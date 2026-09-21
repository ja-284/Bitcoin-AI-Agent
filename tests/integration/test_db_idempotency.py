"""
Backend Phase D: idempotency and duplicate safety against a REAL Postgres, in a scratch
schema that is created and dropped by the test -- the live tables are never touched.

Runs only when explicitly asked (needs a database):

    BITCOIN_AGENT_DB_TESTS=1 python -m pytest tests/integration -q

What is proven at the SQL level (the unit tests fake the database):
  - saving the same hour twice leaves one prediction row; the second save returns None
  - grading the same (prediction, horizon) twice leaves one outcome row; an 'unavailable'
    attempt after an 'ok' row (or the reverse) never overwrites
  - running the outcome tracker twice grades nothing the second time
  - a retry after a failed save produces exactly one row
  - the shadow table behaves the same way, and grading a shadow row twice keeps the first
  - the uniqueness constraints that make all of this true actually exist in the schema
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(os.getenv("BITCOIN_AGENT_DB_TESTS") != "1", reason="needs a database; set BITCOIN_AGENT_DB_TESTS=1")

SCHEMA = "idempotency_test"
HOUR = timedelta(hours=1)


@pytest.fixture
def scratch_db(monkeypatch):
    import psycopg

    import agent.database.db as db
    import agent.shadow.db as sdb

    base_url = os.getenv("DATABASE_URL")
    assert base_url, "DATABASE_URL must be set"
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {SCHEMA}")
        conn.commit()
    sep = "&" if "?" in base_url else "?"
    scoped = f"{base_url}{sep}options=-c%20search_path%3D{SCHEMA}"
    monkeypatch.setattr(db, "DATABASE_URL", scoped)
    # Guard before creating anything: every connection the code opens must land in the scratch
    # schema. If the pooler ignored the search_path option, writes would hit the LIVE tables.
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_schema()")
        assert cur.fetchone()[0] == SCHEMA, "search_path option not honoured -- refusing to touch the database"
    db.init_schema()
    sdb.ensure_schema()
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'predictions' AND table_schema = %s", (SCHEMA,))
        assert cur.fetchone(), "scratch tables were not created in the scratch schema"
    yield db, sdb
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.commit()


def _prediction(as_of: datetime):
    from agent.shared.types import CategoryScore, ConfidenceBreakdown, Prediction

    return Prediction(
        as_of=as_of, cutoff_at=as_of + HOUR, fetched_at=as_of + HOUR + timedelta(minutes=12), close_price=100.0, price_source="binance",
        price_is_synthetic=False, overall_score=0.1, signal="HOLD",
        confidence=ConfidenceBreakdown(agreement_score=0.5, completeness_score=1.0, overall_confidence=0.6),
        category_scores=[CategoryScore("trend", 0.1, 0.25, False, {})], scoring_version="0.1.0", pipeline_version="0.2.0",
        news_items=[], raw_indicators={"close": 100.0}, run_meta={}, ai_model_news=None, ai_model_explanation=None, explanation=None,
    )


def test_constraints_exist(scratch_db):
    db, _ = scratch_db
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT table_name, constraint_type FROM information_schema.table_constraints
                       WHERE table_schema = %s AND constraint_type = 'UNIQUE' ORDER BY 1""", (SCHEMA,))
        uniques = {t for t, _ in cur.fetchall()}
    assert {"predictions", "prediction_outcomes", "shadow_move_size"} <= uniques


def test_saving_the_same_hour_twice_keeps_one_row(scratch_db):
    db, _ = scratch_db
    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = db.save_prediction(_prediction(as_of))
    second = db.save_prediction(_prediction(as_of))
    assert first is not None and second is None
    assert db.prediction_exists(as_of)
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM predictions")
        assert cur.fetchone()[0] == 1


