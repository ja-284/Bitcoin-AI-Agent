"""
Fails (exit code 1) if the newest saved prediction is older than allowed. Used two ways:

- right after each hourly run, as a self-check that a row actually landed for this hour
- from a separate watchdog schedule, so a silently skipped run becomes a failed job --
  and GitHub emails the repository owner about failed scheduled jobs, for free

    python -m agent.healthcheck --max-age-hours 2
    python -m agent.healthcheck --shadow-errors-max 2 --shadow-errors-hours 6
    python -m agent.healthcheck --new-gap-since 2026-10-14T13:12:05Z --gap-body-file missed-hours.txt

The second form is the watchdog's alarm for the research shadow job: a single failed hour is
recorded and tolerated (it does not turn the hourly job red), but a PERSISTENT failure must
still reach the owner. Added after 2026-09-21/22, when a broken shadow step made every second
hourly run red while the live record was in fact healthy.

The third form is the hourly job's alarm for a SINGLE missed hour (added 2026-10-14). It never
fails: it reports, and the workflow sends the report to the heartbeat service (see new_gap()).
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.database.db import latest_prediction_as_of, newest_predictions

HOUR = timedelta(hours=1)
GAP_HOURS_LISTED = 24  # a longer outage is summarised rather than listed hour by hour


def check(max_age_hours: float, now: datetime | None = None, latest: datetime | None = None) -> tuple[bool, str]:
    """
    `latest` lets a caller that has already read the newest `as_of` pass it in instead of
    causing a second query. It exists so that everything judging staleness -- the self-check,
    the watchdog and the outward-facing state in agent/api/state.py -- uses THIS definition
    and cannot drift into disagreeing about whether the system is healthy.
    """
    now = now or datetime.now(tz=timezone.utc)
    latest = latest if latest is not None else latest_prediction_as_of()
    if latest is None:
        return False, "no predictions in the database at all"
    # as_of is the open of the reference candle; the run for it can't happen before as_of + 1h.
    age = now - (latest + timedelta(hours=1))
    ok = age <= timedelta(hours=max_age_hours)
    return ok, f"newest prediction is for {latest.isoformat()} ({age.total_seconds() / 3600:.1f}h since its candle closed)"


def check_shadow_errors(max_errors: int, hours: float = 6.0, now: datetime | None = None) -> tuple[bool, str]:
    """False when the shadow job has failed more than `max_errors` times in the last `hours`."""
    from agent.shadow.db import run_errors_since

    now = now or datetime.now(tz=timezone.utc)
    errors = run_errors_since(now - timedelta(hours=hours))
    if not errors:
        return True, f"no shadow-job errors in the last {hours:g}h"
    steps = ", ".join(sorted({e["step"] for e in errors}))
    latest = errors[-1]
    detail = f"{len(errors)} shadow-job error(s) in the last {hours:g}h (steps: {steps}); latest {latest['error_type']}: {latest['error_message'][:200]}"
    return len(errors) <= max_errors, detail


def new_gap(inserted_since: datetime, newest: list[tuple[datetime, datetime]] | None = None) -> tuple[list[datetime], datetime | None]:
    """
    The hours that became PERMANENTLY missing when this run saved its prediction, and the hour it saved
    (None if it saved none). The alarm for a single missed hour: on 2026-10-07 one hour had no run at
    all, the heartbeat pings either side were 87 min apart (inside its 90 min allowance), and nothing
    alarmed.

    A run only ever analyses the latest closed hour, and nothing is backfilled. So an hour is missing
    for good once a later hour is saved, and never before: a late run is not a missed hour. Only the run
    that SAVED the first hour after a gap sees that row as created at or after its own start, so each
    gap is reported exactly once; the backup runs later in the hour, and re-runs, see nothing new.

    `inserted_since` is this job's start (the runner's clock); created_at is the database's clock. The
    row is written about a minute after the job starts, so only a clock difference of that size could
    hide a gap; it could never invent one.
    `newest` is [(as_of, created_at)] of the two newest predictions, newest first (read if not given).
    """
    rows = newest if newest is not None else newest_predictions(2)
    if not rows or rows[0][1] < inserted_since:
        return [], None
    saved = rows[0][0]
    if len(rows) < 2:
        return [], saved  # the very first prediction has nothing before it to be missing
    missing, t = [], rows[1][0] + HOUR
    while t < saved:
        missing.append(t)
        t += HOUR
    return missing, saved


def gap_message(missing: list[datetime], saved: datetime) -> str:
    """The plain-words report the heartbeat service shows. Hours only: no secret, no URL, nothing else."""
    hours = ", ".join(f"{h:%Y-%m-%d %H:%M}" for h in missing[:GAP_HOURS_LISTED])
    if len(missing) > GAP_HOURS_LISTED:
        hours += f" ... {missing[-1]:%Y-%m-%d %H:%M} ({len(missing) - GAP_HOURS_LISTED} more not listed)"
    return (f"Bitcoin-AI-Agent: {len(missing)} hourly prediction(s) permanently missing, never backfilled "
            f"(UTC): {hours}. Found by the run that saved the {saved:%Y-%m-%d %H:%M} UTC hour, which itself "
            f"succeeded. Look at GitHub Actions for that period.")


def _utc(stamp: str) -> datetime:
    when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if when.tzinfo is None:
        raise argparse.ArgumentTypeError(f"{stamp!r} has no time zone; give UTC, e.g. 2026-10-14T13:12:05Z")
    return when


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-hours", type=float)
    parser.add_argument("--shadow-errors-max", type=int)
    parser.add_argument("--shadow-errors-hours", type=float, default=6.0)
    parser.add_argument("--new-gap-since", type=_utc, help="this job's start (UTC): report hours missing before the hour it saved")
    parser.add_argument("--gap-body-file", type=Path, help="with --new-gap-since: always written; holds the report, or nothing")
    args = parser.parse_args(argv)
    if args.max_age_hours is None and args.shadow_errors_max is None and args.new_gap_since is None:
        parser.error("give --max-age-hours, --shadow-errors-max and/or --new-gap-since")

    failed = False
    if args.max_age_hours is not None:
        ok, message = check(args.max_age_hours)
        print(("OK: " if ok else "STALE: ") + message)
        failed = failed or not ok
    if args.shadow_errors_max is not None:
        ok, message = check_shadow_errors(args.shadow_errors_max, args.shadow_errors_hours)
        print(("OK: " if ok else "SHADOW FAILING: ") + message)
        failed = failed or not ok
    if args.new_gap_since is not None:
        # Reports, never fails: a missed hour is past and permanent, and this run saved its own hour.
        missing, saved = new_gap(args.new_gap_since)
        report = gap_message(missing, saved) if missing else ""
        if args.gap_body_file is not None:
            args.gap_body_file.write_text(report + ("\n" if report else ""), encoding="utf-8")  # empty: nothing to send
        if saved is None:
            print("OK: this run saved no new hour, so it has no gap to report")
        elif not missing:
            print(f"OK: no hour is missing before {saved.isoformat()}, the hour this run saved")
        else:
            print("MISSED: " + report)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
