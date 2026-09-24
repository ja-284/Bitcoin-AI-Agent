"""
agent/database/try_connection.py: a new connection string is tested without ever being printed, and
the judgement names every way the connected role can differ from the restricted one. No database.
"""

import pytest

from agent.database import try_connection as tc

URL = "postgresql://bitcoin_agent.abcdefref:S3cr3t-Pa_ss@aws-0-eu.pooler.supabase.com:6543/postgres"


def _facts(**over):
    f = {"role": "bitcoin_agent", "superuser": False, "bypassrls": False, "schema_version": "4", "predictions_visible": 120,
         "privileges": {f"{t} {p}": needed for t, p, needed in tc.CHECKS}}
    f.update(over)
    return f


def test_the_restricted_role_with_exactly_the_jobs_rights_passes():
    assert tc.judge(_facts()) == []


def test_the_wrong_role_is_named_with_the_username_hint():
    (p, *_) = tc.judge(_facts(role="postgres"))
    assert "not `bitcoin_agent`" in p and "bitcoin_agent.<project-ref>" in p


def test_superuser_rls_bypass_missing_reads_and_wrong_privileges_are_reported():
    assert any("Row Level Security" in p for p in tc.judge(_facts(bypassrls=True)))
    assert any("0 predictions" in p for p in tc.judge(_facts(predictions_visible=0)))
    assert any("whole SQL file" in p for p in tc.judge(_facts(read_error="InsufficientPrivilege")))
    privs = _facts()["privileges"] | {"predictions DELETE": True, "backend_state UPDATE": False}
    problems = tc.judge(_facts(privileges=privs))
    assert "holds DELETE on predictions, which it must not" in problems
    assert "missing UPDATE on backend_state, which the hourly job needs" in problems


def test_the_secret_never_appears_in_a_printed_error():
    msg = f'connection to server failed: FATAL: password "S3cr3t-Pa_ss" rejected; dsn={URL}'
    out = tc.scrub(msg, URL)
    assert "S3cr3t-Pa_ss" not in out and URL not in out and "***" in out


def test_main_never_prints_the_string_even_when_the_connection_fails(monkeypatch, capsys):
    import psycopg

    monkeypatch.setattr(tc.getpass, "getpass", lambda prompt: URL)

    def refuse(url, **kw):
        raise psycopg.OperationalError(f"could not connect using {url} (password S3cr3t-Pa_ss)")

    monkeypatch.setattr(psycopg, "connect", refuse)
    assert tc.main() == 1
    out = capsys.readouterr().out
    assert "S3cr3t-Pa_ss" not in out and URL not in out and "Could not connect" in out


def test_the_prompt_hides_input():
    """getpass, never input(): the string must not be echoed or land in the console history."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("agent/database/try_connection.py").read_text(encoding="utf-8"))
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
             for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "getpass" in calls and "input" not in calls
