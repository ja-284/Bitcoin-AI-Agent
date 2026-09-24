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
  - (2026-09-23) no table is reachable through Supabase's public API, and each of the two
    protecting layers -- revoked privileges and Row Level Security -- works on its own
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
    from agent.migrate import migrate

    migrate()  # the one migration entry point: all three schema files, one transaction
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


def test_record_is_append_only_and_invariants_are_enforced_by_the_database(scratch_db):
    """Backend Phase E: the database itself refuses changes to the research record and rows that break the timestamp rules."""
    import psycopg

    db, sdb = scratch_db
    as_of = datetime(2026, 1, 6, tzinfo=timezone.utc)
    pid = db.save_prediction(_prediction(as_of))
    db.save_outcome(pid, 1, 101.0, 0.01)

    def refused(sql, params=()):
        with pytest.raises(psycopg.Error):
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()

    refused("UPDATE predictions SET signal = 'BUY' WHERE id = %s", (pid,))
    refused("DELETE FROM predictions WHERE id = %s", (pid,))
    refused("UPDATE prediction_outcomes SET pct_change_from_prediction = 0.5 WHERE prediction_id = %s", (pid,))
    refused("DELETE FROM prediction_outcomes WHERE prediction_id = %s", (pid,))
    # timestamp rules at insert time
    bad = _prediction(datetime(2026, 1, 7, tzinfo=timezone.utc))
    bad.fetched_at = bad.cutoff_at - timedelta(minutes=1)
    with pytest.raises(psycopg.Error):
        db.save_prediction(bad)
    bad = _prediction(datetime(2026, 1, 8, tzinfo=timezone.utc))
    bad.cutoff_at = bad.as_of + timedelta(hours=2)
    with pytest.raises(psycopg.Error):
        db.save_prediction(bad)
    # an 'ok' outcome without numbers, or a bad status, cannot exist
    refused("INSERT INTO prediction_outcomes (prediction_id, horizon_hours, status) VALUES (%s, 6, 'ok')", (pid,))
    refused("INSERT INTO prediction_outcomes (prediction_id, horizon_hours, status, price_at_horizon, pct_change_from_prediction) VALUES (%s, 6, 'weird', 1, 1)", (pid,))
    # shadow: the prediction part is immutable, the outcome is written once, deletes refused
    s_as_of = datetime(2026, 1, 9, tzinfo=timezone.utc)
    sid = sdb.save_shadow({"as_of": s_as_of, "cutoff_at": s_as_of + HOUR, "fetched_at": s_as_of + HOUR + timedelta(minutes=12), "model_version": "v", "pipeline_version": "0.2.0",
                           "code_commit": None, "price_source": "binance", "reference_close": 100.0, "live_close_match": None, "status": "ok", "status_reason": None,
                           "features": {}, "p_raw": 0.5, "p_calibrated": 0.5, "threshold": 0.0025, "horizon_hours": 1})
    refused("UPDATE shadow_move_size SET p_calibrated = 0.9 WHERE id = %s", (sid,))
    refused("DELETE FROM shadow_move_size WHERE id = %s", (sid,))
    now = s_as_of + timedelta(hours=3)
    sdb.save_shadow_outcome(sid, 100.3, 0.003, True, "ok", now)  # allowed once
    refused("UPDATE shadow_move_size SET outcome_return = 0.9 WHERE id = %s", (sid,))  # and never again
    with sdb.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT outcome_return FROM shadow_move_size WHERE id = %s", (sid,))
        assert cur.fetchone()[0] == 0.003