def test_retry_after_a_failed_save_produces_exactly_one_row(scratch_db, monkeypatch):
    db, _ = scratch_db
    as_of = datetime(2026, 1, 2, tzinfo=timezone.utc)
    real_connect = db.get_connection
    monkeypatch.setattr(db, "get_connection", lambda: (_ for _ in ()).throw(ConnectionError("db down")))
    with pytest.raises(ConnectionError):
        db.save_prediction(_prediction(as_of))
    monkeypatch.setattr(db, "get_connection", real_connect)
    assert db.save_prediction(_prediction(as_of)) is not None
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM predictions WHERE as_of = %s", (as_of,))
        assert cur.fetchone()[0] == 1


def test_grading_twice_keeps_the_first_outcome(scratch_db):
    db, _ = scratch_db
    as_of = datetime(2026, 1, 3, tzinfo=timezone.utc)
    pid = db.save_prediction(_prediction(as_of))
    db.save_outcome(pid, 1, 101.0, 0.01)
    db.save_outcome(pid, 1, 999.0, 8.99)  # a second grading attempt with different numbers
    db.save_outcome_unavailable(pid, 1)  # and an 'unavailable' attempt after an 'ok' row
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status, price_at_horizon FROM prediction_outcomes WHERE prediction_id = %s", (pid,))
        rows = cur.fetchall()
    assert rows == [("ok", 101.0)]
    # the reverse order: 'unavailable' first is also final
    db.save_outcome_unavailable(pid, 6)
    db.save_outcome(pid, 6, 101.0, 0.01)
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status, price_at_horizon FROM prediction_outcomes WHERE prediction_id = %s AND horizon_hours = 6", (pid,))
        assert cur.fetchall() == [("unavailable", None)]


def test_tracker_run_twice_grades_nothing_the_second_time(scratch_db):
    db, _ = scratch_db
    import agent.outcome_tracker as tracker
    from agent.shared.types import PriceBar

    as_of = datetime(2026, 1, 4, tzinfo=timezone.utc)
    db.save_prediction(_prediction(as_of))

    class Provider:
        def get_bar_at(self, t):
            return PriceBar(t, 100.0, 101.0, 99.0, 100.5, 1.0, "binance")

    now = as_of + timedelta(hours=200)
    first = tracker.track_outcomes(now=now, provider=Provider())
    second = tracker.track_outcomes(now=now, provider=Provider())
    assert first["graded"] == len(tracker.HORIZONS_HOURS) and second["graded"] == 0
    assert db.predictions_awaiting_outcome(1, now) == []


def test_shadow_rows_and_outcomes_are_duplicate_safe(scratch_db):
    _, sdb = scratch_db
    as_of = datetime(2026, 1, 5, tzinfo=timezone.utc)
    row = {"as_of": as_of, "cutoff_at": as_of + HOUR, "fetched_at": as_of + HOUR + timedelta(minutes=12), "model_version": "move_size_1h_v1",
           "pipeline_version": "0.2.0", "code_commit": None, "price_source": "binance", "reference_close": 100.0, "live_close_match": None,
           "status": "ok", "status_reason": None, "features": {"rv_24": 0.01}, "p_raw": 0.5, "p_calibrated": 0.55, "threshold": 0.0025, "horizon_hours": 1}
    first = sdb.save_shadow(row)
    second = sdb.save_shadow({**row, "p_calibrated": 0.99})
    assert first is not None and second is None and sdb.shadow_exists(as_of)
    now = as_of + timedelta(hours=3)
    pending = sdb.shadow_rows_awaiting_outcome(now)
    assert [p[0] for p in pending] == [first]
    sdb.save_shadow_outcome(first, 100.3, 0.003, True, "ok", now)
    sdb.save_shadow_outcome(first, 50.0, -0.5, True, "ok", now)  # second grading must not overwrite
    assert sdb.shadow_rows_awaiting_outcome(now) == []
    with sdb.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT p_calibrated, outcome_close, outcome_return FROM shadow_move_size WHERE id = %s", (first,))
        assert cur.fetchone() == (0.55, 100.3, 0.003)
