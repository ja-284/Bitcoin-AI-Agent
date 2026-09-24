"""
Test a NEW database connection string before it replaces the DATABASE_URL secret -- without the
string ever appearing on screen, in shell history, in a file or in a log.

    python -m agent.database.try_connection

It asks for the string at a hidden prompt (nothing is echoed), connects once, and prints only facts
about the role it connected as: its name, whether it is superuser or bypasses Row Level Security,
whether it can read the schema version and the record, and which of the hourly job's privileges it
holds. It writes nothing. Built for the least-privilege switch (docs/ops/open_user_actions.md item 2):
a wrong username format or password shows up here, not as a failed hourly run.
"""

import getpass
import sys
from urllib.parse import unquote, urlsplit

EXPECTED_ROLE = "bitcoin_agent"
# (table, privilege, the job needs it?) -- mirrors docs/ops/least_privilege_role.sql
CHECKS = [
    ("predictions", "SELECT", True), ("predictions", "INSERT", True),
    ("predictions", "UPDATE", False), ("predictions", "DELETE", False),
    ("prediction_outcomes", "INSERT", True), ("prediction_outcomes", "DELETE", False),
    ("shadow_move_size", "INSERT", True), ("shadow_move_size", "DELETE", False),
    ("shadow_run_errors", "INSERT", True), ("backend_state", "UPDATE", True),
    ("schema_meta", "UPDATE", False),
]


def scrub(text: str, url: str) -> str:
    """Remove the connection string and its password from any message before it is printed."""
    out = text.replace(url, "<connection string>")
    try:
        pw = urlsplit(url).password
    except ValueError:
        pw = None
    for secret in {pw, unquote(pw) if pw else None} - {None, ""}:
        out = out.replace(secret, "***")
    return out


def describe(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT current_user, r.rolsuper, r.rolbypassrls FROM pg_roles r WHERE r.rolname = current_user")
        role, superuser, bypass = cur.fetchone()
        facts = {"role": role, "superuser": bool(superuser), "bypassrls": bool(bypass)}
        try:
            cur.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'")
            row = cur.fetchone()
            facts["schema_version"] = row[0] if row else None
            cur.execute("SELECT count(*) FROM predictions")
            facts["predictions_visible"] = int(cur.fetchone()[0])
        except Exception as exc:  # noqa: BLE001 -- reported, not raised: the point is to see what fails
            conn.rollback()
            facts["read_error"] = type(exc).__name__
        facts["privileges"] = {}
        for table, priv, _ in CHECKS:
            cur.execute("SELECT has_table_privilege(current_user, %s, %s)", (table, priv))
            facts["privileges"][f"{table} {priv}"] = bool(cur.fetchone()[0])
    conn.rollback()  # nothing to keep: every statement above only read
    return facts


def judge(f: dict, expected_role: str = EXPECTED_ROLE) -> list[str]:
    problems = []
    if f["role"] != expected_role:
        problems.append(f"connected as `{f['role']}`, not `{expected_role}` -- check the username part (`{expected_role}.<project-ref>`)")
    if f["superuser"] or f["bypassrls"]:
        problems.append("this role is superuser or bypasses Row Level Security -- it is not the restricted role")
    if "read_error" in f:
        problems.append(f"could not read the schema version or the record ({f['read_error']}) -- was the whole SQL file applied?")
    elif not f.get("predictions_visible"):
        problems.append("the role sees 0 predictions -- its read policy is missing (was the whole SQL file applied?)")
    for table, priv, needed in CHECKS:
        held = f["privileges"][f"{table} {priv}"]
        if needed and not held:
            problems.append(f"missing {priv} on {table}, which the hourly job needs")
        if not needed and held:
            problems.append(f"holds {priv} on {table}, which it must not")
    return problems


def main() -> int:
    import psycopg

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    url = getpass.getpass("Paste the NEW connection string (nothing will show; press Enter): ").strip()
    if not url:
        print("Nothing entered.")
        return 2
    try:
        with psycopg.connect(url, connect_timeout=15) as conn:
            f = describe(conn)
    except Exception as exc:  # noqa: BLE001 -- any failure is reported, never with the secret in it
        print(f"Could not connect: {type(exc).__name__}: {scrub(str(exc), url).strip()}")
        return 1
    print(f"Connected as `{f['role']}` · superuser: {f['superuser']} · bypasses RLS: {f['bypassrls']} · "
          f"schema version: {f.get('schema_version')} · predictions visible: {f.get('predictions_visible')}")
    for name, held in f["privileges"].items():
        print(f"  {name:28s} {'yes' if held else 'no'}")
    problems = judge(f)
    if problems:
        print("NOT READY:")
        for p in problems:
            print("  - " + p)
        return 1
    print(f"OK: this string connects as `{EXPECTED_ROLE}` with exactly the job's rights. It can go into the DATABASE_URL secret.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
