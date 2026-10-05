"""
The private stats read model against a REAL Postgres (Supabase), in a scratch schema created and dropped by the
test. Each probe acts exactly as Supabase's API does for a website request: it switches to the `anon` or
`authenticated` role and sets the signed token's claims (`request.jwt.claims`, what auth.jwt() reads).

Proven here:
  - a signed-in viewer whose token carries app_metadata.reporting_viewer = true reads both cache tables;
  - an anonymous request (the public project key alone) is refused;
  - a signed-in user WITHOUT that owner-set claim -- including one who puts it in their own user_metadata --
    sees nothing;
  - even the viewer cannot write, delete or truncate anything, cannot read the production record, and cannot
    create anything;
  - the live security check accepts exactly this design and reports every way of widening it.

    BITCOIN_AGENT_DB_TESTS=1 python -m pytest tests/integration -q
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(os.getenv("BITCOIN_AGENT_DB_TESTS") != "1", reason="needs a database; set BITCOIN_AGENT_DB_TESTS=1")

SCHEMA = "stats_access_test"
HOUR = timedelta(hours=1)
VIEWER = {"sub": "00000000-0000-4000-8000-000000000001", "role": "authenticated", "app_metadata": {"reporting_viewer": True}}
CACHES = ("reporting_snapshot", "reporting_runs", "reporting_incidents")
RECORD = ("predictions", "prediction_outcomes", "shadow_move_size", "shadow_run_errors", "backend_state", "schema_meta")


@pytest.fixture
def stats_db(monkeypatch):
    import psycopg

    import agent.database.db as db

    base_url = os.getenv("DATABASE_URL")
    assert base_url, "DATABASE_URL must be set"
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regprocedure('auth.jwt()') IS NOT NULL AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')")
        if not cur.fetchone()[0]:
            pytest.skip("not a Supabase database: no auth.jwt() / authenticated role")
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        cur.execute(f"CREATE SCHEMA {SCHEMA}")
        # Supabase grants the API roles USAGE on `public`; the scratch schema gets the same, so every probe below
        # measures the TABLE-level layers (privileges, RLS, policy) rather than stopping at the schema door.
        cur.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO anon, authenticated")
        conn.commit()
    sep = "&" if "?" in base_url else "?"
    monkeypatch.setattr(db, "DATABASE_URL", f"{base_url}{sep}options=-c%20search_path%3D{SCHEMA}")
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_schema()")
        assert cur.fetchone()[0] == SCHEMA, "search_path option not honoured -- refusing to touch the database"
    from agent.migrate import migrate

    migrate()
    _publish_one_hour(db)
    yield db
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.commit()


def _publish_one_hour(db):
    """Write one real hour through the production save path, then publish it through the real publisher."""
    from agent.reporting import publish
    from agent.reporting.source import load
    from tests.integration.test_reporting_readonly import _prediction

    as_of = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - 6 * HOUR
    pid = db.save_prediction(_prediction(as_of))
    db.save_outcome(pid, 1, 101.0, 0.01)
    at = datetime.now(timezone.utc) + timedelta(minutes=5)
    from agent.reporting import incidents

    incidents.record(incidents.workflow_incident({  # one failed run, through the real recorder
        "INCIDENT_WORKFLOW": "Hourly Bitcoin analysis", "INCIDENT_CONCLUSION": "failure", "INCIDENT_RUN_ID": "99",
        "INCIDENT_RUN_ATTEMPT": "1", "INCIDENT_STARTED_AT": (as_of + 2 * HOUR).isoformat(),
        "INCIDENT_RUN_URL": "https://github.com/ja-284/Bitcoin-AI-Agent/actions/runs/99", "INCIDENT_TRIGGER": "schedule"}))
    snapshot, runs = publish.build(load(all_details=True), at, at)
    publish.store(snapshot, runs, at, at)


def _as(db, role: str, sql: str, claims: dict | None = None):
    """One statement as an API role, with the token claims a signed-in request would carry; always rolled back."""
    import psycopg

    with db.get_connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(f"SET LOCAL ROLE {role}")
            if claims is not None:
                cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (json.dumps(claims),))
            cur.execute(sql)
            return cur.fetchall() if cur.description else "ok"
        except psycopg.Error as exc:
            return exc
        finally:
            conn.rollback()


def _refused(result) -> bool:
    import psycopg

    return isinstance(result, psycopg.errors.InsufficientPrivilege)


def test_a_signed_in_viewer_reads_exactly_what_was_published(stats_db):
    rows = _as(stats_db, "authenticated", "SELECT document->>'kind', reporting_contract_version FROM reporting_snapshot", VIEWER)
    assert rows == [("all", "1")], rows
    runs = _as(stats_db, "authenticated", "SELECT count(*), max(run->'outcomes'->'1h'->>'state') FROM reporting_runs", VIEWER)
    assert runs == [(1, "graded")], runs


def test_the_viewer_sees_the_recorded_incident_and_nobody_can_change_or_erase_it(stats_db):
    rows = _as(stats_db, "authenticated", "SELECT kind, source FROM reporting_incidents", VIEWER)
    assert rows == [("hourly_run_failed", "workflow_event")], rows
    snap = _as(stats_db, "authenticated", "SELECT document->'body'->'health'->'incidents'->>'recorded_total' FROM reporting_snapshot", VIEWER)
    assert snap == [("1",)], snap  # the snapshot published after it shows it
    import psycopg

    for sql in ("UPDATE reporting_incidents SET detail = 'nothing happened'", "DELETE FROM reporting_incidents"):
        with stats_db.get_connection() as conn, conn.cursor() as cur:  # even the OWNER: the trigger refuses it
            with pytest.raises(psycopg.Error, match="append-only"):
                cur.execute(sql)
            conn.rollback()


def test_an_anonymous_request_is_refused(stats_db):
    for table in CACHES:
        assert _refused(_as(stats_db, "anon", f"SELECT count(*) FROM {table}")), table
        assert _refused(_as(stats_db, "anon", f"SELECT count(*) FROM {table}", {"role": "anon"})), table


@pytest.mark.parametrize("claims", [
    None,                                                                  # signed in, but no claims at all
    {"sub": VIEWER["sub"], "role": "authenticated"},                       # an ordinary account
    {**VIEWER, "app_metadata": {"reporting_viewer": False}},
    {**VIEWER, "app_metadata": {"reporting_viewer": "yes"}},
    {**VIEWER, "app_metadata": {}, "user_metadata": {"reporting_viewer": True}},  # users CAN edit user_metadata
], ids=["no-claims", "ordinary-account", "claim-false", "claim-not-true", "self-set-user-metadata"])
def test_a_signed_in_user_without_the_owner_set_claim_sees_nothing(stats_db, claims):
    for table in CACHES:
        assert _as(stats_db, "authenticated", f"SELECT count(*) FROM {table}", claims) == [(0,)], (table, claims)


def test_even_the_viewer_cannot_write_delete_create_or_read_the_record(stats_db):
    attempts = [f"INSERT INTO reporting_runs (hour, reporting_contract_version, as_known_at, run) VALUES (now(), '1', now(), '{{}}')",
                "UPDATE reporting_snapshot SET document = '{}'", "DELETE FROM reporting_runs", "TRUNCATE reporting_runs",
                "CREATE TABLE made_by_the_website (x int)"]
    attempts += [f"UPDATE {t} SET id = id" if t != "schema_meta" else "UPDATE schema_meta SET value = value" for t in RECORD]
    attempts += [f"SELECT count(*) FROM {t}" for t in RECORD]
    for sql in attempts:
        assert _refused(_as(stats_db, "authenticated", sql, VIEWER)), sql
    assert _as(stats_db, "authenticated", "SELECT count(*) FROM reporting_runs", VIEWER) == [(1,)]  # still intact


def test_the_detector_accepts_exactly_the_design_and_reports_every_widening(stats_db):
    from agent.database import security

    result = security.posture(SCHEMA)
    assert result["ok"], result["problems"]
    assert result["functions"] == [] and result["views"] == {}, "nothing callable or view-shaped is exposed"
    for table in CACHES:
        (pol,) = [p for p in result["tables"][table]["policies"] if p["roles"] == ["authenticated"]]
        assert security._normalised(pol["qual"]) == security.VIEWER_CONDITION, pol["qual"]  # the real deparse
    widenings = {
        "GRANT SELECT ON reporting_runs TO anon": "reporting_runs: `anon` holds SELECT",
        "GRANT INSERT ON reporting_snapshot TO authenticated": "reporting_snapshot: `authenticated` holds INSERT",
        "CREATE POLICY wide_open ON reporting_runs FOR SELECT TO authenticated USING (true)": "policy `wide_open` lets through more",
        ("ALTER POLICY stats_viewer_read ON reporting_snapshot USING "
         "((auth.jwt() -> 'user_metadata' ->> 'reporting_viewer') = 'true')"): "policy `stats_viewer_read` lets through more",
        "GRANT SELECT ON predictions TO authenticated": "predictions: `authenticated` holds SELECT",
    }
    from agent.migrate import migrate

    with stats_db.get_connection() as conn, conn.cursor() as cur:
        for sql, expected in widenings.items():
            cur.execute(sql)
            conn.commit()  # posture() reads on its own connection
            problems = security.posture(SCHEMA)["problems"]
            assert any(expected in p for p in problems), (sql, problems)
            cur.execute("REVOKE ALL ON reporting_runs, reporting_snapshot, predictions FROM anon")
            cur.execute("REVOKE INSERT ON reporting_snapshot FROM authenticated")
            cur.execute("REVOKE SELECT ON predictions FROM authenticated")
            cur.execute("DROP POLICY IF EXISTS wide_open ON reporting_runs")
            conn.commit()
            migrate()  # the schema files restore the designed policy
            assert security.posture(SCHEMA)["ok"], (sql, security.posture(SCHEMA)["problems"])


def test_the_live_public_schema_lets_the_api_roles_create_nothing(stats_db):
    """Read-only look at production: the website's roles may not create objects in `public`."""
    with stats_db.get_connection() as conn, conn.cursor() as cur:
        for role in ("anon", "authenticated"):
            cur.execute("SELECT has_schema_privilege(%s, 'public', 'CREATE')", (role,))
            assert cur.fetchone()[0] is False, role
