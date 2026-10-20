"""
The backup's own logic, without a database or GnuPG (the full round trip, scratch database -> encrypted file -> restore,
is in tests/integration/test_backup_restore.py). What must hold:
  - a table's hash does not depend on row order, and counts rows exactly;
  - an archive unpacks to exactly what was packed, and any change to a row, a table or the catalog is reported;
  - backups are never written inside the repository, and only a full key fingerprint is accepted;
  - nothing in the live system imports or runs the backup.
"""

import gzip
import io
import re
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.database import backup as b


def _snapshot() -> dict:
    return {"taken_at": datetime(2026, 10, 20, 18, tzinfo=timezone.utc).isoformat(), "snapshot": "100:100:",
            "server_version": "17.6", "schema": "public", "schema_version": "4",
            "tables": {"predictions": ["id", "as_of", "signal"], "schema_meta": ["key", "value", "updated_at"]},
            "data": {"predictions": b"2\t2026-10-01 01:00:00+00\tSELL\n1\t2026-10-01 00:00:00+00\tBUY\n",
                     "schema_meta": b"schema_version\t4\t2026-09-23 12:00:00+00\n"},
            "sequences": {"predictions_id_seq": {"last_value": 2, "is_called": True}},
            "catalog": {"constraints": [["predictions", "predictions_pkey", "PRIMARY KEY (id)"]]}}


def test_a_tables_hash_ignores_row_order_and_counts_rows():
    a = b"1\tx\n2\ty\n3\tz\n"
    shuffled = b"3\tz\n1\tx\n2\ty\n"
    assert b.rows_hash(a) == b.rows_hash(shuffled)
    assert b.rows_hash(a)[0] == 3 and b.rows_hash(b"")[0] == 0
    assert b.rows_hash(a) != b.rows_hash(b"1\tx\n2\ty\n3\tZ\n")
    assert b.rows_hash(a) != b.rows_hash(b"1\tx\n2\ty\n")  # a missing row is a different table


def test_an_archive_unpacks_to_exactly_what_was_packed():
    snap = _snapshot()
    manifest = b.describe(snap)
    unpacked = b.unpack(b.pack(snap, manifest))
    assert unpacked["data"] == snap["data"] and unpacked["sequences"] == snap["sequences"]
    assert unpacked["catalog"] == snap["catalog"] and unpacked["tables"] == snap["tables"]
    assert b.check_contents(unpacked, manifest) == []
    assert manifest["tables"]["predictions"]["rows"] == 2


def test_the_manifest_holds_counts_and_hashes_never_a_value():
    manifest = b.describe(_snapshot())
    text = repr(manifest)
    assert "SELL" not in text and "BUY" not in text and "2026-10-01" not in text
    assert all(re.fullmatch(r"[0-9a-f]{64}", t["rows_sha256"]) for t in manifest["tables"].values())


@pytest.mark.parametrize("change", ["a changed row", "a missing row", "a missing table", "a changed catalog"])
def test_every_kind_of_damage_is_reported(change):
    snap = _snapshot()
    manifest = b.describe(snap)
    damaged = b.unpack(b.pack(snap, manifest))
    if change == "a changed row":
        damaged["data"]["predictions"] = damaged["data"]["predictions"].replace(b"SELL", b"HOLD")
    elif change == "a missing row":
        damaged["data"]["predictions"] = damaged["data"]["predictions"].split(b"\n", 1)[1]
    elif change == "a missing table":
        del damaged["data"]["schema_meta"]
    else:
        damaged["catalog"]["constraints"][0][2] = "PRIMARY KEY (as_of)"
    assert b.check_contents(damaged, manifest)


def test_a_decrypted_archive_that_is_not_the_one_described_is_reported():
    snap = _snapshot()
    content = b.describe(snap)
    payload = b.pack(snap, content)
    m = {**content, "archive_sha256": "0" * 64}
    assert any("archive's SHA-256" in p for p in b.verify_payload(payload, m))


def test_an_archive_member_outside_the_archive_is_refused():
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(b.BackupError, match="unexpected archive member"):
        b.unpack(gzip.compress(raw.getvalue()))


