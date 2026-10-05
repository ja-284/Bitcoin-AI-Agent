"""
Read-only statistics and reporting over the live record: reporting contract v1 (docs/api/reporting_v1.md).

    python -m agent.reporting latest | runs | run --hour <ISO> | statistics | health | all   [--at <ISO>] [--pretty]

The direction of flow is the whole point of this package:

    live system -> authoritative database records -> agent.reporting (read-only) -> a future UI

Nothing flows back. This package:

- reads the append-only record through a connection that Postgres itself holds READ ONLY
  (`source.read_only_connection`), so a write is refused by the database, not just avoided by the code;
- is imported by nothing in the live system, the shadow job, the workflows or the research bench that
  judges the model (tests/test_reporting_separation.py, plus mutation guards);
- computes every figure deterministically from the records "as they stood at a moment" (`views.known_at`),
  so a later outcome can never leak into an earlier run's view;
- reuses the registered checkpoint's own selection rule and statistics, so its running figures cannot
  drift from the checkpoint -- and it never computes, pre-empts or replaces a checkpoint;
- labels every figure with the number of observations behind it and never presents one as a verdict.

What its numbers must never be used for is written into every document it emits (`NEVER_USE_FOR`).
"""

REPORTING_CONTRACT_VERSION = "1"
# Incidents are recorded from this date; failed runs from before were backfilled from GitHub's run history.
INCIDENT_CAPTURE_STARTED = "2026-10-05"

NEVER_USE_FOR = (
    "tuning, refitting or recalibrating any model",
    "choosing features, thresholds, horizons, targets or algorithms",
    "changing, pre-empting or replacing a registered checkpoint (research/LIVE_EVALUATION.md)",
    "trading or investment decisions: this system does not trade and is not financial advice",
)
