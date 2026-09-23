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
# posture() only reads; judge() decides. Testing judge() directly needs no database and no fake
# cursor, and it is where every mistake that matters would live.
def _t(rls=True, grants=None, policies=None):
    return {"rls": rls, "api_privileges": grants or {}, "policies": policies or []}


def _pol(name, roles, command):
    return {"name": name, "roles": roles, "command": command}


def test_a_locked_database_passes():
    assert security.judge({"predictions": _t()}) == []


def test_rls_switched_off_is_reported():
    assert security.judge({"predictions": _t(rls=False)}) == ["predictions: Row Level Security is OFF"]


def test_a_regranted_privilege_is_reported():
    problems = security.judge({"predictions": _t(grants={"anon": ["SELECT", "INSERT"]})})
    assert problems == ["predictions: `anon` holds SELECT, INSERT"]


def test_a_new_table_made_outside_the_schema_files_is_reported():
    """The case the schema files cannot cover: Supabase's defaults expose a dashboard-made table at once."""
    problems = security.judge({
        "predictions": _t(),
        "made_in_dashboard": _t(rls=False, grants={"anon": ["SELECT", "INSERT", "UPDATE", "DELETE"]}),
    })
    assert problems and all(p.startswith("made_in_dashboard:") for p in problems)


def test_a_policy_reaching_anon_on_a_closed_table_is_reported():
    problems = security.judge({"predictions": _t(policies=[_pol("allow_all", ["anon"], "ALL")])})
    assert problems == ["predictions: policy `allow_all` opens a table no frontend is meant to read"]


def test_a_policy_with_no_role_named_is_reported_because_that_means_public():
    assert security.judge({"predictions": _t(policies=[_pol("careless", ["public"], "SELECT")])})


def test_a_policy_scoped_to_a_private_backend_role_is_not_an_exposure():
    """
    A least-privilege backend role needs policies of its own once RLS is on. Those reach no public
    API role, so they are not an exposure -- and a detector that cried wolf about them would soon
    be ignored.
    """
    assert security.judge({"predictions": _t(policies=[_pol("backend_writes", ["bitcoin_agent"], "ALL")])}) == []


def test_an_intended_public_table_may_hold_select_and_nothing_more(monkeypatch):
    monkeypatch.setattr(security, "INTENDED_PUBLIC_READ", {"backend_state": "SELECT"})
    ok = security.judge({"backend_state": _t(grants={"anon": ["SELECT"]},
                                             policies=[_pol("public_read", ["anon"], "SELECT")])})
    assert ok == []
    too_much = security.judge({"backend_state": _t(grants={"anon": ["SELECT", "UPDATE"]},
                                                   policies=[_pol("public_write", ["anon"], "UPDATE")])})
    assert "backend_state: `anon` holds UPDATE" in too_much
    assert "backend_state: policy `public_write` allows UPDATE, only SELECT is intended" in too_much


def test_posture_reads_in_a_constant_number_of_queries(monkeypatch):
    """The first version made ~90 round trips (5 s); it must not scale with tables x roles x privileges."""
    queries = []

    class Cur:
        def __init__(self):
            self.result = []

        def execute(self, sql, params=None):
            queries.append(sql)
            if "has_table_privilege" in sql:
                self.result = [(t, True, r, p, False) for t in ("a", "b", "c") for r in ("anon", "authenticated")
                               for p in security.PRIVILEGES]
            elif "pg_policies" in sql:
                self.result = []
            else:
                self.result = [("a", True), ("b", True), ("c", True)]

        def fetchall(self):
            return self.result

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
    result = security.posture()
    assert len(queries) == 3
    assert result["ok"] and set(result["tables"]) == {"a", "b", "c"}
    assert result["api_roles_present"] == ["anon", "authenticated"]
