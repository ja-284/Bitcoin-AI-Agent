"""
The database backup end to end (agent/database/backup.py), on SYNTHETIC rows in two scratch schemas that the test
creates and drops. The live tables are never read or written here.

    BITCOIN_AGENT_DB_TESTS=1 python -m pytest tests/integration/test_backup_restore.py -q

What is proven:
  - a backup of a populated schema, encrypted to a throwaway key, checks and verifies against its manifest, and its
    copy is byte-identical;
  - restored into a schema freshly built by agent.migrate, every table hashes exactly as before, and the sequences
    continue where they stopped;
  - a restore into a schema that already holds rows is refused, and a damaged backup rolls back leaving it empty.
"""

import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import agent.reporting.incidents  # noqa: E402,F401  (bound at collection, as in test_db_idempotency)
from tests.integration.test_db_idempotency import _direction_row, _prediction

pytestmark = [
    pytest.mark.skipif(os.getenv("BITCOIN_AGENT_DB_TESTS") != "1", reason="needs a database; set BITCOIN_AGENT_DB_TESTS=1"),
    # PAUSED 2026-10-21 by the user: no more GPG commands while the backup work is paused (docs/ops/BACKUP.md). These
    # tests generate a throwaway GPG key, so they no longer run with the weekly integration suite; opt in explicitly.
    pytest.mark.skipif(os.getenv("BITCOIN_AGENT_BACKUP_TESTS") != "1",
                       reason="backup work paused by the user (2026-10-21); set BITCOIN_AGENT_BACKUP_TESTS=1 to run"),
]

SRC, DST = "backup_src_test", "backup_dst_test"
HOUR = timedelta(hours=1)


def _scoped(base_url: str, schema: str) -> str:
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}options=-c%20search_path%3D{schema}"


@pytest.fixture
def schemas(monkeypatch):
    import psycopg

    import agent.database.db as db
    import agent.direction_shadow.db as ddb
    import agent.shadow.db as sdb
    from agent.migrate import migrate

    base_url = os.getenv("DATABASE_URL")
    assert base_url, "DATABASE_URL must be set"
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        for s in (SRC, DST):
            cur.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE")
            cur.execute(f"CREATE SCHEMA {s}")
        conn.commit()
    for s in (SRC, DST):
        monkeypatch.setattr(db, "DATABASE_URL", _scoped(base_url, s))
        with db.get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT current_schema()")
            assert cur.fetchone()[0] == s, "search_path option not honoured -- refusing to touch the database"
        migrate()
    # synthetic rows in SRC only: the record, its outcomes, both shadow tracks with an outcome each
    monkeypatch.setattr(db, "DATABASE_URL", _scoped(base_url, SRC))
    t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
    ids = [db.save_prediction(_prediction(t0 + i * HOUR)) for i in range(3)]
    db.save_outcome(ids[0], 1, 101.0, 0.01)
    db.save_outcome_unavailable(ids[1], 1)
    shadow = {"as_of": t0, "cutoff_at": t0 + HOUR, "fetched_at": t0 + HOUR + timedelta(minutes=12), "model_version": "move_size_1h_v1",
              "pipeline_version": "0.2.0", "code_commit": None, "price_source": "binance", "reference_close": 100.0,
              "live_close_match": None, "status": "ok", "status_reason": None, "features": {"rv_24": 0.01}, "p_raw": 0.5,
              "p_calibrated": 0.55, "threshold": 0.0025, "horizon_hours": 1}
    sid = sdb.save_shadow(shadow)
    sdb.save_shadow_outcome(sid, 100.3, 0.003, True, "ok", t0 + 3 * HOUR)
    did = ddb.save_row(_direction_row(t0))
    ddb.save_outcome(did, 100.5, 0.005, True, "ok", t0 + 3 * HOUR)
    yield {"src": _scoped(base_url, SRC), "dst": _scoped(base_url, DST)}
    with psycopg.connect(base_url) as conn, conn.cursor() as cur:
        for s in (SRC, DST):
            cur.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE")
        conn.commit()


