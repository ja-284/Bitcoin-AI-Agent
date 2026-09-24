"""
agent/database/setup_role.py -- the one-command least-privilege setup. Faked connections only: it
must never print the password, must refuse to touch an existing role, and must build the new
connection string by changing only the username and password.
"""

import pytest

from agent.database import setup_role as sr

CURRENT = "postgresql://postgres.abcdefref:0ld-Pass_word@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"


def test_only_the_username_and_password_change():
    new = sr.new_connection_string(CURRENT, "N3w_pass-word")
    assert new == "postgresql://bitcoin_agent.abcdefref:N3w_pass-word@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"


def test_a_direct_connection_gets_the_plain_role_name():
    new = sr.new_connection_string("postgresql://postgres:pw@db.abcdefref.supabase.co:5432/postgres", "x")
    assert new.startswith("postgresql://bitcoin_agent:x@db.abcdefref.supabase.co:5432/")


class _Cur:
    def __init__(self, exists=False):
        self.exists, self.sql = exists, []

    def execute(self, q, params=None):
        self.sql.append(q)

    def fetchone(self):
        return (1,) if self.exists else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _PGconn:
    def encrypt_password(self, password, user, algorithm):
        import hashlib

        assert algorithm == b"scram-sha-256"
        return ("SCRAM-SHA-256$4096:" + hashlib.sha256(password + user).hexdigest()).encode()


class _Conn:
    pgconn = _PGconn()

    def __init__(self, exists=False):
        self.cur, self.committed = _Cur(exists), False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def test_an_existing_role_is_never_touched():
    conn = _Conn(exists=True)
    with pytest.raises(RuntimeError, match="already exists"):
        sr.create_role(conn, "pw")
    assert len(conn.cur.sql) == 1 and not conn.committed  # only the existence check ran


def test_the_role_and_the_proven_sql_go_in_one_commit():
    conn = _Conn()
    sr.create_role(conn, "pw")
    assert conn.committed and len(conn.cur.sql) == 3  # check, CREATE ROLE, the proven file
    assert conn.cur.sql[2] == sr.SQL_FILE.read_text(encoding="utf-8")


def test_the_plain_password_never_reaches_the_server():
    """Only the SCRAM verifier is sent: statement statistics and logs would otherwise keep the password."""
    conn = _Conn()
    sr.create_role(conn, "Very-Secret_Plain")
    create = conn.cur.sql[1]
    assert "Very-Secret_Plain" not in repr(create) and "SCRAM-SHA-256$" in repr(create)


def test_the_password_is_never_printed_even_when_it_fails(monkeypatch, capsys):
    import psycopg

    import agent.config.settings as settings

    monkeypatch.setattr(settings, "DATABASE_URL", CURRENT)
    monkeypatch.setattr(sr.secrets, "token_urlsafe", lambda n: "G3nerated_Secret-xyz")

    def fail(url, **kw):
        raise psycopg.OperationalError(f"boom for {url} (password G3nerated_Secret-xyz / 0ld-Pass_word)")

    monkeypatch.setattr(psycopg, "connect", fail)
    assert sr.main() == 1
    out = capsys.readouterr().out
    assert "G3nerated_Secret-xyz" not in out and "0ld-Pass_word" not in out and "STOPPED" in out


def test_the_new_string_goes_to_the_clipboard_on_stdin_not_a_command_line(monkeypatch):
    seen = {}

    def fake_run(args, input=None, check=False):
        seen["args"], seen["input"] = args, input

    monkeypatch.setattr(sr.subprocess, "run", fake_run)
    assert sr.to_clipboard("postgresql://u:secret@h/db")
    assert seen["args"] == ["clip"] and b"secret" in seen["input"]
