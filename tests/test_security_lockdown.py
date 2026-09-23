"""
The public-API lockdown (2026-09-23). No database needed.

Supabase gives the `anon` and `authenticated` API roles full access to every new table in
`public` unless Row Level Security is on and their privileges are revoked. Every schema file
must therefore lock down every table it creates. These tests check the real files, and then
prove the checker itself fails when a lockdown is removed -- a checker that only ever says
"all covered" would prove nothing.
"""

from pathlib import Path

import pytest

from agent.database import security

SCHEMA_FILES = [
    Path("agent/database/schema.sql"),
    Path("agent/shadow/schema.sql"),
    Path("agent/api/schema.sql"),
]


def _all_schema_files() -> list[Path]:
    """Every schema file in the package -- so a NEW one cannot slip past this test unlisted."""
    return sorted(Path("agent").rglob("*.sql"))


def test_every_schema_file_is_listed_here():
    assert sorted(SCHEMA_FILES) == _all_schema_files(), (
        "a schema file exists that this test does not check -- add it to SCHEMA_FILES")


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: str(p))
def test_every_table_a_schema_file_creates_is_locked_down(path):
    sql = path.read_text(encoding="utf-8")
    assert security._created_tables(sql), f"{path} creates no tables -- the check would be vacuous"
    assert security.unprotected_tables_in_schema(sql) == set()


def test_the_checker_catches_a_table_dropped_from_the_lockdown():
    """Perturbation: remove one table name from the lockdown array and it must be reported."""
    sql = Path("agent/database/schema.sql").read_text(encoding="utf-8")
    broken = sql.replace("ARRAY['predictions', 'prediction_outcomes', 'schema_meta']",
                         "ARRAY['prediction_outcomes', 'schema_meta']")
    assert broken != sql, "the perturbation did not apply -- the lockdown text has changed shape"
    assert security.unprotected_tables_in_schema(broken) == {"predictions"}


def test_the_checker_catches_a_missing_revoke():
    """RLS alone is one layer; the files are supposed to apply two."""
    sql = Path("agent/shadow/schema.sql").read_text(encoding="utf-8")
    broken = sql.replace("REVOKE ALL ON TABLE", "-- revoke removed")
    assert security.unprotected_tables_in_schema(broken) == {"shadow_move_size", "shadow_run_errors"}


def test_the_checker_catches_a_missing_rls():
    sql = Path("agent/api/schema.sql").read_text(encoding="utf-8")
    broken = sql.replace("ENABLE ROW LEVEL SECURITY", "DISABLE ROW LEVEL SECURITY")
    assert security.unprotected_tables_in_schema(broken) == {"backend_state"}


def test_the_checker_catches_a_file_with_no_lockdown_at_all():
    sql = "CREATE TABLE IF NOT EXISTS new_table (id int);"
    assert security.unprotected_tables_in_schema(sql) == {"new_table"}


def test_nothing_is_intended_to_be_publicly_readable_yet():
    """
    No frontend exists, so no table may be readable through the public API. When one is built,
    changing this is the deliberate, reviewable act of opening one table -- read-only.
    """
    assert security.INTENDED_PUBLIC_READ == {}


def test_the_watchdog_runs_the_live_posture_check():
    wf = Path(".github/workflows/watchdog.yml").read_text(encoding="utf-8")
    assert "python -m agent.database.security" in wf


# ---------------------------------------------------------------- the live checker's judgement
def _fake_posture(monkeypatch, tables, policies=None, roles=("anon", "authenticated")):
    """Drive posture() with a fake cursor so its judgement can be tested without a database."""
    policies = policies or {}

    class Cur:
        def __init__(self):
            self.result = []

        def execute(self, sql, params=None):
            if "FROM pg_roles" in sql:
                self.result = [(r,) for r in roles]
            elif "FROM pg_class" in sql:
                self.result = [(name, t["rls"]) for name, t in tables.items()]
            elif "has_table_privilege" in sql:
                role, qualified, priv = params
                name = qualified.split(".", 1)[1]
                self.result = [(priv in tables[name]["grants"].get(role, ()),)]
            elif "FROM pg_policies" in sql:
                self.result = policies.get(params[1], [])
            else:
                raise AssertionError(sql)

        def fetchall(self):
            return self.result

        def fetchone(self):
            return self.result[0]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import agent.database.db as db
    monkeypatch.setattr(db, "get_connection", lambda: Conn())
    return security.posture()


def test_posture_passes_a_locked_database(monkeypatch):
    r = _fake_posture(monkeypatch, {"predictions": {"rls": True, "grants": {}}})
    assert r["ok"] and r["problems"] == []


def test_posture_flags_rls_switched_off(monkeypatch):
    r = _fake_posture(monkeypatch, {"predictions": {"rls": False, "grants": {}}})
    assert not r["ok"]
    assert r["problems"] == ["predictions: Row Level Security is OFF"]


def test_posture_flags_a_regranted_privilege(monkeypatch):
    r = _fake_posture(monkeypatch, {"predictions": {"rls": True, "grants": {"anon": ("SELECT", "INSERT")}}})
    assert not r["ok"]
    assert "predictions: `anon` holds SELECT, INSERT" in r["problems"]


def test_posture_flags_a_new_table_created_outside_the_schema_files(monkeypatch):
    """The case the schema files cannot cover: Supabase's defaults expose a dashboard-made table at once."""
    r = _fake_posture(monkeypatch, {
        "predictions": {"rls": True, "grants": {}},
        "made_in_dashboard": {"rls": False, "grants": {"anon": ("SELECT", "INSERT", "UPDATE", "DELETE")}},
    })
    assert not r["ok"]
    assert any(p.startswith("made_in_dashboard:") for p in r["problems"])


def test_posture_flags_a_policy_on_a_table_nobody_should_read(monkeypatch):
    r = _fake_posture(monkeypatch, {"predictions": {"rls": True, "grants": {}}},
                      policies={"predictions": [("allow_all", ["anon"], "ALL")]})
    assert not r["ok"]
    assert "policy `allow_all`" in r["problems"][0]


def test_posture_allows_only_select_on_an_intended_public_table(monkeypatch):
    monkeypatch.setattr(security, "INTENDED_PUBLIC_READ", {"backend_state": "SELECT"})
    ok = _fake_posture(monkeypatch, {"backend_state": {"rls": True, "grants": {"anon": ("SELECT",)}}},
                       policies={"backend_state": [("public_read", ["anon"], "SELECT")]})
    assert ok["ok"], ok["problems"]
    too_much = _fake_posture(monkeypatch, {"backend_state": {"rls": True, "grants": {"anon": ("SELECT", "UPDATE")}}})
    assert "backend_state: `anon` holds UPDATE" in too_much["problems"]
