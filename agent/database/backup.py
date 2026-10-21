"""
Encrypted, verifiable backups of the record (2026-10-20, the user's "protect live evidence" plan).

STATUS: PAUSED and INACTIVE since 2026-10-21, by the user's decision. The owner's GPG key could not be created (a keyboxd
error on Windows), and the user stopped the setup. This tool has NEVER been run on real data, nothing schedules or
imports it, and NO verified backup of the database exists (docs/ops/BACKUP.md). It is tested only on synthetic rows.

    python -m agent.database.backup create --recipient FPR --out DIR [--copy-to DIR ...]
    python -m agent.database.backup check FILE      # no secret needed: the encrypted file against its manifest
    python -m agent.database.backup verify FILE     # decrypts in memory (gpg asks YOU for the passphrase), recomputes
    python -m agent.database.backup restore FILE --target-url-env VAR   # disaster recovery into a NEW, EMPTY database

Why. Supabase's Free plan keeps no backups, and its documentation asks free projects to export their own data. The
database holds the only copy of the prospective record: the live predictions and their outcomes, the move-size shadow
record, the blind direction track and the news scores. None of it can be re-collected.

What a backup is:
- ONE read-only REPEATABLE READ transaction, so every table comes from the same instant (what pg_dump does). The data
  of every base table in `public` is taken with COPY, the mechanism pg_dump uses for data, with each table's column
  list. Also recorded: every sequence's position, and a catalog of the live constraints, indexes, triggers, policies,
  grants and functions.
- The structure itself is rebuilt from the repository's schema files (`python -m agent.migrate`) at the commit the
  manifest names. The weekly drift check proves the live database matches what those files build.
- The archive is packed in memory and piped straight into `gpg --encrypt` to the owner's PUBLIC key. No unencrypted
  byte of the record is ever written to disk, and making a backup needs no secret. Only the owner's private key and
  passphrase can open one.
- Beside it, a plaintext manifest: timestamps, row counts and SHA-256 hashes only, never a value. A table's hash is
  taken over its rows in sorted order, so a re-dump of a restored copy hashes the same however the rows come back.

Not covered (documented in docs/ops/BACKUP.md): Supabase's own schemas. That means the pg_cron jobs (their SQL is in
docs/ops), the Vault token (re-created at restore), the auth users and storage. Also the database roles' passwords:
`bitcoin_agent` is re-created with setup_role.

Nothing here writes to the production database. `restore` refuses any target table that already has rows, so it can
only fill a freshly built, empty database.
"""

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

FORMAT_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT = re.compile(r"^[0-9A-F]{40}$")
# Git for Windows ships GnuPG; on Linux (CI) it is on the PATH.
GIT_GPG = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "usr" / "bin" / "gpg.exe"
SESSION = ("SET LOCAL TimeZone = 'UTC'", "SET LOCAL DateStyle = 'ISO, YMD'", "SET LOCAL IntervalStyle = 'postgres'",
           "SET LOCAL extra_float_digits = 3", "SET LOCAL bytea_output = 'hex'")
# Filled by migrate on a fresh database, so on restore it is compared rather than loaded.
COMPARED_NOT_LOADED = {"schema_meta": ("key", "value")}


class BackupError(RuntimeError):
    pass


def gpg_binary() -> str:
    found = os.environ.get("BITCOIN_AGENT_GPG") or shutil.which("gpg") or (str(GIT_GPG) if GIT_GPG.is_file() else None)
    if not found:
        raise BackupError("GnuPG not found: install it, or set BITCOIN_AGENT_GPG to gpg's path")
    return found


def rows_hash(data: bytes) -> tuple[int, str]:
    """(row count, SHA-256 over the rows in sorted order) of COPY text output: one row per line, newlines escaped."""
    lines = [line for line in data.split(b"\n") if line]
    h = hashlib.sha256()
    for line in sorted(lines):
        h.update(line + b"\n")
    return len(lines), h.hexdigest()


