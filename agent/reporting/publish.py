"""
Publish the private stats read model (docs/api/stats_access.md).

    python -m agent.reporting.publish            # compute from the record and store the two caches
    python -m agent.reporting.publish --dry-run  # compute and print what would be stored; store nothing

THIS IS A PRIVATE READ-ONLY STATISTICS INTERFACE. IT IS NOT THE FUTURE AUTOMATED-TRADING APPLICATION.

It runs in its own workflow (.github/workflows/reporting.yml) AFTER each hourly run completes -- never
inside the hourly job, which is unchanged. It is downstream only:

- it READS the record through the reporting layer's read-only connection (`source.load`), and computes
  with the reporting layer's own functions (`views.report`, `views.all_runs`) -- nothing is recalculated
  differently for the website;
- it WRITES nothing but `reporting_snapshot` and `reporting_runs`, two derived caches that nothing in
  the system ever reads back (tests/test_reporting_separation.py pins the write targets);
- it refuses to publish anything dated inside the sealed holdout;
- a transient failure is tolerated (the previous snapshot stays, visibly older by its own timestamp); a
  failure that has left the snapshot older than STALE_AFTER exits 1, so it is noticed without an email
  every time one attempt fails;
- (2026-10-05) its own problems stay visible afterwards: a failed publish (if the database can still be
  reached) and a snapshot that went more than STALE_AFTER without a refresh are recorded as incidents
  (agent/reporting/incidents.py), before the new snapshot is computed, so the snapshot shows them.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

from agent.database.db import get_connection
from agent.reporting import REPORTING_CONTRACT_VERSION, incidents, views
from agent.reporting.source import computed_readings, frozen_terciles, load, read_only_connection
from agent.research.periods import HOLDOUT

logger = logging.getLogger(__name__)

CACHE_TABLES = ("reporting_snapshot", "reporting_runs")
STALE_AFTER = timedelta(hours=3)

SNAPSHOT_SQL = """
    INSERT INTO reporting_snapshot (id, reporting_contract_version, as_known_at, generated_at, document)
    VALUES (1, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE
       SET reporting_contract_version = EXCLUDED.reporting_contract_version,
           as_known_at = EXCLUDED.as_known_at, generated_at = EXCLUDED.generated_at, document = EXCLUDED.document
"""
# A run's row changes only when its content does (an outcome recorded, pending -> overdue), so an hourly
# publish rewrites a handful of rows, not the whole history.
RUN_SQL = """
    INSERT INTO reporting_runs (hour, reporting_contract_version, as_known_at, run)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (hour) DO UPDATE
       SET reporting_contract_version = EXCLUDED.reporting_contract_version,
           as_known_at = EXCLUDED.as_known_at, run = EXCLUDED.run
     WHERE reporting_runs.run IS DISTINCT FROM EXCLUDED.run
        OR reporting_runs.reporting_contract_version IS DISTINCT FROM EXCLUDED.reporting_contract_version
"""
SNAPSHOT_AGE_SQL = "SELECT generated_at FROM reporting_snapshot WHERE id = 1"


def refuse_holdout(hours) -> None:
    """Nothing dated inside the sealed holdout may ever be published. The record cannot contain such an hour
    (it begins 2026-09-19); this makes that a checked fact rather than an assumption."""
    inside = [h for h in hours if HOLDOUT.start <= h < HOLDOUT.end]
    if inside:
        raise RuntimeError(f"refusing to publish {len(inside)} hour(s) inside the sealed holdout, first {inside[0].isoformat()}")


def build(records, at: datetime, now: datetime, terciles=None, computed=None) -> tuple[dict, dict[datetime, dict]]:
    """The two things the website may read, computed by the reporting layer's own functions."""
    runs = views.all_runs(records, at)
    refuse_holdout(runs)
    snapshot = views.document("all", views.report(records, at, terciles, computed), at, now)
    return snapshot, {hour: views.clean(run) for hour, run in runs.items()}


def _cache_connection():
    """The publisher's only write connection. Everything it sends is SNAPSHOT_SQL or RUN_SQL."""
    return get_connection()


def store(snapshot: dict, runs: dict[datetime, dict], at: datetime, now: datetime) -> dict:
    """Replace the snapshot row and upsert the run rows, in one transaction."""
    with _cache_connection() as conn, conn.cursor() as cur:
        cur.execute(SNAPSHOT_SQL, (REPORTING_CONTRACT_VERSION, at, now, json.dumps(snapshot, allow_nan=False)))
        cur.executemany(RUN_SQL, [(hour, REPORTING_CONTRACT_VERSION, at, json.dumps(run, allow_nan=False))
                                  for hour, run in runs.items()])
        conn.commit()
    return {"runs": len(runs), "snapshot_bytes": len(json.dumps(snapshot)), "as_known_at": at.isoformat()}


def snapshot_generated_at() -> datetime | None:
    """When the stored snapshot was computed, read through the read-only connection; None if there is none."""
    with read_only_connection() as conn, conn.cursor() as cur:
        cur.execute(SNAPSHOT_AGE_SQL)
        row = cur.fetchone()
    return None if row is None else row[0]


def snapshot_age(now: datetime) -> timedelta | None:
    generated = snapshot_generated_at()
    return None if generated is None else now - generated


def stale_incident(previous: datetime | None, now: datetime) -> dict | None:
    """The incident for a refresh gap longer than STALE_AFTER, or None. Pure."""
    if previous is None or now - previous <= STALE_AFTER:
        return None
    hours = (now - previous).total_seconds() / 3600
    return incidents.publisher_incident(
        "stats_snapshot_was_stale", previous,
        f"The stats snapshot was not refreshed between {previous:%Y-%m-%d %H:%M} and {now:%Y-%m-%d %H:%M} UTC ({hours:.1f} hours).",
        f"stale:{previous:%Y-%m-%dT%H:%M:%S}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish the private stats read model (read-only statistics).")
    parser.add_argument("--dry-run", action="store_true", help="compute and summarise; store nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    now = datetime.now(timezone.utc)
    try:
        gap = stale_incident(snapshot_generated_at(), now)
        if gap is not None and not args.dry_run:
            incidents.record(gap)  # before computing, so the new snapshot already shows it
        records = load(all_details=True)
        snapshot, runs = build(records, now, now, frozen_terciles(), computed_readings())
        if args.dry_run:
            print(json.dumps({"would_store": {"runs": len(runs), "snapshot_bytes": len(json.dumps(snapshot)),
                                              "newest_hour": max(runs).isoformat() if runs else None}}, indent=2))
            return 0
        logger.info("published the stats read model: %s", store(snapshot, runs, now, now))
        return 0
    except Exception as exc:  # noqa: BLE001 -- a publish failure must never be louder than it deserves
        logger.error("could not publish the stats read model: %s: %s", type(exc).__name__, exc)
        try:  # best effort: if the database is unreachable this cannot be written either, and the stale rule takes over
            incidents.record(incidents.publisher_incident(
                "stats_publish_failed", now, f"Publishing the stats snapshot failed ({type(exc).__name__}).",
                f"failed:{now:%Y-%m-%dT%H}"))
        except Exception:  # noqa: BLE001
            logger.warning("the failure could not be recorded as an incident either")
        try:
            age = snapshot_age(now)
        except Exception:  # noqa: BLE001
            age = None
        if age is not None and age <= STALE_AFTER:
            logger.warning("the previous snapshot (%.1f h old) stays in place; a later run will refresh it",
                           age.total_seconds() / 3600)
            return 0
        logger.error("the stats read model is missing or older than %s: failing so it is noticed", STALE_AFTER)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
