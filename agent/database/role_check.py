"""
Does the least-privilege role hold exactly what docs/ops/least_privilege_role.sql gives it --
no more, no less? Checked on the live database, not assumed.

    python -m agent.database.role_check          # exit 1 on any difference

Run it with the OWNER connection (`postgres`) after creating the role and applying the file, and
BEFORE switching the DATABASE_URL secret: a half-applied file then shows up here, as a named
missing grant or policy, instead of as a failed hourly run. The integration test proves the file
itself; this proves the live database received all of it.

It is a detector, never a fixer, like agent.database.security.

What it cannot change, and says so: Supabase grants the `net` schema's queue and HTTP functions to
PUBLIC, which every role -- this one included -- belongs to, and the project's role cannot revoke
that (tried 2026-09-23; Postgres refused). Reported as a NOTE.
"""

import re
import sys
from pathlib import Path

ROLE = "bitcoin_agent"
SQL_FILE = Path(__file__).resolve().parents[2] / "docs" / "ops" / "least_privilege_role.sql"
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
# Roles whose membership would hand this role more than the file grants.
POWERFUL = ("postgres", "supabase_admin", "service_role", "authenticated", "anon", "pg_read_all_data",
            "pg_write_all_data", "pg_read_all_stats", "pg_monitor")


def expected_from_sql(sql: str) -> tuple[dict[str, set[str]], dict[str, set[str]], int]:
    """
    What the file grants, read from the file itself -- so this check and the proven SQL can never
    drift apart. Returns (table -> privileges, table -> columns granted UPDATE, number of policies).
    """
    tables: dict[str, set[str]] = {}
    columns: dict[str, set[str]] = {}
    body = re.sub(r"--[^\n]*", "", sql)
    for privs, cols, targets in re.findall(r"GRANT\s+([A-Z, ]+?)\s*(?:\(([^)]*)\))?\s+ON\s+([\w, ]+?)\s+TO\s+bitcoin_agent",
                                           body, flags=re.S):
        names = [t.strip() for t in targets.split(",") if t.strip()]
        if names[:1] in (["SCHEMA"], ["ALL"]) or any(n.startswith(("SCHEMA ", "ALL ")) for n in names):
            continue
        for name in names:
            if cols:
                columns.setdefault(name, set()).update(c.strip() for c in cols.split(","))
            else:
                tables.setdefault(name, set()).update(p.strip() for p in privs.split(","))
    policies = len(re.findall(r"CREATE POLICY\s+\w+\s+ON\s+\w+.*?TO bitcoin_agent", body, flags=re.S))
    return tables, columns, policies


def judge(f: dict, expected: tuple, require_login: bool = True) -> list[str]:
    """Pure: the facts read from the database against what the file grants."""
    tables, columns, n_policies = expected
    if not f["exists"]:
        return [f"role `{f['role']}` does not exist yet -- create it (docs/ops/open_user_actions.md item 2)"]
    problems = []
    for attr in ("superuser", "bypassrls", "createrole", "createdb", "replication"):
        if f["attributes"][attr]:
            problems.append(f"`{f['role']}` has {attr.upper()} -- it must not")
    if require_login and not f["attributes"]["login"]:
        problems.append(f"`{f['role']}` cannot LOGIN, so the job could not connect as it")
    for m in f["member_of"]:
        if m in POWERFUL:
            problems.append(f"`{f['role']}` is a member of `{m}` and inherits its rights")
    if f["owns"]:
        problems.append(f"`{f['role']}` owns {', '.join(f['owns'])} -- an owner can alter or drop them")
    for table, held in f["table_privileges"].items():
        want = tables.get(table, set())
        for p in sorted(set(held) - want):
            problems.append(f"{table}: holds {p}, which the file does not grant")
        for p in sorted(want - set(held)):
            problems.append(f"{table}: missing {p} -- the file grants it; was the whole file applied?")
    for table in sorted(set(tables) - set(f["table_privileges"])):
        problems.append(f"{table}: table not found in the schema")
    for table, cols in f["column_update"].items():
        want = columns.get(table, set())
        if set(cols) - want:
            problems.append(f"{table}: may UPDATE {', '.join(sorted(set(cols) - want))}, which the file does not grant")
        if want - set(cols):
            problems.append(f"{table}: missing UPDATE on {', '.join(sorted(want - set(cols)))}")
    for table in sorted(set(columns) - set(f["column_update"])):
        problems.append(f"{table}: missing UPDATE on {', '.join(sorted(columns[table]))}")
    if f["policies"] != n_policies:
        problems.append(f"{f['policies']} policies name `{f['role']}`, the file creates {n_policies}")
    for pol in f["shared_policies"]:
        problems.append(f"policy {pol} names `{f['role']}` together with other roles -- each must be scoped to it alone")
    return problems


