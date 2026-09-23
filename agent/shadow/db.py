"""Storage for the shadow record. Only touches shadow_move_size (plus a read of predictions.close_price for the cross-check)."""

from datetime import datetime
from pathlib import Path

from psycopg.types.json import Jsonb

from agent.database.db import get_connection

SCHEMA_PATH = Path(__file__).parent / "schema.sql"  # applied by `python -m agent.migrate`, never at runtime


def shadow_exists(as_of: datetime) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM shadow_move_size WHERE as_of = %s LIMIT 1", (as_of,))
        return cur.fetchone() is not None


def live_close_for(as_of: datetime) -> float | None:
    """The live prediction's reference close for this hour, if that row exists (read-only cross-check)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT close_price FROM predictions WHERE as_of = %s", (as_of,))
        row = cur.fetchone()
        return float(row[0]) if row else None


def save_shadow(row: dict) -> int | None:
    """Insert one hour. ON CONFLICT DO NOTHING: a second run for the same hour changes nothing."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO shadow_move_size (as_of, cutoff_at, fetched_at, model_version, pipeline_version, code_commit, price_source,
                                          reference_close, live_close_match, status, status_reason, features, p_raw, p_calibrated,
                                          threshold, horizon_hours)
            VALUES (%(as_of)s, %(cutoff_at)s, %(fetched_at)s, %(model_version)s, %(pipeline_version)s, %(code_commit)s, %(price_source)s,
                    %(reference_close)s, %(live_close_match)s, %(status)s, %(status_reason)s, %(features)s, %(p_raw)s, %(p_calibrated)s,
                    %(threshold)s, %(horizon_hours)s)
            ON CONFLICT (as_of) DO NOTHING
            RETURNING id
            """,
            {**row, "features": Jsonb(row["features"]) if row.get("features") is not None else None},
        )
        out = cur.fetchone()
        conn.commit()
        return out[0] if out else None


def shadow_rows_awaiting_outcome(now: datetime) -> list[tuple[int, datetime, float, float, int]]:
    """(id, as_of, reference_close, threshold, horizon) for graded-able rows: status ok, no outcome yet, target candle closed."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, as_of, reference_close, threshold, horizon_hours FROM shadow_move_size
            WHERE status = 'ok' AND outcome_status IS NULL
              AND as_of + (horizon_hours || ' hours')::interval + interval '1 hour' <= %s
            ORDER BY as_of
            """,
            (now,),
        )
        return [(r[0], r[1], float(r[2]), float(r[3]), int(r[4])) for r in cur.fetchall()]


def save_run_error(row: dict) -> int | None:
    """Record an operational failure of the shadow job. Nothing about it is silent."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO shadow_run_errors (expected_as_of, step, error_type, error_message, model_version, pipeline_version, code_commit)
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
        cur.execute("SELECT to_regclass('shadow_run_errors')")
        if cur.fetchone()[0] is None:
            return []
        cur.execute(
            """SELECT occurred_at, expected_as_of, step, error_type, error_message, code_commit
               FROM shadow_run_errors WHERE occurred_at >= %s ORDER BY occurred_at""",
            (since,),
        )
        return [dict(zip(["occurred_at", "expected_as_of", "step", "error_type", "error_message", "code_commit"], r)) for r in cur.fetchall()]


def save_shadow_outcome(row_id: int, close: float | None, ret: float | None, large: bool | None, status: str, checked_at: datetime) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE shadow_move_size SET outcome_status = %s, outcome_close = %s, outcome_return = %s, outcome_large = %s, outcome_checked_at = %s
            WHERE id = %s AND outcome_status IS NULL
            """,
            (status, close, ret, large, checked_at, row_id),
        )
        conn.commit()
