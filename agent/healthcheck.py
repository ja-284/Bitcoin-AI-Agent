"""
Fails (exit code 1) if the newest saved prediction is older than allowed. Used two ways:

- right after each hourly run, as a self-check that a row actually landed for this hour
- from a separate watchdog schedule, so a silently skipped run becomes a failed job --
  and GitHub emails the repository owner about failed scheduled jobs, for free

    python -m agent.healthcheck --max-age-hours 2
    python -m agent.healthcheck --shadow-errors-max 2 --shadow-errors-hours 6

The second form is the watchdog's alarm for the research shadow job: a single failed hour is
recorded and tolerated (it does not turn the hourly job red), but a PERSISTENT failure must
still reach the owner. Added after 2026-09-21/22, when a broken shadow step made every second
hourly run red while the live record was in fact healthy.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from agent.database.db import latest_prediction_as_of


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-hours", type=float)
    parser.add_argument("--shadow-errors-max", type=int)
    parser.add_argument("--shadow-errors-hours", type=float, default=6.0)
    args = parser.parse_args()
    if args.max_age_hours is None and args.shadow_errors_max is None:
        parser.error("give --max-age-hours and/or --shadow-errors-max")

    failed = False
    if args.max_age_hours is not None:
        ok, message = check(args.max_age_hours)
        print(("OK: " if ok else "STALE: ") + message)
        failed = failed or not ok
    if args.shadow_errors_max is not None:
        ok, message = check_shadow_errors(args.shadow_errors_max, args.shadow_errors_hours)
        print(("OK: " if ok else "SHADOW FAILING: ") + message)
        failed = failed or not ok
    sys.exit(1 if failed else 0)