def test_shadow_run_errors_are_recorded_and_append_only(scratch_db):
    """A failed shadow job must leave a readable trace that nothing can quietly edit away."""
    import psycopg

    db, sdb = scratch_db
    row = {"expected_as_of": datetime(2026, 1, 10, tzinfo=timezone.utc), "step": "load_model", "error_type": "ModelVersionError",
           "error_message": "feature definitions changed since move_size_1h_v1 was fitted", "model_version": "move_size_1h_v1",
           "pipeline_version": "0.2.0", "code_commit": "abc123"}
    first = sdb.save_run_error(row)
    second = sdb.save_run_error({**row, "step": "fetch"})
    assert first and second and second != first  # every failure is its own row (not deduplicated)
    got = sdb.run_errors_since(datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert [g["step"] for g in got] == ["load_model", "fetch"] and "feature definitions changed" in got[0]["error_message"]
    assert sdb.run_errors_since(datetime(2027, 1, 1, tzinfo=timezone.utc)) == []
    for sql in ("UPDATE shadow_run_errors SET error_message = 'nothing to see' WHERE id = %s",
                "DELETE FROM shadow_run_errors WHERE id = %s"):
        with pytest.raises(psycopg.Error):
            with db.get_connection() as conn, conn.cursor() as cur:
                cur.execute(sql, (first,))
                conn.commit()


# ---------------------------------------------------------------- public-API lockdown (2026-09-23)
# Supabase's `anon` role is what anyone holding the project's public anon key acts as. Two layers
# keep it out -- revoked privileges AND Row Level Security with no policies -- and each layer is
# proven here on its own, because a test that only ever sees the first layer stop the probe
# cannot tell you whether the second one works. Everything happens in the scratch schema.
def _as_role(db, role: str, sql: str):
    """Run one statement as an API role, inside a transaction that is always rolled back."""
    import psycopg

    with db.get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(f"SET LOCAL ROLE {role}")
            cur.execute(sql)
            return cur.fetchone()[0] if cur.description else "ok"
        except psycopg.Error as exc:
            return exc
        finally:
            conn.rollback()


def test_every_table_is_locked_against_the_public_api(scratch_db):
    db, _ = scratch_db  # the fixture applied all three schema files through agent.migrate
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = %s AND c.relkind = 'r' ORDER BY 1""", (SCHEMA,))
        tables = dict(cur.fetchall())
        assert set(tables) >= {"predictions", "prediction_outcomes", "schema_meta", "shadow_move_size",
                               "shadow_run_errors", "backend_state"}
        assert all(tables.values()), f"RLS is off on: {[t for t, on in tables.items() if not on]}"
        for t in tables:
            for role in ("anon", "authenticated"):
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    cur.execute("SELECT has_table_privilege(%s, %s, %s)", (role, f"{SCHEMA}.{t}", priv))
                    assert not cur.fetchone()[0], f"`{role}` still holds {priv} on {t}"


def test_rls_alone_hides_every_row_even_if_a_privilege_is_regranted(scratch_db):
    """
    The second layer, isolated: hand `anon` the schema and SELECT on predictions -- exactly the
    kind of mistake a future dashboard click could make -- and RLS must still show it nothing.
    Then switch RLS off and the same query must see the row, which proves the test is measuring
    RLS and not something else.
    """
    db, _ = scratch_db
    db.save_prediction(_prediction(datetime(2026, 1, 5, tzinfo=timezone.utc)))
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO anon")
        cur.execute("GRANT SELECT ON predictions TO anon")
        conn.commit()
    assert _as_role(db, "anon", "SELECT count(*) FROM predictions") == 0, "RLS did not hide the row"

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE predictions DISABLE ROW LEVEL SECURITY")
        conn.commit()
    assert _as_role(db, "anon", "SELECT count(*) FROM predictions") == 1, (
        "with RLS off the re-granted row should be visible -- if not, the test above measured nothing")


@pytest.fixture
def least_privileged(scratch_db, monkeypatch):
    """
    The backend's own modules, connected as a throwaway role that holds EXACTLY the permissions in
    docs/ops/least_privilege_role.sql -- the file applied verbatim, in the scratch schema only.
    The role is NOLOGIN (it cannot be used to connect by anyone) and is dropped afterwards; the
    test acts as it through SET ROLE on its own connection.
    """
    from pathlib import Path

    import psycopg

    import agent.api.publish as pub

    db, sdb = scratch_db
    base_url, scoped = os.getenv("DATABASE_URL"), db.DATABASE_URL
    source = Path("docs/ops/least_privilege_role.sql").read_text(encoding="utf-8")
    assert source.count("SCHEMA public") == 2, "the file changed shape -- update the substitution below"
    sql = source.replace("bitcoin_agent", PROBE_ROLE).replace("SCHEMA public", f"SCHEMA {SCHEMA}")

    def drop_role(cur):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (PROBE_ROLE,))
        if cur.fetchone():
            cur.execute(f"DROP OWNED BY {PROBE_ROLE}")
            cur.execute(f"DROP ROLE {PROBE_ROLE}")

    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        drop_role(cur)  # a leftover from an interrupted run
        cur.execute(f"CREATE ROLE {PROBE_ROLE} NOLOGIN")
        cur.execute(f"GRANT {PROBE_ROLE} TO current_user WITH SET TRUE")  # PG 16+: needed to SET ROLE to it
        conn.commit()
    with db.get_connection() as conn, conn.cursor() as cur:  # the scratch schema, as the owner
        cur.execute(sql)
        conn.commit()

    def as_probe():
        conn = psycopg.connect(scoped)
        conn.execute(f"SET ROLE {PROBE_ROLE}")
        conn.commit()  # SET is transactional; commit makes it hold for the session
        return conn

    for module in (db, sdb, pub):
        monkeypatch.setattr(module, "get_connection", as_probe)
    yield db, sdb, pub, as_probe
    # Drop the scratch schema first -- it holds every policy and grant naming the role -- then the role.
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        drop_role(cur)
        conn.commit()


PROBE_ROLE = "bitcoin_agent_ci_probe"


def test_the_least_privilege_role_can_do_everything_the_hourly_job_does(least_privileged):
    """Every write path the hourly job uses, run AS the restricted role, must work."""
    db, sdb, pub, as_probe = least_privileged
    with as_probe() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_user")
        assert cur.fetchone()[0] == PROBE_ROLE, "the test is not actually running as the restricted role"

    db.assert_schema_current()                                   # reads schema_meta
    as_of = datetime(2026, 2, 1, tzinfo=timezone.utc)
    pid = db.save_prediction(_prediction(as_of))                 # INSERT ... RETURNING
    assert pid and db.prediction_exists(as_of) and db.latest_prediction_as_of() == as_of
    with as_probe() as conn, conn.cursor() as cur:  # the database stamped the role that wrote it
        cur.execute("SELECT run_meta->>'db_role' FROM predictions WHERE id = %s", (pid,))
        assert cur.fetchone()[0] == PROBE_ROLE
    now = as_of + timedelta(hours=10)
    assert pid in [p[0] for p in db.predictions_awaiting_outcome(1, now)]
    db.save_outcome(pid, 1, 101.0, 0.01)
    db.save_outcome_unavailable(pid, 6)

    row = {"as_of": as_of, "cutoff_at": as_of + HOUR, "fetched_at": as_of + HOUR + timedelta(minutes=12),
           "model_version": "move_size_1h_v1", "pipeline_version": "0.2.0", "code_commit": None,
           "price_source": "binance", "reference_close": 100.0, "live_close_match": True, "status": "ok",
           "status_reason": None, "features": {"rv_24": 0.01}, "p_raw": 0.5, "p_calibrated": 0.55,
           "threshold": 0.0025, "horizon_hours": 1}
    sid = sdb.save_shadow(row)
    assert sid and sdb.shadow_exists(as_of) and sdb.live_close_for(as_of) == 100.0
    assert [r[0] for r in sdb.shadow_rows_awaiting_outcome(now)] == [sid]
    # The case the hand-written policy got wrong: grading SETS outcome_status, so an UPDATE policy
    # whose USING clause is also applied to the new row would refuse every single grading.
    sdb.save_shadow_outcome(sid, 100.3, 0.003, True, "ok", now)
    assert sdb.shadow_rows_awaiting_outcome(now) == [], "grading was silently refused"
    sdb.save_shadow_outcome(sid, 1.0, -0.99, False, "ok", now)  # a second grading must change nothing
    with as_probe() as conn, conn.cursor() as cur:
        cur.execute("SELECT outcome_status, outcome_close FROM shadow_move_size WHERE id = %s", (sid,))
        assert cur.fetchone() == ("ok", 100.3)

    assert sdb.save_run_error({"expected_as_of": as_of, "step": "probe", "error_type": "Probe",
                               "error_message": "least-privilege probe", "model_version": None,
                               "pipeline_version": None, "code_commit": None})
    assert [e["step"] for e in sdb.run_errors_since(as_of)] == ["probe"]

    state = {"contract_version": "1", "generated_at": "2026-02-01T00:00:00+00:00", "health": {"status": "ok"}}
    pub.publish(state)
    pub.publish({**state, "generated_at": "2026-02-01T01:00:00+00:00"})  # the hourly replace
    with as_probe() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), max(generated_at) FROM backend_state")
        count, latest = cur.fetchone()
        assert count == 1 and latest.hour == 1


def test_the_least_privilege_role_cannot_do_anything_else(least_privileged):
    """And everything outside the job's needs is refused -- privileges, policies and ownership each hold."""
    import psycopg

    db, _, _, as_probe = least_privileged
    as_of = datetime(2026, 2, 2, tzinfo=timezone.utc)
    pid = db.save_prediction(_prediction(as_of))
    refused = {
        "rewrite a prediction": f"UPDATE predictions SET signal = 'BUY' WHERE id = {pid}",
        "delete a prediction": f"DELETE FROM predictions WHERE id = {pid}",
        "change a shadow probability": "UPDATE shadow_move_size SET p_calibrated = 0",
        "delete a shadow row": "DELETE FROM shadow_move_size",
        "move the schema version": "UPDATE schema_meta SET value = '9'",
        "switch RLS off": "ALTER TABLE predictions DISABLE ROW LEVEL SECURITY",
        "drop a table": "DROP TABLE backend_state",
    }
    for what, sql in refused.items():
        with as_probe() as conn, conn.cursor() as cur:
            with pytest.raises(psycopg.Error, match="permission denied|must be owner|append-only"):
                cur.execute(sql)
            conn.rollback()


def test_the_role_check_passes_on_the_applied_file_and_catches_an_extra_grant(least_privileged):
    """
    agent.database.role_check against a role that received exactly the file (the fixture's probe,
    NOLOGIN by design) -- and then one grant too many, which it must name.
    """
    from agent.database import role_check as rc

    db, _, _, _ = least_privileged
    expected = rc.expected_from_sql(rc.SQL_FILE.read_text(encoding="utf-8"))
    facts = rc.facts(PROBE_ROLE, SCHEMA)
    assert rc.judge(facts, expected, require_login=False) == [], rc.judge(facts, expected, require_login=False)
    assert facts["notes"], "the Supabase PUBLIC grant on net should be noted for any role"
    import psycopg

    # db.get_connection acts as the probe inside this fixture; the grant needs the owner.
    with psycopg.connect(db.DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(f"GRANT DELETE ON predictions TO {PROBE_ROLE}")
        conn.commit()
    problems = rc.judge(rc.facts(PROBE_ROLE, SCHEMA), expected, require_login=False)
    assert "predictions: holds DELETE, which the file does not grant" in problems, problems


def test_the_server_accepts_a_locally_computed_scram_verifier(scratch_db):
    """
    agent.database.setup_role never sends the plain password: it sends the SCRAM verifier libpq computes
    locally. Prove the live server accepts that form -- on a throwaway role that CANNOT log in, dropped
    at once (no login is ever created by a test).
    """
    import psycopg
    from psycopg import sql

    probe = "bitcoin_agent_ci_scram_probe"
    base_url = os.getenv("DATABASE_URL")
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (probe,))
        if cur.fetchone():
            cur.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(probe)))
        verifier = conn.pgconn.encrypt_password(b"throwaway-never-used", probe.encode(), b"scram-sha-256").decode()
        assert verifier.startswith("SCRAM-SHA-256$") and "throwaway" not in verifier
        try:
            cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN PASSWORD {}").format(sql.Identifier(probe), sql.Literal(verifier)))
            cur.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", (probe,))
            assert cur.fetchone() == (False,)
        finally:
            conn.rollback()  # nothing persists: the role never exists outside this transaction
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (probe,))
        assert cur.fetchone() is None


