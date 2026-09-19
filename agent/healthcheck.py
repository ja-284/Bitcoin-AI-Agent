"""
Fails (exit code 1) if the newest saved prediction is older than allowed. Used two ways:

- right after each hourly run, as a self-check that a row actually landed for this hour
- from a separate watchdog schedule, so a silently skipped run becomes a failed job --
  and GitHub emails the repository owner about failed scheduled jobs, for free

    python -m agent.healthcheck --max-age-hours 2
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

from agent.database.db import latest_prediction_as_of


def check(max_age_hours: float, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now(tz=timezone.utc)
    latest = latest_prediction_as_of()
    if latest is None:
        return False, "no predictions in the database at all"
    # as_of is the open of the reference candle; the run for it can't happen before as_of + 1h.
    age = now - (latest + timedelta(hours=1))
    ok = age <= timedelta(hours=max_age_hours)
    return ok, f"newest prediction is for {latest.isoformat()} ({age.total_seconds() / 3600:.1f}h since its candle closed)"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-age-hours", type=float, required=True)
    args = parser.parse_args()
    ok, message = check(args.max_age_hours)
    print(("OK: " if ok else "STALE: ") + message)
    sys.exit(0 if ok else 1)
