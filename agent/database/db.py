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

from agent.config.settings import DATABASE_URL
from agent.shared.types import Prediction

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> psycopg.Connection:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set (check your .env file)")
    return psycopg.connect(DATABASE_URL)


def init_schema() -> None:
    sql = SCHEMA_PATH.read_text()
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()


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
            INSERT INTO prediction_outcomes (prediction_id, horizon_hours, price_at_horizon, pct_change_from_prediction)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (prediction_id, horizon_hours) DO NOTHING
            """,
            (prediction_id, horizon_hours, price_at_horizon, pct_change),
        )
        conn.commit()