def test_the_connection_tester_accepts_the_restricted_role_and_refuses_the_owner(least_privileged):
    """agent.database.try_connection's checks, run for real: OK as the probe role, NOT READY as the owner."""
    import psycopg

    from agent.database import try_connection as tc

    db, _, _, as_probe = least_privileged
    db.save_prediction(_prediction(datetime(2026, 2, 3, tzinfo=timezone.utc)))  # something for the read check to see
    with as_probe() as conn:
        facts = tc.describe(conn)
    assert tc.judge(facts, expected_role=PROBE_ROLE) == [], tc.judge(facts, expected_role=PROBE_ROLE)
    with psycopg.connect(db.DATABASE_URL) as conn:  # the owner, in the scratch schema
        owner = tc.describe(conn)
    assert any("not the restricted role" in p for p in tc.judge(owner, expected_role=owner["role"]))


def test_the_least_privilege_policies_are_invisible_to_the_security_check(least_privileged):
    """Policies scoped to the backend role must not be reported as a public-API exposure."""
    from agent.database.security import posture

    result = posture(SCHEMA)
    assert result["ok"], result["problems"]
    assert any(t["policies"] for t in result["tables"].values()), "the policies were not there to ignore"


def _structure(cur, schema: str) -> dict:
    """
    Everything that defines a schema's behaviour, normalised so two schemas can be compared:
    columns (type, nullability, default), constraints, indexes, triggers, RLS flags, policies and
    the public API roles' privileges. Schema qualifiers are stripped, column ORDER is ignored
    (a column added by a later migration sits at the end of a live table but in the middle of a
    freshly built one -- that difference is cosmetic, a missing or different column is not).
    """
    import re

    def norm(text):
        return None if text is None else re.sub(rf"\b{re.escape(schema)}\.", "", text)

    out: dict = {}
    cur.execute("""SELECT table_name, column_name, data_type, is_nullable, column_default
                   FROM information_schema.columns WHERE table_schema = %s""", (schema,))
    out["columns"] = {(t, c, d, n, norm(dflt)) for t, c, d, n, dflt in cur.fetchall()}
    cur.execute("""SELECT cl.relname, co.conname, pg_get_constraintdef(co.oid)
                   FROM pg_constraint co JOIN pg_class cl ON cl.oid = co.conrelid
                   JOIN pg_namespace n ON n.oid = cl.relnamespace WHERE n.nspname = %s""", (schema,))
    out["constraints"] = {(t, name, norm(d)) for t, name, d in cur.fetchall()}
    cur.execute("SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = %s", (schema,))
    out["indexes"] = {(t, i, norm(d)) for t, i, d in cur.fetchall()}
    cur.execute("""SELECT cl.relname, t.tgname, t.tgenabled, pg_get_triggerdef(t.oid)
                   FROM pg_trigger t JOIN pg_class cl ON cl.oid = t.tgrelid
                   JOIN pg_namespace n ON n.oid = cl.relnamespace
                   WHERE n.nspname = %s AND NOT t.tgisinternal""", (schema,))
    out["triggers"] = {(t, name, enabled, norm(d)) for t, name, enabled, d in cur.fetchall()}
    cur.execute("""SELECT cl.relname, cl.relrowsecurity, cl.relforcerowsecurity FROM pg_class cl
                   JOIN pg_namespace n ON n.oid = cl.relnamespace WHERE n.nspname = %s AND cl.relkind = 'r'""", (schema,))
    out["rls"] = set(cur.fetchall())
    cur.execute("SELECT tablename, policyname, roles::text, cmd, qual, with_check FROM pg_policies WHERE schemaname = %s", (schema,))
    out["policies"] = set(cur.fetchall())
    cur.execute("""SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
                   WHERE table_schema = %s AND grantee IN ('anon', 'authenticated')""", (schema,))
    out["api_grants"] = set(cur.fetchall())
    # the standing rule for NEW objects (2026-09-23 evening): must grant the API roles nothing
    cur.execute("""SELECT d.defaclobjtype, g.rolname, a.privilege_type FROM pg_default_acl d
                   JOIN pg_namespace n ON n.oid = d.defaclnamespace CROSS JOIN LATERAL aclexplode(d.defaclacl) a
                   JOIN pg_roles g ON g.oid = a.grantee
                   WHERE n.nspname = %s AND g.rolname IN ('anon', 'authenticated') AND d.defaclrole = 'postgres'::regrole""", (schema,))
    out["api_default_grants"] = set(cur.fetchall())
    return out


