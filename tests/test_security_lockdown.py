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
    Path("agent/reporting/schema.sql"),
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


def test_the_only_read_surface_is_two_cache_tables_for_signed_in_viewers():
    """
    The one deliberate opening (2026-09-27): the private stats read model, SELECT only, for `authenticated`
    only -- never `anon`. Changing any of this is a reviewable security decision, not a convenience.
    """
    assert security.VIEWER_READ_TABLES == ("reporting_snapshot", "reporting_runs")
    assert (security.VIEWER_ROLE, security.VIEWER_PRIVILEGE) == ("authenticated", "SELECT")
    assert security.VIEWER_CONDITION == "auth.jwt->'app_metadata'->>'reporting_viewer'='true'"
    assert not set(security.VIEWER_READ_TABLES) & {"predictions", "prediction_outcomes", "shadow_move_size",
                                                     "shadow_run_errors", "backend_state", "schema_meta"}


def test_the_reporting_schema_file_opens_exactly_the_designed_surface():
    """Static: the policy the file creates is the viewer claim, for `authenticated`, SELECT, and nothing else."""
    import re

    sql = Path("agent/reporting/schema.sql").read_text(encoding="utf-8")
    policies = re.findall(r"CREATE POLICY (\w+) ON %I FOR (\w+) TO (\w+)\s+USING \((.*?)\)\$p\$", sql, flags=re.S)
    assert len(policies) == 1, policies
    name, command, role, condition = policies[0]
    assert (command, role) == ("SELECT", "authenticated")
    assert security._normalised(condition) == security.VIEWER_CONDITION
    grants = re.findall(r"GRANT (.+?) ON TABLE %I TO ([\w, ]+)'", sql)  # the WHOLE grantee list, not its first name
    assert grants == [("SELECT", "authenticated")], grants
    code = re.sub(r"--[^\n]*", "", sql)  # the comments explain user_metadata; the SQL must never use it
    assert "TO anon" not in code and "user_metadata" not in code and "app_metadata" in code
    assert re.findall(r"ARRAY\['(\w+)', '(\w+)'\]", sql)[0] == security.VIEWER_READ_TABLES


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


QUAL = "(((auth.jwt() -> 'app_metadata'::text) ->> 'reporting_viewer'::text) = 'true'::text)"


def _viewer(**kw):
    pol = {"name": "stats_viewer_read", "roles": ["authenticated"], "command": "SELECT",
           "permissive": "PERMISSIVE", "qual": QUAL, "with_check": None}
    pol.update(kw)
    return pol


def test_the_viewer_tables_pass_exactly_as_designed():
    tables = {t: _t(grants={"anon": [], "authenticated": ["SELECT"]}, policies=[_viewer()])
              for t in security.VIEWER_READ_TABLES}
    tables["predictions"] = _t()
    assert security.judge(tables) == []


def test_anon_may_never_read_the_viewer_tables():
    problems = security.judge({"reporting_runs": _t(grants={"anon": ["SELECT"]}, policies=[_viewer()])})
    assert problems == ["reporting_runs: `anon` holds SELECT"]


def test_a_viewer_may_never_write_and_no_other_table_opens():
    problems = security.judge({"reporting_snapshot": _t(grants={"authenticated": ["SELECT", "INSERT", "UPDATE"]}),
                               "backend_state": _t(grants={"authenticated": ["SELECT"]})})
    assert "reporting_snapshot: `authenticated` holds INSERT, UPDATE" in problems
    assert "backend_state: `authenticated` holds SELECT" in problems