@pytest.fixture(scope="module")
def throwaway_key():
    """A passphrase-less key in a temporary keyring (short path: gpg-agent's socket path has a length limit)."""
    from agent.database import backup as b

    try:
        gpg = b.gpg_binary()
    except b.BackupError:
        pytest.skip("GnuPG is not installed")
    home = Path(tempfile.mkdtemp(prefix="g"))
    gnupghome = ("/" + home.drive[0].lower() + home.as_posix()[2:]) if os.name == "nt" else str(home)
    env = {**os.environ, "GNUPGHOME": gnupghome, "PATH": str(Path(gpg).parent) + os.pathsep + os.environ.get("PATH", "")}
    subprocess.run([gpg, "--batch", "--passphrase", "", "--pinentry-mode", "loopback", "--quick-generate-key",
                    "backup test <test@example.invalid>", "default", "default", "never"], check=True, capture_output=True, env=env)
    out = subprocess.run([gpg, "--batch", "--with-colons", "--list-keys"], check=True, capture_output=True, text=True, env=env).stdout
    fpr = next(line.split(":")[9] for line in out.splitlines() if line.startswith("fpr:"))
    yield gpg, env, fpr
    subprocess.run([str(Path(gpg).with_name("gpgconf.exe" if os.name == "nt" else "gpgconf")), "--kill", "gpg-agent"], env=env)
    shutil.rmtree(home, ignore_errors=True)


def test_a_backup_is_encrypted_checked_verified_and_restored_exactly(schemas, throwaway_key, tmp_path):
    import psycopg

    from agent.database import backup as b

    gpg, env, fpr = throwaway_key
    with psycopg.connect(schemas["src"]) as conn:
        path = b.create(conn, fpr, tmp_path / "local", [tmp_path / "offsite"], gpg, env, schema=SRC)
    m = b.manifest_for(path)
    assert m["tables"]["predictions"]["rows"] == 3 and m["tables"]["prediction_outcomes"]["rows"] == 2
    assert m["tables"]["shadow_direction"]["rows"] == 1 and m["tables"]["shadow_move_size"]["rows"] == 1
    assert b"SELL" not in path.read_bytes() and b"move_size_1h_v1" not in path.read_bytes()  # encrypted
    copy = tmp_path / "offsite" / path.name
    assert copy.read_bytes() == path.read_bytes()
    assert b.check(path, gpg, env) == [] and b.check(copy, gpg, env) == []
    assert b.verify(path, gpg, env) == []

    backup = b.unpack(b.decrypt(path, gpg, env))
    with psycopg.connect(schemas["dst"]) as conn:
        loaded = b.restore(conn, backup, schema=DST)
    assert loaded["predictions"] == 3 and loaded["shadow_direction"] == 1
    with psycopg.connect(schemas["src"]) as s, psycopg.connect(schemas["dst"]) as d:
        before, after = b.take_snapshot(s, SRC), b.take_snapshot(d, DST)
    for t in before["tables"]:
        if t not in b.COMPARED_NOT_LOADED:
            assert b.rows_hash(after["data"][t]) == b.rows_hash(before["data"][t]), t
    assert after["sequences"] == before["sequences"]


def test_a_restore_never_touches_a_schema_that_holds_rows(schemas, throwaway_key, tmp_path):
    import psycopg

    from agent.database import backup as b

    gpg, env, fpr = throwaway_key
    with psycopg.connect(schemas["src"]) as conn:
        path = b.create(conn, fpr, tmp_path, [], gpg, env, schema=SRC)
    backup = b.unpack(b.decrypt(path, gpg, env))
    with psycopg.connect(schemas["src"]) as conn:  # the populated source stands in for any database with a record
        with pytest.raises(b.BackupError, match="not empty"):
            b.restore(conn, backup, schema=SRC)


@pytest.mark.parametrize("damage", ["a referenced row lost (the database refuses it)",
                                    "a value changed (the re-hash catches it)"])
def test_a_damaged_backup_rolls_back_and_leaves_the_target_empty(schemas, throwaway_key, tmp_path, damage):
    import psycopg

    from agent.database import backup as b

    gpg, env, fpr = throwaway_key
    with psycopg.connect(schemas["src"]) as conn:
        path = b.create(conn, fpr, tmp_path, [], gpg, env, schema=SRC)
    backup = b.unpack(b.decrypt(path, gpg, env))
    rows = [r for r in backup["data"]["predictions"].split(b"\n") if r]
    if damage.startswith("a referenced row"):
        rows = [r for r in rows if not r.startswith(b"1\t")]  # prediction 1 has an outcome pointing at it
    else:
        rows[-1] = rows[-1].replace(b"HOLD", b"SELL")
    backup["data"]["predictions"] = b"\n".join(rows) + b"\n"
    with psycopg.connect(schemas["dst"]) as conn:
        with pytest.raises(b.BackupError, match="rolled back"):
            b.restore(conn, backup, schema=DST)
    with psycopg.connect(schemas["dst"]) as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {DST}.predictions")
        assert cur.fetchone()[0] == 0
