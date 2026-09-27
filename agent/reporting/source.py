"""
The only place the reporting layer touches the database.

Every statement here is a SELECT, and every one runs on a connection that Postgres itself holds READ
ONLY: psycopg opens each transaction with `BEGIN READ ONLY`, so an INSERT, UPDATE or DELETE sent
through it is refused by the server ("cannot execute ... in a read-only transaction") whatever the
role's privileges are. That matters locally, where `.env` holds the owner role, which could write.
tests/test_reporting_separation.py keeps this module SELECT-only and the connection read-only;
tests/integration/test_reporting_readonly.py proves the refusal on real Postgres.

Deliberately NOT read: the text of shadow-job error messages (a stringified exception is not
something to publish -- the same rule agent/api/state.py follows), news headlines and raw indicator
snapshots (large, and not needed for statistics).
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agent.database.db import get_connection
from agent.research.live_checkpoint import CHECKPOINTS, OUT_DIR, TERCILES_PATH

PREDICTIONS_SQL = """
    SELECT id, as_of, cutoff_at, fetched_at, created_at, pipeline_version, scoring_version, signal,
           overall_score, overall_confidence, agreement_score, completeness_score, close_price,
           price_source, price_is_synthetic, ai_model_news, ai_model_explanation,
           (explanation IS NOT NULL AND explanation <> '') AS has_explanation,
           COALESCE(jsonb_array_length(news_items), 0) AS news_items_n, run_meta
    FROM predictions ORDER BY as_of
"""
OUTCOMES_SQL = """
    SELECT prediction_id, horizon_hours, status, price_at_horizon, pct_change_from_prediction, checked_at
    FROM prediction_outcomes ORDER BY prediction_id, horizon_hours
"""
SHADOW_SQL = """
    SELECT as_of, cutoff_at, fetched_at, created_at, model_version, pipeline_version, status, status_reason,
           features, p_calibrated, threshold, horizon_hours, live_close_match,
           outcome_status, outcome_return, outcome_large, outcome_checked_at
    FROM shadow_move_size ORDER BY as_of
"""
SHADOW_ERRORS_SQL = """
    SELECT occurred_at, expected_as_of, step, error_type FROM shadow_run_errors ORDER BY occurred_at
"""
BACKEND_STATE_SQL = "SELECT contract_version, generated_at FROM backend_state WHERE id = 1"
SCHEMA_VERSION_SQL = "SELECT value FROM schema_meta WHERE key = 'schema_version'"
TABLE_EXISTS_SQL = "SELECT to_regclass(%s)"
RUN_DETAIL_SQL = """
    SELECT explanation, category_scores, created_at FROM predictions WHERE as_of = %s
"""
ALL_RUN_DETAILS_SQL = """
    SELECT as_of, explanation, category_scores, created_at FROM predictions ORDER BY as_of
"""


@dataclass(frozen=True)
class Records:
    """The authoritative rows, as read. Nothing here is derived; `views` derives everything."""

    predictions: list[dict]
    outcomes: list[dict]
    shadow: list[dict]
    shadow_errors: list[dict]
    backend_state: dict | None
    schema_version: str | None
    run_detail: dict | None = None  # explanation and category scores of ONE requested hour
    run_details: dict | None = None  # the same for EVERY hour (as_of -> detail), when the publisher asks for it


def read_only_connection():
    """A connection whose every transaction the server runs READ ONLY. Fails closed."""
    conn = get_connection()
    conn.read_only = True
    if conn.read_only is not True:
        conn.close()
        raise RuntimeError("the reporting connection could not be made read-only; refusing to read through it")
    return conn


def _rows(cur, sql: str, params: tuple = ()) -> list[dict]:
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _exists(cur, table: str) -> bool:
    cur.execute(TABLE_EXISTS_SQL, (table,))
    return cur.fetchone()[0] is not None


def load(detail_hour: datetime | None = None, all_details: bool = False) -> Records:
    """Everything the views need, in one read-only transaction (one consistent snapshot of the record)."""
    with read_only_connection() as conn, conn.cursor() as cur:
        preds = _rows(cur, PREDICTIONS_SQL)
        outcomes = _rows(cur, OUTCOMES_SQL)
        shadow = _rows(cur, SHADOW_SQL) if _exists(cur, "shadow_move_size") else []
        errors = _rows(cur, SHADOW_ERRORS_SQL) if _exists(cur, "shadow_run_errors") else []
        state = _rows(cur, BACKEND_STATE_SQL) if _exists(cur, "backend_state") else []
        version = _rows(cur, SCHEMA_VERSION_SQL) if _exists(cur, "schema_meta") else []
        detail = _rows(cur, RUN_DETAIL_SQL, (detail_hour,)) if detail_hour is not None else []
        details = {d.pop("as_of"): d for d in _rows(cur, ALL_RUN_DETAILS_SQL)} if all_details else None
    return Records(predictions=preds, outcomes=outcomes, shadow=shadow, shadow_errors=errors,
                   backend_state=state[0] if state else None,
                   schema_version=version[0]["value"] if version else None,
                   run_detail=detail[0] if detail else None, run_details=details)


def computed_readings(out_dir: Path = OUT_DIR) -> dict[int, str]:
    """Registered checkpoint readings that exist on disk (written once by live_checkpoint, never here)."""
    return {c: str(out_dir / f"checkpoint_{c}h.md") for c in CHECKPOINTS if (out_dir / f"checkpoint_{c}h.md").exists()}


def frozen_terciles(path: Path = TERCILES_PATH) -> tuple[float, float] | None:
    """The development-period volatility cut points the 5,000-hour checkpoint uses (never recomputed)."""
    if not path.exists():
        return None
    return tuple(json.loads(path.read_text(encoding="utf-8"))["tercile_cut_points"])