def test_the_live_database_matches_what_the_repository_builds(scratch_db):
    """
    Reproducibility and drift, in one check: build the schema fresh from the repository (the
    fixture did, through agent.migrate) and compare it, piece by piece, with the LIVE `public`
    schema. A column, constraint, trigger, RLS flag, policy or public-API grant that exists in one
    and not the other means the repository no longer describes production -- a change made by hand
    in the dashboard, or a migration never applied. The live schema is only READ here.
    """
    db, _ = scratch_db
    with db.get_connection() as conn, conn.cursor() as cur:
        built = _structure(cur, SCHEMA)
        live = _structure(cur, "public")
    assert built["columns"], "the comparison would be vacuous"
    differences = {}
    for part in built:
        only_live, only_built = live[part] - built[part], built[part] - live[part]
        if only_live or only_built:
            differences[part] = {"only in the live database": sorted(map(str, only_live)),
                                 "only in what the repository builds": sorted(map(str, only_built))}
    assert not differences, "the live database has drifted from the repository:\n" + "\n".join(
        f"  {part}: {d}" for part, d in differences.items())


def test_the_drift_check_actually_detects_drift(scratch_db):
    """
    The comparison above passed at its first run, which proves nothing unless it can fail. Make
    three hand-made changes to the freshly built copy -- the kinds a dashboard click produces --
    and each must show up as a difference against the live schema.
    """
    db, _ = scratch_db
    with db.get_connection() as conn, conn.cursor() as cur:
        before = _structure(cur, SCHEMA)
        cur.execute("ALTER TABLE predictions ADD COLUMN added_by_hand integer")
        cur.execute("ALTER TABLE backend_state DISABLE ROW LEVEL SECURITY")
        cur.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO anon")
        cur.execute("GRANT SELECT ON schema_meta TO anon")
        conn.commit()
        after = _structure(cur, SCHEMA)
        live = _structure(cur, "public")
    assert before["columns"] == live["columns"] and before["rls"] == live["rls"]  # identical before
    assert any(c[1] == "added_by_hand" for c in after["columns"] - live["columns"])
    assert ("backend_state", False, False) in after["rls"] - live["rls"]
    assert ("schema_meta", "anon", "SELECT") in after["api_grants"] - live["api_grants"]