@pytest.mark.parametrize("change, fragment", [
    ({"qual": "true"}, "lets through more than the viewer claim"),
    ({"qual": "(COALESCE(((auth.jwt() -> 'app_metadata'::text) ->> 'reporting_viewer'::text), 'true'::text) = 'true'::text)"},
     "lets through more than the viewer claim"),
    ({"qual": "(((auth.jwt() -> 'user_metadata'::text) ->> 'reporting_viewer'::text) = 'true'::text)"},
     "lets through more than the viewer claim"),
    ({"qual": QUAL[:-1] + " OR true)"}, "lets through more than the viewer claim"),
    ({"qual": None}, "lets through more than the viewer claim"),
    ({"roles": ["anon"]}, "only `authenticated` viewers"),
    ({"roles": ["authenticated", "anon"]}, "only `authenticated` viewers"),
    ({"roles": ["public"]}, "only `authenticated` viewers"),
    ({"command": "ALL"}, "allows ALL, only SELECT"),
    ({"command": "UPDATE", "with_check": "true"}, "allows UPDATE, only SELECT"),
    ({"permissive": "RESTRICTIVE"}, "is not a plain read policy"),
    ({"with_check": "true"}, "is not a plain read policy"),
])
def test_any_widened_viewer_policy_is_reported(change, fragment):
    (problem,) = security.judge({"reporting_snapshot": _t(grants={"authenticated": ["SELECT"]}, policies=[_viewer(**change)])})
    assert problem.startswith("reporting_snapshot: policy `stats_viewer_read` ") and fragment in problem, problem


def test_posture_reads_in_a_constant_number_of_queries(monkeypatch):
    """The first version made ~90 round trips (5 s); it must not scale with tables x roles x privileges."""
    queries = []

    class Cur:
        def __init__(self):
            self.result = []

        def execute(self, sql, params=None):
            queries.append(sql)
            if any(k in sql for k in ("relkind IN ('v', 'm')", "pg_proc", "pg_default_acl", "NOT c.relrowsecurity")):
                self.result = []  # views, functions, default grants, notes: none in this fake database
            elif "has_table_privilege" in sql:
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
    assert len(queries) == 7  # tables, policies, table list, views, functions, default grants, notes
    assert result["ok"] and set(result["tables"]) == {"a", "b", "c"}
    assert result["api_roles_present"] == ["anon", "authenticated"]


# ---------------------------------------------------------------- views, functions, default privileges
def test_a_view_the_api_can_read_is_reported_because_it_bypasses_rls():
    """A view runs with its owner's rights: the tables' RLS does not protect what it selects."""
    problems = security.judge_objects({"latest": {"api_privileges": {"anon": ["SELECT"]}, "security_invoker": False}}, [], [])
    assert len(problems) == 1 and "view latest: `anon` holds SELECT" in problems[0] and "RLS" in problems[0]


def test_a_view_granted_nothing_is_fine():
    assert security.judge_objects({"latest": {"api_privileges": {"anon": [], "authenticated": []},
                                              "security_invoker": False}}, [], []) == []


def test_no_view_is_ever_part_of_the_read_surface():
    """Even a security_invoker view named like a viewer table is reported: the surface is two tables, under RLS."""
    for name in ("latest", "reporting_runs"):
        v = {name: {"api_privileges": {"authenticated": ["SELECT"]}, "security_invoker": True}}
        (problem,) = security.judge_objects(v, [], [])
        assert f"view {name}: `authenticated` holds SELECT" in problem


def test_a_callable_function_is_reported_and_security_definer_is_named():
    fns = [{"name": "latest_state", "args": "", "security_definer": True, "callable_by": ["anon"]}]
    (problem,) = security.judge_objects({}, fns, [])
    assert "latest_state() is callable by `anon` at /rest/v1/rpc" in problem and "SECURITY DEFINER" in problem


def test_standing_default_grants_are_reported_per_object_kind_and_role():
    grants = [("r", "anon", "SELECT"), ("r", "anon", "INSERT"), ("f", "authenticated", "EXECUTE")]
    problems = security.judge_objects({}, [], grants)
    assert len(problems) == 2
    assert any("NEW table or view" in p and "INSERT, SELECT to `anon`" in p for p in problems)
    assert any("NEW function" in p and "EXECUTE to `authenticated`" in p for p in problems)


def test_the_schema_file_removes_the_default_grants_for_every_object_kind():
    """Static: the root-cause block must cover tables (and so views), sequences and functions, per API role."""
    sql = Path("agent/database/schema.sql").read_text(encoding="utf-8")
    block = sql[sql.index("The root cause, closed as well"):]
    for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        assert f"ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON {kind} FROM %I" in block, kind
    assert "current_schema()" in block and "ARRAY['anon', 'authenticated']" in block