# ------------------------------------------------------------------ the snapshot (read-only)
def _ident(name: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise BackupError(f"unexpected identifier {name!r}")
    return f'"{name}"'


def _copy_out(cur, schema: str, table: str, columns: list[str]) -> bytes:
    cols = ", ".join(_ident(c) for c in columns)
    buf = io.BytesIO()
    with cur.copy(f"COPY (SELECT {cols} FROM {_ident(schema)}.{_ident(table)}) TO STDOUT") as copy:
        for chunk in copy:
            buf.write(bytes(chunk))
    return buf.getvalue()


def _tables(cur, schema: str) -> dict[str, list[str]]:
    cur.execute("""SELECT c.relname, array_agg(a.attname ORDER BY a.attnum)
                   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                   WHERE n.nspname = %s AND c.relkind = 'r' GROUP BY c.relname ORDER BY c.relname""", (schema,))
    return {t: list(cols) for t, cols in cur.fetchall()}


def _catalog(cur, schema: str) -> dict:
    """The live structure as definitions, for the record: what the repository's schema files must rebuild."""
    q = {
        "columns": """SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
                             pg_get_expr(d.adbin, d.adrelid)
                      FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
                      LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                      WHERE n.nspname = %s AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped ORDER BY 1, a.attnum""",
        "constraints": """SELECT cl.relname, co.conname, pg_get_constraintdef(co.oid) FROM pg_constraint co
                          JOIN pg_class cl ON cl.oid = co.conrelid JOIN pg_namespace n ON n.oid = cl.relnamespace
                          WHERE n.nspname = %s ORDER BY 1, 2""",
        "indexes": "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = %s ORDER BY 1, 2",
        "triggers": """SELECT cl.relname, t.tgname, pg_get_triggerdef(t.oid) FROM pg_trigger t
                       JOIN pg_class cl ON cl.oid = t.tgrelid JOIN pg_namespace n ON n.oid = cl.relnamespace
                       WHERE n.nspname = %s AND NOT t.tgisinternal ORDER BY 1, 2""",
        "rls": """SELECT cl.relname, cl.relrowsecurity, cl.relforcerowsecurity FROM pg_class cl
                  JOIN pg_namespace n ON n.oid = cl.relnamespace WHERE n.nspname = %s AND cl.relkind = 'r' ORDER BY 1""",
        "policies": """SELECT tablename, policyname, roles::text, cmd, qual, with_check FROM pg_policies
                       WHERE schemaname = %s ORDER BY 1, 2""",
        "grants": """SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
                     WHERE table_schema = %s ORDER BY 1, 2, 3""",
        "functions": """SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                        WHERE n.nspname = %s AND p.prokind = 'f' ORDER BY 1""",
    }
    out = {}
    for part, sql in q.items():
        cur.execute(sql, (schema,))
        out[part] = [list(r) for r in cur.fetchall()]
    return out


def take_snapshot(conn, schema: str = "public") -> dict:
    """Every base table of `schema`, its sequences and its catalog, from ONE read-only snapshot. Writes nothing."""
    import psycopg

    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    conn.read_only = True
    try:
        with conn.cursor() as cur:
            for s in SESSION:
                cur.execute(s)
            cur.execute("SELECT now(), pg_current_snapshot()::text, current_setting('server_version')")
            taken_at, snapshot_id, server_version = cur.fetchone()
            tables = _tables(cur, schema)
            data = {t: _copy_out(cur, schema, t, cols) for t, cols in tables.items()}
            cur.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                           WHERE n.nspname = %s AND c.relkind = 'S' ORDER BY 1""", (schema,))
            sequences = {}
            for (seq,) in cur.fetchall():
                cur.execute(f"SELECT last_value, is_called FROM {_ident(schema)}.{_ident(seq)}")
                last, called = cur.fetchone()
                sequences[seq] = {"last_value": int(last), "is_called": bool(called)}
            catalog = _catalog(cur, schema)
            version = None
            if "schema_meta" in tables:
                cur.execute(f"SELECT value FROM {_ident(schema)}.schema_meta WHERE key = 'schema_version'")
                row = cur.fetchone()
                version = row[0] if row else None
    finally:
        conn.rollback()  # read-only: nothing to keep, and the connection must leave the transaction before the reset
        conn.read_only = False
        conn.isolation_level = None
    return {"taken_at": taken_at.astimezone(timezone.utc).isoformat(), "snapshot": snapshot_id,
            "server_version": server_version, "schema": schema, "schema_version": version,
            "tables": tables, "data": data, "sequences": sequences, "catalog": catalog}


# ------------------------------------------------------------------ the archive (in memory)
def _git_state() -> dict:
    def git(*args):
        r = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    return {"commit": git("rev-parse", "HEAD"), "tree_clean": git("status", "--porcelain") == ""}


def describe(snap: dict) -> dict:
    """The manifest's content part: never a value, only counts and hashes."""
    tables = {}
    for t, cols in snap["tables"].items():
        n, h = rows_hash(snap["data"][t])
        tables[t] = {"rows": n, "rows_sha256": h, "columns": cols}
    return {"format_version": FORMAT_VERSION, "taken_at": snap["taken_at"], "snapshot": snap["snapshot"],
            "server_version": snap["server_version"], "schema": snap["schema"], "schema_version": snap["schema_version"],
            "repository": _git_state(), "tables": tables, "sequences": len(snap["sequences"]),
            "catalog_sha256": hashlib.sha256(json.dumps(snap["catalog"], sort_keys=True).encode()).hexdigest()}


def pack(snap: dict, manifest: dict) -> bytes:
    """A gzip'd tar in memory: the manifest, the catalog, the sequences, and one COPY file per table."""
    mtime = int(datetime.fromisoformat(snap["taken_at"]).timestamp())
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        def add(name: str, payload: bytes):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(payload), mtime, 0o600
            tar.addfile(info, io.BytesIO(payload))
        add("manifest.json", json.dumps(manifest, indent=1, sort_keys=True).encode())
        add("catalog.json", json.dumps(snap["catalog"], indent=1, sort_keys=True, default=str).encode())
        add("sequences.json", json.dumps(snap["sequences"], indent=1, sort_keys=True).encode())
        for t in snap["tables"]:
            add(f"tables/{t}.copy", snap["data"][t])
    return gzip.compress(raw.getvalue(), mtime=mtime)


def unpack(payload: bytes) -> dict:
    files = {}
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(payload)), mode="r") as tar:
        for member in tar.getmembers():
            if not member.isfile() or member.name.startswith("/") or ".." in member.name.split("/"):
                raise BackupError(f"unexpected archive member {member.name!r}")
            files[member.name] = tar.extractfile(member).read()
    manifest = json.loads(files["manifest.json"])
    return {"manifest": manifest, "catalog": json.loads(files["catalog.json"]),
            "sequences": json.loads(files["sequences.json"]),
            "tables": {t: d["columns"] for t, d in manifest["tables"].items()},
            "data": {t: files[f"tables/{t}.copy"] for t in manifest["tables"]}}


