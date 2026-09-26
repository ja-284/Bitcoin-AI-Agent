"""
The least-privilege role check (agent/database/role_check.py): its expectations come from the proven
SQL file itself, and its judgement names every way a live role can differ from that file. No database.
"""

import pytest

from agent.database import role_check as rc

EXPECTED = rc.expected_from_sql(rc.SQL_FILE.read_text(encoding="utf-8"))


def test_the_expectations_are_read_from_the_proven_file():
    tables, columns, policies = EXPECTED
    assert tables == {"predictions": {"SELECT", "INSERT"}, "prediction_outcomes": {"SELECT", "INSERT"},
                      "schema_meta": {"SELECT"}, "shadow_move_size": {"SELECT", "INSERT"},
                      "shadow_run_errors": {"SELECT", "INSERT"}, "backend_state": {"SELECT", "INSERT", "UPDATE"}}
    assert columns == {"shadow_move_size": {"outcome_status", "outcome_close", "outcome_return", "outcome_large",
                                            "outcome_checked_at"}}
    assert policies == 13


def test_a_change_to_the_file_changes_the_expectation():
    """Perturbation: the parser must follow the file, or the check would enforce a stale copy."""
    sql = rc.SQL_FILE.read_text(encoding="utf-8") + "\nGRANT DELETE ON predictions TO bitcoin_agent;\n"
    assert "DELETE" in rc.expected_from_sql(sql)[0]["predictions"]
    commented = rc.SQL_FILE.read_text(encoding="utf-8") + "\n-- GRANT DELETE ON predictions TO bitcoin_agent;\n"
    assert "DELETE" not in rc.expected_from_sql(commented)[0]["predictions"], "a comment is not a grant"


def _facts(**over):
    tables, columns, n = EXPECTED
    f = {"role": "bitcoin_agent", "exists": True,
         "attributes": {"superuser": False, "bypassrls": False, "createrole": False, "createdb": False,
                        "replication": False, "login": True},
         "member_of": [], "owns": [], "table_privileges": {t: sorted(p) for t, p in tables.items()},
         "column_update": {t: sorted(c) for t, c in columns.items()}, "policies": n, "shared_policies": [], "notes": []}
    f.update(over)
    return f


def test_a_role_exactly_as_the_file_describes_passes():
    assert rc.judge(_facts(), EXPECTED) == []


def test_a_missing_role_says_what_to_do():
    (p,) = rc.judge({"role": "bitcoin_agent", "exists": False}, EXPECTED)
    assert "does not exist" in p and "item 2" in p


@pytest.mark.parametrize("attr", ["superuser", "bypassrls", "createrole", "createdb", "replication"])
def test_a_powerful_attribute_is_reported(attr):
    f = _facts()
    f["attributes"][attr] = True
    assert any(attr.upper() in p for p in rc.judge(f, EXPECTED))


def test_a_role_that_cannot_log_in_is_reported_unless_told_otherwise():
    f = _facts()
    f["attributes"]["login"] = False
    assert any("cannot LOGIN" in p for p in rc.judge(f, EXPECTED))
    assert rc.judge(f, EXPECTED, require_login=False) == []  # the integration test's NOLOGIN probe


def test_an_extra_privilege_is_reported():
    tp = {t: list(p) for t, p in _facts()["table_privileges"].items()}
    tp["predictions"].append("DELETE")
    assert "predictions: holds DELETE, which the file does not grant" in rc.judge(_facts(table_privileges=tp), EXPECTED)


def test_a_missing_privilege_points_at_a_half_applied_file():
    tp = {t: list(p) for t, p in _facts()["table_privileges"].items()}
    tp["backend_state"].remove("UPDATE")
    assert any("backend_state: missing UPDATE" in p and "whole file" in p for p in rc.judge(_facts(table_privileges=tp), EXPECTED))


def test_column_updates_beyond_the_grading_columns_are_reported():
    cu = {"shadow_move_size": sorted(EXPECTED[1]["shadow_move_size"] | {"p_calibrated"})}
    assert any("may UPDATE p_calibrated" in p for p in rc.judge(_facts(column_update=cu), EXPECTED))
    assert any("missing UPDATE on" in p for p in rc.judge(_facts(column_update={}), EXPECTED))


def test_membership_ownership_and_policy_scope_are_reported():
    assert any("member of `postgres`" in p for p in rc.judge(_facts(member_of=["postgres"]), EXPECTED))
    assert any("owns public.predictions" in p for p in rc.judge(_facts(owns=["public.predictions"]), EXPECTED))
    assert any("12 policies" in p for p in rc.judge(_facts(policies=12), EXPECTED))
    assert any("together with other roles" in p for p in rc.judge(_facts(shared_policies=["predictions.x"]), EXPECTED))


def test_the_watchdog_requires_the_connection_itself_to_be_the_restricted_role():
    assert rc.judge_connected("bitcoin_agent") == []
    (p,) = rc.judge_connected("postgres")
    assert "`postgres`, not `bitcoin_agent`" in p and "DATABASE_URL" in p


def test_connected_mode_fails_on_the_owner_even_when_the_role_itself_is_perfect(monkeypatch, capsys):
    monkeypatch.setattr(rc, "facts", lambda *a, **k: _facts())
    monkeypatch.setattr(rc, "connected_role", lambda: "postgres")
    assert rc.main(["--connected"]) == 1 and "not `bitcoin_agent`" in capsys.readouterr().out
    monkeypatch.setattr(rc, "connected_role", lambda: "bitcoin_agent")
    assert rc.main(["--connected"]) == 0
    monkeypatch.setattr(rc, "connected_role", lambda: "postgres")
    assert rc.main([]) == 0, "without --connected the owner may run the check (the local audit)"


def test_the_watchdog_runs_the_connected_role_check():
    from pathlib import Path

    wf = Path(".github/workflows/watchdog.yml").read_text(encoding="utf-8")
    assert "python -m agent.database.role_check --connected" in wf


def test_the_database_stamps_which_role_wrote_each_prediction():
    """Static: the INSERT itself adds db_role = current_user, so no code path can claim another role."""
    import inspect

    from agent.database import db

    assert "jsonb_build_object('db_role', current_user::text)" in inspect.getsource(db.save_prediction)
