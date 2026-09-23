"""
Schema changes happen in one place, deliberately -- never on the hourly path. No database needed.

Before 2026-09-23 the shadow step re-applied its schema file every hour and publishing did the same,
while the documented fresh-database command built only one of the three schema files. These tests
pin the replacement: one migration entry point that applies every file atomically, and no DDL
anywhere the hourly job runs.
"""

from pathlib import Path

import pytest

from agent import migrate

# Every module the hourly workflow (.github/workflows/hourly.yml) executes, plus what they write through.
HOURLY_PATH = [
    "agent/orchestrator.py", "agent/outcome_tracker.py", "agent/healthcheck.py",
    "agent/shadow/run.py", "agent/shadow/outcomes.py", "agent/shadow/db.py",
    "agent/api/publish.py", "agent/database/db.py",
]
# Calls that would re-apply schema SQL. agent/database/db.py is allowed ONE: its init_schema(),
# which only delegates to agent.migrate and is never called on the hourly path.
DDL_CALLS = ("SCHEMA_PATH.read_text", "ensure_schema(", "ensure_table(", "init_schema(")


def test_every_schema_file_in_the_package_is_migrated():
    """A new schema file that migrate() did not know about would silently never be applied."""
    assert sorted(migrate.SCHEMA_FILES) == sorted(Path("agent").resolve().rglob("*.sql"))


def test_the_record_schema_is_applied_first():
    """It writes schema_meta, so it goes first; the others are independent of each other."""
    assert migrate.SCHEMA_FILES[0].parts[-2:] == ("database", "schema.sql")


def test_migrate_applies_every_file_in_order_in_one_transaction(monkeypatch):
    executed, commits = [], []

    class Cur:
        def execute(self, sql, *a):
            executed.append(sql)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            commits.append(len(executed))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(migrate, "get_connection", lambda: Conn())
    monkeypatch.setattr(migrate, "schema_version", lambda: "4")
    assert migrate.migrate() == "4"
    assert executed == [p.read_text(encoding="utf-8") for p in migrate.SCHEMA_FILES]
    assert commits == [len(migrate.SCHEMA_FILES)], "exactly one commit, after the last file"


def test_a_failing_file_commits_nothing(monkeypatch):
    """Atomic: a database can never be left half-migrated."""
    commits = []

    class Cur:
        def __init__(self):
            self.n = 0

        def execute(self, sql, *a):
            if "shadow_move_size" in sql and "CREATE TABLE" in sql:
                raise RuntimeError("second file failed")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            commits.append(True)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(migrate, "get_connection", lambda: Conn())
    with pytest.raises(RuntimeError, match="second file failed"):
        migrate.migrate()
    assert commits == []


@pytest.mark.parametrize("module", HOURLY_PATH)
def test_no_schema_ddl_runs_on_the_hourly_path(module):
    """
    Re-applying schema SQL every hour took exclusive locks to achieve nothing, and made a
    least-privilege database role impossible (only a table's owner may run that DDL).
    """
    source = Path(module).read_text(encoding="utf-8")
    calls = [c for c in DDL_CALLS if c in source]
    if module == "agent/database/db.py":
        # its own init_schema() definition, delegating to agent.migrate, is the only allowed mention
        assert source.count("init_schema(") == 1 and "SCHEMA_PATH.read_text" not in source
    else:
        assert calls == [], f"{module} applies schema SQL at runtime: {calls}"


def test_the_guard_message_names_the_complete_migration():
    source = Path("agent/database/db.py").read_text(encoding="utf-8")
    assert "python -m agent.migrate" in source