def test_the_standing_rule_that_exposed_every_new_table_is_removed(scratch_db):
    """
    The root cause (2026-09-23 evening). Supabase's default privileges grant every NEW object in
    `public` to the API roles. Recreate that rule in the scratch schema, prove it bites (control),
    re-apply the schema files, and a table, a view and a sequence created afterwards must be closed
    -- while the object created under the old rule keeps its grant, which shows the migration
    changes the rule and not objects by accident.
    """
    db, _ = scratch_db
    from agent.database.security import posture
    from agent.migrate import migrate

    with db.get_connection() as conn, conn.cursor() as cur:
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            cur.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} GRANT ALL ON {kind} TO anon, authenticated")
        cur.execute("CREATE TABLE made_under_the_old_rule (x int)")
        conn.commit()
        cur.execute("SELECT has_table_privilege('anon', %s, 'SELECT')", (f"{SCHEMA}.made_under_the_old_rule",))
        assert cur.fetchone()[0], "control failed: the simulated Supabase rule did not grant the new table"
    assert any(p.startswith("default privileges:") for p in posture(SCHEMA)["problems"]), \
        "the detector must see the standing rule before the migration removes it"

    migrate()  # the schema files again: idempotent, and they now remove the rule
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("CREATE TABLE made_after_the_fix (x int)")
        cur.execute("CREATE SEQUENCE seq_after_the_fix")
        cur.execute("CREATE VIEW view_after_the_fix AS SELECT count(*) AS n FROM predictions")
        conn.commit()
        for obj, priv in (("made_after_the_fix", "SELECT"), ("view_after_the_fix", "SELECT"),
                          ("made_after_the_fix", "INSERT")):
            for role in ("anon", "authenticated"):
                cur.execute("SELECT has_table_privilege(%s, %s, %s)", (role, f"{SCHEMA}.{obj}", priv))
                assert not cur.fetchone()[0], f"`{role}` got {priv} on {obj}, created after the fix"
        cur.execute("SELECT has_sequence_privilege('anon', %s, 'USAGE')", (f"{SCHEMA}.seq_after_the_fix",))
        assert not cur.fetchone()[0]
        cur.execute("SELECT has_table_privilege('anon', %s, 'SELECT')", (f"{SCHEMA}.made_under_the_old_rule",))
        assert cur.fetchone()[0], "existing grants are the table lockdown's job, not this block's"
        cur.execute("DROP TABLE made_under_the_old_rule, made_after_the_fix")
        cur.execute("DROP VIEW view_after_the_fix")
        conn.commit()


