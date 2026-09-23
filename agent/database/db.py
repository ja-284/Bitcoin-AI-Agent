"""
The only module that knows any SQL. Everything else just hands this module a
Prediction object -- if the database is ever swapped for something else, this is
the one file that would need to change.
"""

import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg
from psycopg.types.json import Jsonb

from agent.config.settings import DATABASE_URL, DB_CONNECT_TIMEOUT_S
from agent.shared.types import Prediction

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set (check your .env file)")
    return psycopg.connect(DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT_S)


SCHEMA_VERSION = "4"  # 1: original tables; 2: cutoff/version/status migrations (pipeline 0.2.0); 3: invariants + append-only triggers + schema_meta; 4: public-API lockdown (RLS on, API roles revoked, 2026-09-23)
# The value written by schema.sql's schema_meta upsert must match this constant (checked by a test).


def init_schema() -> None:
    sql = SCHEMA_PATH.read_text()
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()


def schema_version() -> Optional[str]:
    """The schema version recorded in the database, or None before schema_meta exists."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('schema_meta')")
        if cur.fetchone()[0] is None:
            return None
        cur.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'")
        row = cur.fetchone()
        return row[0] if row else None


def schema_is_compatible(found: Optional[str]) -> bool:
    """
    True when the database has AT LEAST the schema this code was written against.

    "At least", not "exactly" (changed 2026-09-23). Migrations in this project are additive: they
    add constraints, triggers and access rules and never remove anything older code relies on, so
    a database that is AHEAD of the code still has everything the code needs. Requiring exact
    equality turned every migration into a two-sided deployment with a window in which the running
    code and the database disagree and the hourly job fails for no reason. With "at least", the
    order is simply: migrate the database first, then deploy the code. A migration that ever
    REMOVES or CHANGES something older code relies on breaks this assumption and must say so at
    the top of its section in schema.sql.

    Anything that is not a version number fails closed.
    """
    try:
        return found is not None and int(found) >= int(SCHEMA_VERSION)
    except ValueError:
        return False


def assert_schema_current() -> None:
    """
    Fail loudly, before anything is written, if the database is OLDER than the schema this code
    was written against.

    An older database is not a cosmetic problem. Version 3 added the CHECK constraints (the cutoff
    rule, fetch-after-cutoff, outcome consistency) and the append-only triggers; version 4 locked
    every table against Supabase's public API. Code elsewhere assumes those exist -- an older
    database would quietly accept rows this project believes are impossible, or accept them from
    anyone holding the public key. Checking costs one small query an hour; not checking costs a
    corrupted record that looks fine.
    """
    found = schema_version()
    if not schema_is_compatible(found):
        raise RuntimeError(
            f"database schema is {found!r} but this code expects at least {SCHEMA_VERSION!r}. "
            "The invariants, append-only triggers or access lockdown this code relies on may be missing. "
            "Apply the migrations first: python -c \"from agent.database.db import init_schema; init_schema()\""
        )


def prediction_exists(as_of: datetime) -> bool:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM predictions WHERE as_of = %s LIMIT 1", (as_of,))
        return cur.fetchone() is not None


def latest_prediction_as_of() -> Optional[datetime]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT max(as_of) FROM predictions")
        row = cur.fetchone()
        return row[0] if row else None


def save_prediction(prediction: Prediction) -> Optional[int]:
    category_scores_json = [dataclasses.asdict(c) for c in prediction.category_scores]

    news_items_json = []
    for item in prediction.news_items:
        d = dataclasses.asdict(item)
        d["published_at"] = d["published_at"].isoformat() if d["published_at"] else None
        news_items_json.append(d)

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO predictions (
                as_of, cutoff_at, fetched_at, pipeline_version, run_meta,
                close_price, price_source, price_is_synthetic,
                overall_score, signal, agreement_score, completeness_score, overall_confidence,
                scoring_version, ai_model_news, ai_model_explanation, explanation,
                category_scores, news_items, raw_indicators
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (as_of) DO NOTHING
            RETURNING id
            """,
            (
                prediction.as_of,
                prediction.cutoff_at,
                prediction.fetched_at,
                prediction.pipeline_version,
                Jsonb(prediction.run_meta),
                prediction.close_price,
                prediction.price_source,
                prediction.price_is_synthetic,
                prediction.overall_score,
                prediction.signal,
                prediction.confidence.agreement_score,
                prediction.confidence.completeness_score,
                prediction.confidence.overall_confidence,
                prediction.scoring_version,
                prediction.ai_model_news,
                prediction.ai_model_explanation,
                prediction.explanation,
                Jsonb(category_scores_json),
                Jsonb(news_items_json),
                Jsonb(prediction.raw_indicators),
            ),
        )
        row = cur.fetchone()
        conn.commit()

    return row[0] if row else None  # None means a prediction for this hour already existed


def predictions_awaiting_outcome(horizon_hours: int, now: datetime) -> list[tuple[int, datetime, float]]:
    """Predictions old enough to be graded at this horizon that haven't been graded yet."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.as_of, p.close_price
            FROM predictions p
            LEFT JOIN prediction_outcomes o
                   ON o.prediction_id = p.id AND o.horizon_hours = %s
            WHERE o.id IS NULL
              AND p.as_of + make_interval(hours => %s) + interval '1 hour' <= %s
            ORDER BY p.as_of
            """,
            (horizon_hours, horizon_hours, now),
        )
        return [(row[0], row[1], float(row[2])) for row in cur.fetchall()]


def save_outcome(prediction_id: int, horizon_hours: int, price_at_horizon: float, pct_change: float) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO prediction_outcomes (prediction_id, horizon_hours, status, price_at_horizon, pct_change_from_prediction)
            VALUES (%s, %s, 'ok', %s, %s)
            ON CONFLICT (prediction_id, horizon_hours) DO NOTHING
            """,
            (prediction_id, horizon_hours, price_at_horizon, pct_change),
        )
        conn.commit()


def save_outcome_unavailable(prediction_id: int, horizon_hours: int) -> None:
    """The target candle does not exist in the exchange's history; record that fact and stop retrying."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO prediction_outcomes (prediction_id, horizon_hours, status)
            VALUES (%s, %s, 'unavailable')
            ON CONFLICT (prediction_id, horizon_hours) DO NOTHING
            """,
            (prediction_id, horizon_hours),
        )
        conn.commit()