def test_backups_are_never_written_inside_the_repository(tmp_path):
    for inside in (b.REPO_ROOT, b.REPO_ROOT / "backups", b.REPO_ROOT / "research" / "monitoring"):
        with pytest.raises(b.BackupError, match="inside the repository"):
            b._outside_repo(inside)
    assert b._outside_repo(tmp_path) == tmp_path.resolve()


@pytest.mark.parametrize("recipient", ["", "Bitcoin AI Agent backup", "94564E508FD3E290", "998606285d610a5aab74c86d6084f9c0422ea9b2"])
def test_only_a_full_upper_case_fingerprint_names_the_key(recipient, tmp_path):
    with pytest.raises(b.BackupError, match="full 40-character fingerprint"):
        b.encrypt(b"x", recipient, tmp_path / "x.gpg", gpg="gpg-is-not-reached")
    assert not list(tmp_path.iterdir())


class _FakeConn:
    """Just enough of a psycopg connection to see what the backup asks the database to do, and in which order."""

    def __init__(self, tables: dict, rows: int = 0):
        self.events, self.tables, self.rows = [], tables, rows
        self._iso, self._ro = None, False

    isolation_level = property(lambda self: self._iso,
                               lambda self, v: (self.events.append(("isolation", v)), setattr(self, "_iso", v)))
    read_only = property(lambda self: self._ro, lambda self, v: (self.events.append(("read_only", v)), setattr(self, "_ro", v)))

    def cursor(self):
        return _FakeCursor(self)

    def rollback(self):
        self.events.append(("rollback",))

    def commit(self):
        self.events.append(("commit",))


class _FakeCursor:
    def __init__(self, conn):
        self.conn, self.result = conn, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.conn.events.append(("execute", sql.split()[0] + " " + sql.split()[1]))
        if "pg_current_snapshot" in sql:
            self.result = [(datetime(2026, 10, 20, tzinfo=timezone.utc), "1:1:", "17.6")]
        elif "array_agg(a.attname" in sql:
            self.result = [(t, cols) for t, cols in self.conn.tables.items()]
        elif sql.startswith("SELECT count(*)"):
            self.result = [(self.conn.rows,)]
        else:
            self.result = []

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result

    def copy(self, sql):
        self.conn.events.append(("copy", sql.split()[0] + " " + sql.split()[-1]))
        conn = self.conn

        class _Copy:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def __iter__(self):
                return iter([b"1\tx\n"])

            def write(self, data):
                conn.events.append(("copy_in",))
        return _Copy()


def test_the_snapshot_is_one_read_only_repeatable_read_transaction_that_keeps_nothing():
    import psycopg

    conn = _FakeConn({"predictions": ["id", "signal"]})
    snap = b.take_snapshot(conn)
    first_sql = next(i for i, e in enumerate(conn.events) if e[0] == "execute")
    before = conn.events[:first_sql]
    assert ("read_only", True) in before and ("isolation", psycopg.IsolationLevel.REPEATABLE_READ) in before
    assert ("commit",) not in conn.events and ("rollback",) in conn.events
    assert conn.events[-2:] == [("read_only", False), ("isolation", None)]  # the connection is handed back as found
    assert snap["data"]["predictions"] == b"1\tx\n"


def test_a_restore_refuses_a_target_that_holds_rows_before_writing_anything():
    snap = _snapshot()
    backup = b.unpack(b.pack(snap, b.describe(snap)))
    conn = _FakeConn(snap["tables"], rows=5)
    with pytest.raises(b.BackupError, match="not empty"):
        b.restore(conn, backup)
    assert not [e for e in conn.events if e[0] in ("copy_in", "commit")]


def test_nothing_in_the_live_system_imports_or_runs_the_backup():
    root = b.REPO_ROOT
    for path in [*root.glob("agent/**/*.py"), *root.glob(".github/workflows/*.yml"), root / "run.py"]:
        if path.resolve() == Path(b.__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        assert "database.backup" not in text and "database/backup" not in text, path


def test_backup_files_are_ignored_by_git_as_a_second_line_of_defence():
    ignored = (b.REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.tar.gz.gpg" in ignored and "bitcoin-agent-db_*.manifest.json" in ignored