def facts(role: str = ROLE, schema: str = "public") -> dict:
    from agent.database.db import get_connection

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication, rolcanlogin
                       FROM pg_roles WHERE rolname = %s""", (role,))
        row = cur.fetchone()
        if row is None:
            return {"role": role, "exists": False}
        attributes = dict(zip(("superuser", "bypassrls", "createrole", "createdb", "replication", "login"), row))
        cur.execute("""SELECT g.rolname FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid
                       JOIN pg_roles r ON r.oid = m.member WHERE r.rolname = %s""", (role,))
        member_of = [r[0] for r in cur.fetchall()]
        cur.execute("""SELECT n.nspname || '.' || c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE c.relowner = (SELECT oid FROM pg_roles WHERE rolname = %s)""", (role,))
        owns = [r[0] for r in cur.fetchall()]
        cur.execute("""
            SELECT c.relname, array_remove(array_agg(CASE WHEN has_table_privilege(%s, c.oid, p) THEN p END), NULL)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace CROSS JOIN unnest(%s::text[]) AS p
            WHERE n.nspname = %s AND c.relkind IN ('r', 'p') GROUP BY c.relname""", (role, list(TABLE_PRIVILEGES), schema))
        table_privileges = {t: list(p) for t, p in cur.fetchall()}
        # Column-level UPDATE where the table-level one is absent: the shape the grading grant has.
        cur.execute("""
            SELECT c.relname, array_agg(a.attname::text ORDER BY a.attname)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
              AND NOT has_table_privilege(%s, c.oid, 'UPDATE') AND has_column_privilege(%s, c.oid, a.attnum, 'UPDATE')
            GROUP BY c.relname""", (schema, role, role))
        column_update = {t: list(cols) for t, cols in cur.fetchall()}
        cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname = %s AND %s = ANY(roles)", (schema, role))
        policies = cur.fetchone()[0]
        cur.execute("""SELECT tablename || '.' || policyname FROM pg_policies
                       WHERE schemaname = %s AND %s = ANY(roles) AND cardinality(roles) > 1""", (schema, role))
        shared = [r[0] for r in cur.fetchall()]
        cur.execute("""SELECT has_table_privilege(%s, 'net.http_request_queue', 'SELECT')
                       FROM pg_namespace WHERE nspname = 'net'""", (role,))
        net = cur.fetchone()
    notes = []
    if net and net[0]:
        notes.append(f"`{role}` can read net.http_request_queue (where the hourly dispatch request waits, GitHub token "
                     "included, for seconds) through Supabase's grant to PUBLIC, which this project cannot revoke. "
                     "It is still far less than `postgres`, which can read the Vault itself.")
    return {"role": role, "exists": True, "attributes": attributes, "member_of": member_of, "owns": owns,
            "table_privileges": table_privileges, "column_update": column_update, "policies": policies,
            "shared_policies": shared, "notes": notes}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    expected = expected_from_sql(SQL_FILE.read_text(encoding="utf-8"))
    f = facts()
    problems = judge(f, expected)
    if f["exists"]:
        for table, privs in sorted(f["table_privileges"].items()):
            extra = f["column_update"].get(table)
            print(f"  {table:22s} {','.join(sorted(privs)) or '-'}{'  + UPDATE(' + ','.join(extra) + ')' if extra else ''}")
        print(f"  policies naming it: {f['policies']} (file: {expected[2]}) · login: {f['attributes']['login']} · "
              f"member of: {', '.join(f['member_of']) or 'nothing'}")
        for n in f["notes"]:
            print("  NOTE: " + n)
    if not problems:
        print(f"OK: `{ROLE}` holds exactly what docs/ops/least_privilege_role.sql grants")
        return 0
    print("DIFFERENT:" if f["exists"] else "NOT READY:")
    for p in problems:
        print("  - " + p)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
