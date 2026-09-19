"""
The only module that knows any SQL. Everything else just hands this module a
Prediction object -- if the database is ever swapped for something else, this is
the one file that would need to change.
"""

import dataclasses
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


def save_prediction(prediction: Prediction) -> Optional[int]:
    category_scores_json = [dataclasses.asdict(c) for c in prediction.category_scores]

    news_items_json = []
    for item in prediction.news_items:
        d = dataclasses.asdict(item)
        d["published_at"] = d["published_at"].isoformat()
        news_items_json.append(d)

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO predictions (
                as_of, fetched_at, close_price, price_source, price_is_synthetic,
                overall_score, signal, agreement_score, completeness_score, overall_confidence,
                scoring_version, ai_model_news, ai_model_explanation, explanation,
                category_scores, news_items, raw_indicators
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (as_of) DO NOTHING
            RETURNING id
            """,
            (
                prediction.as_of,
                prediction.fetched_at,
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