def test_the_detector_sees_a_view_and_a_callable_function(scratch_db):
    """
    The two objects the tables-only check could never see. A view granted to `anon` publishes
    what it selects past RLS; a plain function is callable at /rest/v1/rpc -- and Postgres grants
    EXECUTE to PUBLIC by default, which a per-schema rule cannot remove, so only the detector
    stands between a new helper function and the internet. Closing both must make it pass again.
    """
    from agent.database.security import posture

    db, _ = scratch_db
    assert posture(SCHEMA)["ok"], posture(SCHEMA)["problems"]  # the trigger functions do not count
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("CREATE VIEW latest_by_hand AS SELECT as_of FROM predictions")
        cur.execute("GRANT SELECT ON latest_by_hand TO anon")
        cur.execute("CREATE FUNCTION helper_by_hand() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        conn.commit()
    problems = posture(SCHEMA)["problems"]
    assert any(p.startswith("view latest_by_hand: `anon` holds SELECT") for p in problems), problems
    assert any("helper_by_hand() is callable by `anon`" in p for p in problems), problems
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("REVOKE ALL ON latest_by_hand FROM anon")
        cur.execute("REVOKE EXECUTE ON FUNCTION helper_by_hand() FROM PUBLIC, anon, authenticated")
        conn.commit()
    assert posture(SCHEMA)["ok"], posture(SCHEMA)["problems"]


def test_the_revoke_alone_blocks_writes_even_with_rls_off(scratch_db):
    """The first layer, isolated: with RLS switched off, revoked privileges must still refuse a write."""
    import psycopg

    db, _ = scratch_db
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO anon")
        cur.execute("ALTER TABLE schema_meta DISABLE ROW LEVEL SECURITY")
        conn.commit()
    result = _as_role(db, "anon", "UPDATE schema_meta SET value = '0'")
    assert isinstance(result, psycopg.errors.InsufficientPrivilege), result