def check_contents(backup: dict, manifest: dict) -> list[str]:
    """Problems, if any, between unpacked contents and a manifest. Prints nothing itself."""
    problems = []
    if set(backup["data"]) != set(manifest["tables"]):
        problems.append(f"tables differ: archive {sorted(backup['data'])} vs manifest {sorted(manifest['tables'])}")
    for t, d in manifest["tables"].items():
        if t in backup["data"]:
            n, h = rows_hash(backup["data"][t])
            if (n, h) != (d["rows"], d["rows_sha256"]):
                problems.append(f"{t}: {n} rows / hash {h[:12]}... vs manifest {d['rows']} / {d['rows_sha256'][:12]}...")
    cat = hashlib.sha256(json.dumps(backup["catalog"], sort_keys=True).encode()).hexdigest()
    if cat != manifest["catalog_sha256"]:
        problems.append("the catalog differs from the manifest's hash")
    return problems


# ------------------------------------------------------------------ encryption (gpg; the plaintext stays in memory)
def recipient_key_ids(fingerprint: str, gpg: str | None = None, env: dict | None = None) -> list[str]:
    """The encryption-capable key IDs of a public key in the keyring (the PKESK packet names one of these)."""
    r = subprocess.run([gpg or gpg_binary(), "--batch", "--with-colons", "--list-keys", fingerprint],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise BackupError(f"public key {fingerprint} is not in the keyring: {r.stderr.strip()[:200]}")
    return [f[4] for f in (line.split(":") for line in r.stdout.splitlines())
            if f[0] in ("pub", "sub") and "e" in f[11] and f[1] not in ("r", "e")]


def encrypt(payload: bytes, fingerprint: str, out: Path, gpg: str | None = None, env: dict | None = None) -> None:
    if not FINGERPRINT.fullmatch(fingerprint):
        raise BackupError("give the key's full 40-character fingerprint, not a name or short ID")
    recipient_key_ids(fingerprint, gpg, env)  # refuse early if the key is missing or cannot encrypt
    tmp = out.with_name(out.name + ".partial")
    r = subprocess.run([gpg or gpg_binary(), "--batch", "--yes", "--trust-model", "always", "--compress-algo", "none",
                        "--encrypt", "--recipient", fingerprint, "--output", str(tmp)], input=payload,
                       capture_output=True, env=env)
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise BackupError(f"gpg --encrypt failed: {r.stderr.decode(errors='replace').strip()[:300]}")
    tmp.replace(out)


def decrypt(path: Path, gpg: str | None = None, env: dict | None = None) -> bytes:
    """gpg's own prompt (pinentry) asks for the passphrase; it never passes through this program."""
    r = subprocess.run([gpg or gpg_binary(), "--decrypt", str(path)], capture_output=True, env=env)
    if r.returncode != 0:
        raise BackupError(f"gpg --decrypt failed: {r.stderr.decode(errors='replace').strip()[:300]}")
    return r.stdout


def packet_key_ids(path: Path, gpg: str | None = None, env: dict | None = None) -> list[str]:
    """The key IDs an encrypted file is addressed to, read from its packets without decrypting anything."""
    r = subprocess.run([gpg or gpg_binary(), "--batch", "--pinentry-mode", "cancel", "--list-only", "--list-packets",
                        str(path)], capture_output=True, text=True, env=env)
    return re.findall(r"keyid ([0-9A-F]{16})", r.stdout + r.stderr)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ create / check / verify
def _outside_repo(directory: Path) -> Path:
    d = directory.resolve()
    if d == REPO_ROOT or REPO_ROOT in d.parents:
        raise BackupError(f"{d} is inside the repository: backups never go anywhere git could pick them up")
    return d


def create(conn, fingerprint: str, out_dir: Path, copy_to: list[Path] = (), gpg: str | None = None,
           env: dict | None = None, schema: str = "public") -> Path:
    out_dir = _outside_repo(out_dir)
    copies = [_outside_repo(c) for c in copy_to]
    snap = take_snapshot(conn, schema)
    content = describe(snap)
    payload = pack(snap, content)
    stamp = datetime.fromisoformat(snap["taken_at"]).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"bitcoin-agent-db_{stamp}.tar.gz.gpg"
    encrypt(payload, fingerprint, target, gpg, env)
    manifest = {**content, "archive_sha256": hashlib.sha256(payload).hexdigest(), "encrypted_file": target.name,
                "encrypted_bytes": target.stat().st_size, "encrypted_sha256": sha256_file(target),
                "recipient_fingerprint": fingerprint, "created_at": datetime.now(tz=timezone.utc).isoformat(),
                "not_covered": ["Supabase-owned schemas: pg_cron jobs (SQL in docs/ops), the Vault token, auth users, storage",
                                "role passwords (bitcoin_agent is re-created with python -m agent.database.setup_role)"]}
    del payload, snap
    mpath = target.with_name(target.name.removesuffix(".tar.gz.gpg") + ".manifest.json")
    mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    for c in copies:
        c.mkdir(parents=True, exist_ok=True)
        for f in (target, mpath):
            shutil.copy2(f, c / f.name)
            if sha256_file(c / f.name) != sha256_file(f):
                raise BackupError(f"the copy at {c / f.name} differs from the original")
    return target


def manifest_for(path: Path) -> dict:
    mpath = path.with_name(path.name.removesuffix(".tar.gz.gpg") + ".manifest.json")
    return json.loads(mpath.read_text(encoding="utf-8"))


def check(path: Path, gpg: str | None = None, env: dict | None = None) -> list[str]:
    """Without any secret: the encrypted file is the one the manifest describes, addressed to the manifest's key."""
    m = manifest_for(path)
    problems = []
    if path.stat().st_size != m["encrypted_bytes"] or sha256_file(path) != m["encrypted_sha256"]:
        problems.append("the encrypted file's size or SHA-256 differs from its manifest")
    wanted = set(recipient_key_ids(m["recipient_fingerprint"], gpg, env))
    found = set(packet_key_ids(path, gpg, env))
    if not found or not found <= wanted:
        problems.append(f"addressed to key IDs {sorted(found)}, not to the manifest's key {m['recipient_fingerprint']}")
    return problems


def verify_payload(payload: bytes, m: dict) -> list[str]:
    """A decrypted archive against its manifest: its hash, every table's row count and hash, the catalog."""
    problems = []
    if hashlib.sha256(payload).hexdigest() != m["archive_sha256"]:
        problems.append("the decrypted archive's SHA-256 differs from the manifest")
    backup = unpack(payload)
    problems += check_contents(backup, m)
    inner = backup["manifest"]
    if {k: inner[k] for k in ("taken_at", "snapshot", "tables")} != {k: m[k] for k in ("taken_at", "snapshot", "tables")}:
        problems.append("the archive's own manifest differs from the one beside it")
    return problems


def verify(path: Path, gpg: str | None = None, env: dict | None = None) -> list[str]:
    """`check`, then decrypt in memory and `verify_payload`. Nothing decrypted is written anywhere or printed."""
    return check(path, gpg, env) + verify_payload(decrypt(path, gpg, env), manifest_for(path))


# ------------------------------------------------------------------ restore (a NEW, EMPTY database only)
def _load_order(cur, schema: str, tables: list[str]) -> list[str]:
    cur.execute("""SELECT c.relname, f.relname FROM pg_constraint co JOIN pg_class c ON c.oid = co.conrelid
                   JOIN pg_class f ON f.oid = co.confrelid JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE co.contype = 'f' AND n.nspname = %s""", (schema,))
    needs: dict[str, set] = {t: set() for t in tables}
    for child, parent in cur.fetchall():
        if child in needs and parent in needs and child != parent:
            needs[child].add(parent)
    order = []
    while needs:
        ready = sorted(t for t, deps in needs.items() if not deps - set(order))
        if not ready:
            raise BackupError(f"circular foreign keys among {sorted(needs)}")
        for t in ready:
            order.append(t)
            del needs[t]
    return order


def restore(conn, backup: dict, schema: str = "public") -> dict:
    """
    Load a backup into the structure `python -m agent.migrate` built, in ONE transaction. It refuses unless every
    target table is EMPTY (so it can never touch a database that already holds a record); `schema_meta`, which the
    migration fills, must say the same version instead. After loading, every table is dumped again and must hash
    exactly as the manifest says, or nothing is committed. Returns {table: rows loaded}.
    """
    import psycopg

    try:
        loaded = _load_and_check(conn, backup, schema)
    except psycopg.Error as exc:  # a constraint refused a row: nothing of this transaction is kept
        conn.rollback()
        raise BackupError(f"restore rolled back: the database refused the data ({type(exc).__name__}: "
                          f"{str(exc).splitlines()[0][:200]})") from None
    conn.commit()
    return loaded


def _load_and_check(conn, backup: dict, schema: str) -> dict:
    tables = backup["tables"]
    with conn.cursor() as cur:
        for s in SESSION:
            cur.execute(s)
        present = _tables(cur, schema)
        missing = sorted(set(tables) - set(present))
        if missing:
            raise BackupError(f"tables missing in the target (run python -m agent.migrate on it first): {missing}")
        for t in tables:
            cur.execute(f"SELECT count(*) FROM {_ident(schema)}.{_ident(t)}")
            if cur.fetchone()[0] and t not in COMPARED_NOT_LOADED:
                raise BackupError(f"target table {t} is not empty: restore only fills a NEW, empty database")
        loaded = {}
        for t in _load_order(cur, schema, [t for t in tables if t not in COMPARED_NOT_LOADED]):
            cols = ", ".join(_ident(c) for c in tables[t])
            with cur.copy(f"COPY {_ident(schema)}.{_ident(t)} ({cols}) FROM STDIN") as copy:
                copy.write(backup["data"][t])
            loaded[t] = rows_hash(backup["data"][t])[0]
        for seq, v in backup["sequences"].items():
            cur.execute("SELECT setval(%s::regclass, %s, %s)", (f"{_ident(schema)}.{_ident(seq)}", v["last_value"], v["is_called"]))
        problems = []
        for t, d in backup["manifest"]["tables"].items():
            if t in COMPARED_NOT_LOADED:
                keep = COMPARED_NOT_LOADED[t]
                idx = [tables[t].index(c) for c in keep]
                cur.execute(f"SELECT {', '.join(_ident(c) for c in keep)} FROM {_ident(schema)}.{_ident(t)} ORDER BY 1")
                there = sorted(tuple(map(str, r)) for r in cur.fetchall())
                wanted = sorted(tuple(line.split(b"\t")[i].decode() for i in idx)
                                for line in backup["data"][t].split(b"\n") if line)
                if there != wanted:
                    problems.append(f"{t}: the target says {there}, the backup {wanted}")
                continue
            if rows_hash(_copy_out(cur, schema, t, tables[t])) != (d["rows"], d["rows_sha256"]):
                problems.append(f"{t}: the restored rows do not hash as the manifest says")
        if problems:
            conn.rollback()
            raise BackupError("restore rolled back: " + "; ".join(problems))
    return loaded


# ------------------------------------------------------------------ command line
def _print_table_lines(manifest: dict) -> None:
    for t, d in sorted(manifest["tables"].items()):
        print(f"  {t:26} rows {d['rows']:7}  sha256 {d['rows_sha256'][:16]}...")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--recipient", required=True, help="the backup key's full fingerprint (public key in the keyring)")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--copy-to", type=Path, action="append", default=[])
    for name in ("check", "verify"):
        sub.add_parser(name).add_argument("file", type=Path)
    r = sub.add_parser("restore")
    r.add_argument("file", type=Path)
    r.add_argument("--target-url-env", required=True, help="name of an environment variable holding the NEW database's URL")
    args = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.cmd == "create":
            from agent.database.db import get_connection

            with get_connection() as conn:
                path = create(conn, args.recipient.replace(" ", "").upper(), args.out, args.copy_to)
            m = manifest_for(path)
            print(f"BACKUP CREATED {path.name}: snapshot {m['taken_at']}, {len(m['tables'])} tables, "
                  f"{m['encrypted_bytes']:,} bytes encrypted to {m['recipient_fingerprint'][-16:]}")
            _print_table_lines(m)
            for d in [args.out, *args.copy_to]:
                print(f"  stored in {d.resolve()}")
            return 0
        if args.cmd in ("check", "verify"):
            problems = (check if args.cmd == "check" else verify)(args.file)
            m = manifest_for(args.file)
            if args.cmd == "verify" and not problems:
                _print_table_lines(m)
            print(("OK: " if not problems else "FAILED: ") + f"{args.file.name} ({args.cmd})"
                  + "".join(f"\n  - {x}" for x in problems))
            return 0 if not problems else 1
        if args.cmd == "restore":
            import psycopg

            from agent.config.settings import DATABASE_URL

            target = os.environ.get(args.target_url_env)
            if not target:
                raise BackupError(f"the environment variable {args.target_url_env} is empty")
            if target == DATABASE_URL:
                raise BackupError("the target is the production DATABASE_URL: restore only fills a NEW database")
            m = manifest_for(args.file)
            payload = decrypt(args.file)
            problems = check(args.file) + verify_payload(payload, m)
            if problems:
                raise BackupError("the backup does not verify: " + "; ".join(problems))
            with psycopg.connect(target) as conn:
                loaded = restore(conn, unpack(payload))
            print(f"RESTORED {sum(loaded.values()):,} rows into {len(loaded)} tables from the snapshot of {m['taken_at']}; "
                  "every table re-hashed equal to the manifest")
            return 0
    except BackupError as exc:
        print(f"FAILED: {exc}")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
