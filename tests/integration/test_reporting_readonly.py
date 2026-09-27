"""
The reporting layer against a REAL Postgres, in a scratch schema created and dropped by the test (the live
tables are never touched):

  - a write sent through the reporting connection is refused BY THE DATABASE (a read-only transaction),
    whatever the connecting role's own rights -- locally that role is the owner, which could write;
  - the views read back exactly what the live code paths wrote (predictions, outcomes, shadow rows).

    BITCOIN_AGENT_DB_TESTS=1 python -m pytest tests/integration -q
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(os.getenv("BITCOIN_AGENT_DB_TESTS") != "1", reason="needs a database; set BITCOIN_AGENT_DB_TESTS=1")

SCHEMA = "reporting_test"
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
    monkeypatch.setattr(db, "DATABASE_URL", f"{base_url}{sep}options=-c%20search_path%3D{SCHEMA}")
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_schema()")
        assert cur.fetchone()[0] == SCHEMA, "search_path option not honoured -- refusing to touch the database"
    from agent.migrate import migrate

    migrate()
    yield db, sdb
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.commit()


def _prediction(as_of: datetime, signal: str = "BUY"):
    from agent.shared.types import CategoryScore, ConfidenceBreakdown, Prediction

    return Prediction(
        as_of=as_of, cutoff_at=as_of + HOUR, fetched_at=as_of + HOUR + timedelta(minutes=12), close_price=100.0, price_source="binance",
        price_is_synthetic=False, overall_score=0.1, signal=signal,
        confidence=ConfidenceBreakdown(agreement_score=0.5, completeness_score=1.0, overall_confidence=0.6),
        category_scores=[CategoryScore("trend", 0.1, 0.25, False, {})], scoring_version="0.2.0", pipeline_version="0.2.0",
        news_items=[], raw_indicators={"close": 100.0}, run_meta={"db_role": "test"}, ai_model_news=None, ai_model_explanation=None,
        explanation="text",
    )


def test_the_database_refuses_a_write_through_the_reporting_connection(scratch_db):
    import psycopg

    from agent.reporting.source import read_only_connection

    db, _ = scratch_db
    as_of = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - 5 * HOUR
    assert db.save_prediction(_prediction(as_of)) is not None
    for sql in ("INSERT INTO schema_meta (key, value) VALUES ('probe', 'x')",
                "UPDATE predictions SET signal = 'SELL'",
                "CREATE TABLE reporting_probe (x int)"):
        with read_only_connection() as conn, conn.cursor() as cur:
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                cur.execute(sql)
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), min(signal) FROM predictions")
        assert cur.fetchone() == (1, "BUY")
        cur.execute("SELECT count(*) FROM schema_meta WHERE key = 'probe'")
        assert cur.fetchone()[0] == 0


def test_the_views_read_back_what_the_live_code_wrote(scratch_db):
    from agent.reporting import views
    from agent.reporting.source import load
    from agent.research.live_checkpoint import prospective_graded

    db, sdb = scratch_db
    now = datetime.now(timezone.utc)
    base = now.replace(minute=0, second=0, microsecond=0) - 30 * HOUR
    for i in range(3):
        as_of = base + i * HOUR
        pid = db.save_prediction(_prediction(as_of, ("BUY", "HOLD", "SELL")[i]))
        db.save_outcome(pid, 1, 101.0, 0.01 * (i - 1))
        row_id = sdb.save_shadow({"as_of": as_of, "cutoff_at": as_of + HOUR, "fetched_at": as_of + HOUR + timedelta(minutes=12),
                                  "model_version": "move_size_1h_v1", "pipeline_version": "0.2.0", "code_commit": None,
                                  "price_source": "binance", "reference_close": 100.0, "live_close_match": True, "status": "ok",
                                  "status_reason": None, "features": {"rv_168": 0.004}, "p_raw": 0.4, "p_calibrated": 0.4,
                                  "threshold": 0.0025, "horizon_hours": 1})
        sdb.save_shadow_outcome(row_id, 101.0, 0.01, True, "ok", now)
    records = load(detail_hour=base + 2 * HOUR)
    # rows are stamped by the DATABASE clock (created_at DEFAULT now()), after `now` was taken: view a moment
    # later, with room for a small clock difference -- a view of an earlier moment correctly hides them
    assert views.latest_run(records, now - HOUR) is None
    now = datetime.now(timezone.utc) + timedelta(minutes=5)
    latest = views.latest_run(records, now)
    assert latest["hour"] == (base + 2 * HOUR).isoformat() and latest["signal"]["value"] == "SELL"
    assert latest["outcomes"]["1h"] == latest["outcomes"]["1h"] | {"state": "graded", "return": 0.01}
    assert latest["outcomes"]["168h"]["state"] == "pending"
    assert views.run_at(records, now, base + 2 * HOUR)["explanation"] == "text"
    m = views.move_size_statistics(records, now)
    assert m["sample"]["n"] == len(prospective_graded(records.shadow)) == 3
    # the shadow rows here were stored long after their outcome candle closed only if fetched_at says so; it does not
    assert m["not_prospective"] == 0
    assert views.health(records, now)["schema_version"] is not None
