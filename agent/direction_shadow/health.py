"""
The direction shadow track's own health monitor and alert (master plan addendum 2026-10-16, item 5). It is separate
from the main model's heartbeat: its own healthchecks.io check (secret DIRECTION_HEARTBEAT_URL), its own protected
record (shadow_direction_health), and it reads only the direction track's own tables.

    python -m agent.direction_shadow.health --actions-file A --fail-body-file B   # the hourly job's step
    python -m agent.direction_shadow.health --status                              # read-only: the current state
    python -m agent.direction_shadow.health --delivery-test-body FILE             # the labelled delivery test's text

The rules (research/DIRECTION_TRACK.md fixes one observation per hour, stored before its outcome candle closes):
  * HEALTHY: the latest closed hour has a valid observation -> a success ping.
  * LATE BUT RECOVERABLE: no valid observation for the latest closed hour yet, but its prospective deadline (as_of + 2h)
    has not passed, so a later run can still record it -> nothing is sent and nothing is recorded. (A failed attempt
    is already in shadow_direction_errors.)
  * LOST: an hour since the track started whose deadline has passed without a valid observation. It can never be
    recorded prospectively, so it is a genuine failure. Each lost hour is recorded ONCE (UNIQUE (kind, hour), so even
    two overlapping runs cannot record it twice).
  * ALERT: a /fail is sent only when this run recorded a lost hour AND no incident was open before it, so one
    unresolved incident gives one alert. A new incident after a recovery alerts again.
  * RECOVERY: when an incident is open and the latest closed hour is valid again, 'recovered' is recorded and the
    success ping is sent, which turns the check green.
  * OVERDUE: if no run reaches this step at all, no success ping arrives and healthchecks.io's own silence alarm
    fires (period 1 h, grace 1 h recommended).

A valid observation is a row with status 'ok', or 'unavailable' for a data reason the protocol registers as an honest
blank (missing inputs, gaps inside the window). Any other 'unavailable' (a scoring-version mismatch, a refused input,
a short fetch) is a failure of the track, not an observation.

It never changes a direction row, a probability, the model, the BUY/HOLD/SELL record or the main heartbeat.
"""

import argparse
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOUR = timedelta(hours=1)
VALID_UNAVAILABLE = ("missing inputs", "gap(s) inside the window")  # data reasons: the registered honest blank
HOURS_LISTED = 24


def expected_hour(now: datetime) -> datetime:
    """The hour whose candle closed most recently: the one a run at `now` scores."""
    return now.replace(minute=0, second=0, microsecond=0) - HOUR


def is_valid(row: dict) -> bool:
    if row["status"] == "ok":
        return True
    reason = row.get("status_reason") or ""
    return row["status"] == "unavailable" and any(r in reason for r in VALID_UNAVAILABLE)


@dataclass
class Assessment:
    expected: datetime
    current_ok: bool
    incident_open_before: bool
    lost: list[datetime]                      # every lost hour since the track started
    new_lost: list[datetime]                  # the lost hours not yet recorded
    record_recovered: bool
    send: list[str] = field(default_factory=list)   # "fail", then "success", in that order

    @property
    def state(self) -> str:
        if self.current_ok:
            return "healthy"
        return "failing" if (self.incident_open_before or self.new_lost) else "late but recoverable"


def assess(rows: list[dict], events: list[dict], now: datetime) -> Assessment:
    """
    Pure. rows: the track's [{as_of, status, status_reason}]; events: its recorded [{kind, hour}] in recording order.
    The deadline of an hour is as_of + 2h: after it, no prospective observation of that hour is possible.
    """
    expected = expected_hour(now)
    valid = {r["as_of"] for r in rows if is_valid(r)}
    lost: list[datetime] = []
    if rows:
        t = min(r["as_of"] for r in rows)
        while t <= expected:
            if t not in valid and now >= t + 2 * HOUR:  # the deadline passed: lost for good
                lost.append(t)
            t += HOUR
    recorded = {e["hour"] for e in events if e["kind"] == "hour_lost"}
    new_lost = [h for h in lost if h not in recorded]
    open_before = bool(events) and events[-1]["kind"] == "hour_lost"
    current_ok = expected in valid
    a = Assessment(expected, current_ok, open_before, lost, new_lost, record_recovered=False)
    if new_lost and not open_before:
        a.send.append("fail")  # a new incident: one alert
    if current_ok:
        a.record_recovered = open_before or bool(new_lost)
        a.send.append("success")
    return a


def fail_message(a: Assessment) -> str:
    hours = ", ".join(f"{h:%Y-%m-%d %H:%M}" for h in a.new_lost[:HOURS_LISTED])
    if len(a.new_lost) > HOURS_LISTED:
        hours += f" ... ({len(a.new_lost) - HOURS_LISTED} more not listed)"
    now_state = ("it recorded the latest hour again, so it has recovered" if a.current_ok
                 else "the latest hour is not recorded yet either")
    return (f"Bitcoin-AI-Agent DIRECTION TRACK (the research shadow track E034, separate from the main hourly prediction, "
            f"which is unaffected): {len(a.new_lost)} hour(s) permanently without a valid direction observation (UTC): {hours}. "
            f"Found by the run assessing the {a.expected:%Y-%m-%d %H:%M} UTC hour; {now_state}. Look at shadow_direction_errors "
            f"and GitHub Actions for that period.")


