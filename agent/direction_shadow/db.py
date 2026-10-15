"""
Storage for the direction shadow track. Writes only shadow_direction and shadow_direction_errors; reads the live
predictions table for two read-only cross-checks (the reference close and the category scores), nothing else.
"""

from datetime import datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from agent.database.db import get_connection

SCHEMA_PATH = Path(__file__).parent / "schema.sql"  # applied by `python -m agent.migrate`, never at runtime
LIVE_CATEGORY_NAMES = {"trend": "trend_score", "momentum": "momentum_score", "volume": "volume_score",
                       "chart_pattern": "chart_pattern_score"}


def row_exists(as_of: datetime) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM shadow_direction WHERE as_of = %s LIMIT 1", (as_of,))
        return cur.fetchone() is not None


def live_reference_for(as_of: datetime) -> tuple[float, dict[str, float]] | None:
    """The live prediction's reference close and its four technical category scores for this hour, if it exists."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT close_price, category_scores FROM predictions WHERE as_of = %s", (as_of,))
        row = cur.fetchone()
    if not row:
        return None
    scores = {LIVE_CATEGORY_NAMES[c["name"]]: float(c["score"]) for c in (row[1] or []) if c.get("name") in LIVE_CATEGORY_NAMES}
    return float(row[0]), scores


def save_row(row: dict) -> int | None:
    """Insert one hour. ON CONFLICT DO NOTHING: a second run for the same hour changes nothing."""
    cols = ("as_of", "cutoff_at", "fetched_at", "model_version", "artefact_sha256", "pipeline_version", "scoring_version",
            "code_commit", "price_source", "reference_close", "price_at_prediction", "live_close_match", "live_scores_match",
            "status", "status_reason", "features", "regime_rv_168", "p_model", "p_one_feature", "p_base", "horizon_hours")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO shadow_direction ({', '.join(cols)}) VALUES ({', '.join('%(' + c + ')s' for c in cols)}) "
            "ON CONFLICT (as_of) DO NOTHING RETURNING id",
            {**{c: row.get(c) for c in cols}, "features": Jsonb(row["features"]) if row.get("features") is not None else None},
        )
        out = cur.fetchone()
        conn.commit()
        return out[0] if out else None


def rows_awaiting_outcome(now: datetime) -> list[tuple[int, datetime, float, int]]:
    """(id, as_of, reference_close, horizon) for rows with status ok, no outcome yet, and a closed target candle."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, as_of, reference_close, horizon_hours FROM shadow_direction
            WHERE status = 'ok' AND outcome_status IS NULL
              AND as_of + (horizon_hours || ' hours')::interval + interval '1 hour' <= %s
            ORDER BY as_of
            """,
            (now,),
        )
        return [(r[0], r[1], float(r[2]), int(r[3])) for r in cur.fetchall()]


def save_outcome(row_id: int, close: float | None, ret: float | None, up: bool | None, status: str, checked_at: datetime) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE shadow_direction SET outcome_status = %s, outcome_close = %s, outcome_return = %s, outcome_up = %s,
                                        outcome_checked_at = %s
            WHERE id = %s AND outcome_status IS NULL
            """,
            (status, close, ret, up, checked_at, row_id),
        )
        conn.commit()


def save_run_error(row: dict) -> int | None:
    """Record an operational failure of the direction step. Nothing about it is silent."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO shadow_direction_errors (expected_as_of, step, error_type, error_message, model_version, pipeline_version, code_commit)
            VALUES (%(expected_as_of)s, %(step)s, %(error_type)s, %(error_message)s, %(model_version)s, %(pipeline_version)s, %(code_commit)s)
            RETURNING id
            """,
            row,
        )
        out = cur.fetchone()
        conn.commit()
        return out[0] if out else None


def run_errors_since(since: datetime) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('shadow_direction_errors')")
        if cur.fetchone()[0] is None:
            return []
        cur.execute(
            """SELECT occurred_at, expected_as_of, step, error_type, error_message, code_commit
               FROM shadow_direction_errors WHERE occurred_at >= %s ORDER BY occurred_at""",
            (since,),
        )
        return [dict(zip(["occurred_at", "expected_as_of", "step", "error_type", "error_message", "code_commit"], r)) for r in cur.fetchall()]