def delivery_test_message(now: datetime) -> str:
    example = fail_message(Assessment(datetime(2026, 10, 16, 15, tzinfo=timezone.utc), True, False,
                                      [datetime(2026, 10, 16, 13, tzinfo=timezone.utc)], [datetime(2026, 10, 16, 13, tzinfo=timezone.utc)], True))
    return (f"Bitcoin-AI-Agent DELIVERY TEST of the DIRECTION TRACK alert, sent {now:%Y-%m-%d %H:%M} UTC by the manual "
            f"'Alert delivery test' workflow. NO direction hour is lost and nothing failed. The next real hourly run turns this "
            f"check green again. A real report looks like this: \"{example}\"")


# ---------------------------------------------------------------- storage (the job's role: SELECT on the track, INSERT here)
def read_state() -> tuple[list[dict], list[dict]]:
    from agent.database.db import get_connection

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT as_of, status, status_reason FROM shadow_direction ORDER BY as_of")
        rows = [dict(zip(("as_of", "status", "status_reason"), r)) for r in cur.fetchall()]
        cur.execute("SELECT kind, hour, recorded_at FROM shadow_direction_health ORDER BY recorded_at, id")
        events = [dict(zip(("kind", "hour", "recorded_at"), r)) for r in cur.fetchall()]
    return rows, events


def record(a: Assessment) -> tuple[int, bool]:
    """Insert the new lost hours and a recovery; returns (lost hours actually inserted, recovery inserted)."""
    from agent.database.db import get_connection

    run = os.environ.get("GITHUB_RUN_ID")
    run = f"{run}/{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}" if run else None
    commit = os.environ.get("GITHUB_SHA")
    inserted, recovered = 0, False
    with get_connection() as conn, conn.cursor() as cur:
        for h in a.new_lost:
            cur.execute("""INSERT INTO shadow_direction_health (kind, hour, detail, github_run, code_commit)
                           VALUES ('hour_lost', %s, %s, %s, %s) ON CONFLICT (kind, hour) DO NOTHING RETURNING id""",
                        (h, f"no valid direction observation before its deadline {h + 2 * HOUR:%Y-%m-%d %H:%M} UTC; found assessing {a.expected:%Y-%m-%d %H:%M} UTC", run, commit))
            inserted += cur.fetchone() is not None
        if a.record_recovered:
            cur.execute("""INSERT INTO shadow_direction_health (kind, hour, detail, github_run, code_commit)
                           VALUES ('recovered', %s, %s, %s, %s) ON CONFLICT (kind, hour) DO NOTHING RETURNING id""",
                        (a.expected, f"the {a.expected:%Y-%m-%d %H:%M} UTC hour has a valid observation again", run, commit))
            recovered = cur.fetchone() is not None
        conn.commit()
    return inserted, recovered


def step(now: datetime, actions_file: Path, fail_body_file: Path) -> int:
    """The hourly job's step. It never raises into the job: the workflow step is continue-on-error as well."""
    rows, events = read_state()
    a = assess(rows, events, now)
    inserted, _ = record(a)
    send = list(a.send)
    if "fail" in send and inserted == 0:  # a concurrent run recorded these hours first and sent the alert
        send.remove("fail")
    actions_file.write_text("\n".join(send) + ("\n" if send else ""), encoding="utf-8")
    fail_body_file.write_text((fail_message(a) + "\n") if "fail" in send else "", encoding="utf-8")
    print(f"direction track: {a.state}; expected hour {a.expected:%Y-%m-%d %H:%M} UTC valid={a.current_ok}; "
          f"lost hours ever {len(a.lost)}, newly recorded {inserted}; incident open before: {a.incident_open_before}; send {send or 'nothing'}")
    return 0


def status(now: datetime) -> int:
    rows, events = read_state()
    a = assess(rows, events, now)
    print(f"direction track: {a.state}; {len(rows)} rows; expected hour {a.expected:%Y-%m-%d %H:%M} UTC valid={a.current_ok}; "
          f"lost hours ever {len(a.lost)} (recorded {len({e['hour'] for e in events if e['kind'] == 'hour_lost'})}); "
          f"incident open: {bool(events) and events[-1]['kind'] == 'hour_lost'}; events {len(events)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--actions-file", type=Path)
    ap.add_argument("--fail-body-file", type=Path)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--delivery-test-body", type=Path)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    if a.delivery_test_body is not None:
        a.delivery_test_body.write_text(delivery_test_message(now) + "\n", encoding="utf-8")
        print("DIRECTION TRACK DELIVERY TEST report written (nothing is lost; this is a test)")
        return 0
    if a.status:
        return status(now)
    if a.actions_file is None or a.fail_body_file is None:
        ap.error("give --actions-file and --fail-body-file, or --status, or --delivery-test-body")
    return step(now, a.actions_file, a.fail_body_file)


if __name__ == "__main__":
    raise SystemExit(main())
