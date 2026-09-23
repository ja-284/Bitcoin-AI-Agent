"""
Is the database locked down against the public API? Checked, not assumed.

    python -m agent.database.security      # exit 1 if any table is exposed (used by the watchdog)

Supabase publishes every table in the `public` schema through its REST and GraphQL APIs to the
`anon` and `authenticated` roles -- the roles used by anyone holding the project's anon key,
which is designed to be public -- and its default privileges give those roles full access to
every new table. On 2026-09-23 Supabase's security advisor showed that Row Level Security was
off on every table here, with full read/insert/update/delete held by both roles. The schema
files now close that with two independent layers (RLS on with no policies, and the roles'
privileges revoked), but a schema file only protects the tables it creates, at the moment it
is applied. This module catches everything else:

  * a table created later, outside the schema files (for example from the dashboard), which
    Supabase's defaults would expose immediately;
  * RLS switched off, or privileges re-granted, by hand;
  * a restored or rebuilt database that never had the lockdown applied.

It is deliberately a *detector*, not a fixer. It never changes a permission. If something is
exposed, the right response is to understand why before closing it -- which is exactly how the
original finding was handled.

Two functions:
  unprotected_tables_in_schema(sql)  static: every CREATE TABLE in a schema file must be covered
                                     by that file's lockdown block (a unit test runs this)
  posture()                          live: every table in `public` must have RLS on and grant
                                     the API roles nothing (the watchdog runs this every 3h)

Extended the same evening, after a wider audit, to the other ways Supabase opens `public` by
default -- none of them present today, all of them easy to create by accident:
  * VIEWS: a view runs with its owner's rights, so RLS on the tables beneath it does not apply;
    one SELECT grant on a view publishes whatever it selects;
  * FUNCTIONS: any non-trigger function in `public` that the API roles may execute is callable
    by anyone at /rest/v1/rpc/<name> (and a SECURITY DEFINER one runs past RLS);
  * DEFAULT PRIVILEGES: the standing rule that grants every new object to the API roles -- the
    root cause of the original exposure, now removed by the schema file and watched here.
And it NOTES, without failing, what lies outside this project's control: Supabase-owned schemas
(notably `net`, which holds each hourly dispatch request -- GitHub token included -- for a few
seconds) whose grants the project's role cannot revoke. Those are reachable only if the schema is
listed under Project Settings -> API -> Exposed schemas, a setting invisible from the database.
"""

import re
import sys

API_ROLES = ("anon", "authenticated")
PUBLIC_REACHING = {"anon", "authenticated", "public"}  # roles a policy can name that the public API acts as
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
LOCKDOWN_MARKER = "Access lockdown"

# Tables a frontend is DELIBERATELY allowed to read, each with the one privilege it may hold.
# Empty today: no frontend exists, so nothing is readable. When one is built, adding a table here
# is the reviewable, one-line record that its exposure is intended -- and anything beyond SELECT
# will still be reported.
INTENDED_PUBLIC_READ: dict[str, str] = {}


def _created_tables(sql: str) -> set[str]:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql, flags=re.IGNORECASE))


def unprotected_tables_in_schema(sql: str) -> set[str]:
    """
    Tables a schema file creates but does not lock down. A table counts as covered only if the
    file's lockdown section both names it and revokes privileges -- enabling RLS alone, or
    revoking alone, is one layer, and the file is supposed to apply two.
    """
    created = _created_tables(sql)
    if LOCKDOWN_MARKER not in sql:
        return created
    section = sql[sql.index(LOCKDOWN_MARKER):]
    if "ENABLE ROW LEVEL SECURITY" not in section or "REVOKE ALL ON TABLE" not in section:
        return created
    named = set(re.findall(r"'(\w+)'", section))  # names in the FOREACH arrays
    named |= set(re.findall(r"ALTER TABLE\s+(\w+)\s+ENABLE ROW LEVEL SECURITY", section, flags=re.IGNORECASE))
    return created - named


def judge(tables: dict[str, dict]) -> list[str]:
    """
    The judgement, separated from the reading so it can be tested without a database.
    `tables`: name -> {"rls": bool, "api_privileges": {role: [privileges]}, "policies": [...]}.
    """
    problems: list[str] = []
    for name, t in tables.items():
        allowed = INTENDED_PUBLIC_READ.get(name)
        if not t["rls"]:
            problems.append(f"{name}: Row Level Security is OFF")
        for role, granted in t["api_privileges"].items():
            extra = [p for p in granted if p != allowed]
            if extra:
                problems.append(f"{name}: `{role}` holds {', '.join(extra)}")
        for pol in t["policies"]:
            # Only a policy that reaches the public API is an exposure. A policy scoped to a
            # private backend role (the least-privilege role in docs/ops/open_user_actions.md
            # needs exactly that) is not -- and flagging it would teach people to ignore this
            # check. No TO clause means PUBLIC, which includes the API roles.
            if not set(pol["roles"]) & PUBLIC_REACHING:
                continue
            if allowed is None:
                problems.append(f"{name}: policy `{pol['name']}` opens a table no frontend is meant to read")
            elif pol["command"] not in ("SELECT",):
                problems.append(f"{name}: policy `{pol['name']}` allows {pol['command']}, only SELECT is intended")
    return problems


_DEFAULT_KINDS = {"r": "table or view", "S": "sequence", "f": "function", "T": "type", "n": "schema"}


def judge_objects(views: dict[str, dict], functions: list[dict], default_grants: list[tuple]) -> list[str]:
    """
    views: name -> {"api_privileges": {role: [privileges]}, "security_invoker": bool}
    functions: [{"name", "args", "security_definer", "callable_by": [roles]}] -- non-trigger only
    default_grants: [(object type letter, grantee role, privilege)] of the table owner's defaults
    """
    problems: list[str] = []
    for name, v in views.items():
        allowed = INTENDED_PUBLIC_READ.get(name)
        for role, granted in v["api_privileges"].items():
            if not granted:
                continue
            if allowed is None or [p for p in granted if p != allowed]:
                problems.append(f"view {name}: `{role}` holds {', '.join(granted)} -- a view runs with its owner's "
                                "rights, so RLS on the tables beneath it does not apply")
            elif not v["security_invoker"]:
                problems.append(f"view {name}: intended for public read but not security_invoker, so it bypasses RLS")
    for f in functions:
        for role in f["callable_by"]:
            problems.append(f"function {f['name']}({f['args']}) is callable by `{role}` at /rest/v1/rpc"
                            + (" and is SECURITY DEFINER, so it runs past RLS" if f["security_definer"] else ""))
    by_role: dict[tuple, list[str]] = {}
    for kind, role, priv in default_grants:
        by_role.setdefault((kind, role), []).append(priv)
    for (kind, role), privs in sorted(by_role.items()):
        problems.append(f"default privileges: every NEW {_DEFAULT_KINDS.get(kind, kind)} created here is granted "
                        f"{', '.join(sorted(privs))} to `{role}` -- apply `python -m agent.migrate`")
    return problems


def posture(schema: str = "public") -> dict:
    """
    What the public API roles can actually reach, table by table. Read-only, three queries in
    total however many tables exist -- the first version made one round trip per table, role
    and privilege (about 90, 5 seconds) and would only have grown.
    """
    from agent.database.db import get_connection

    tables: dict[str, dict] = {}
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT c.relname, c.relrowsecurity, r.rolname, p.priv,
                   has_table_privilege(r.rolname, c.oid, p.priv) AS granted
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            CROSS JOIN (SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)) r
            CROSS JOIN unnest(%s::text[]) AS p(priv)
            WHERE n.nspname = %s AND c.relkind IN ('r', 'p')
            ORDER BY c.relname, r.rolname
        """, (list(API_ROLES), list(PRIVILEGES), schema))
        rows = cur.fetchall()
        cur.execute("SELECT tablename, policyname, roles, cmd FROM pg_policies WHERE schemaname = %s", (schema,))
        policies = cur.fetchall()
        # Tables are listed even when no API role exists (a plain Postgres), so the RLS state is
        # still visible; the role/privilege rows are simply absent then.
        cur.execute("""SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = %s AND c.relkind IN ('r', 'p')""", (schema,))
        for name, rls in cur.fetchall():
            tables[name] = {"rls": bool(rls), "api_privileges": {}, "policies": []}
        cur.execute("""
            SELECT c.relname, r.rolname,
                   array_remove(array_agg(CASE WHEN has_table_privilege(r.rolname, c.oid, p.priv) THEN p.priv END), NULL),
                   coalesce(c.reloptions::text[] && ARRAY['security_invoker=true', 'security_invoker=on'], false)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            CROSS JOIN (SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)) r
            CROSS JOIN unnest(%s::text[]) AS p(priv)
            WHERE n.nspname = %s AND c.relkind IN ('v', 'm')
            GROUP BY c.relname, r.rolname, c.reloptions
        """, (list(API_ROLES), list(PRIVILEGES), schema))
        views: dict[str, dict] = {}
        for vname, role, granted, invoker in cur.fetchall():
            v = views.setdefault(vname, {"api_privileges": {}, "security_invoker": bool(invoker)})
            v["api_privileges"][role] = list(granted)
        # Trigger functions cannot be called directly (Postgres refuses), so only the rest count.
        cur.execute("""
            SELECT p.proname, pg_get_function_identity_arguments(p.oid), p.prosecdef,
                   array_remove(array_agg(CASE WHEN has_function_privilege(r.rolname, p.oid, 'EXECUTE') THEN r.rolname END), NULL)
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            CROSS JOIN (SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)) r
            WHERE n.nspname = %s AND p.prokind IN ('f', 'p')
              AND p.prorettype NOT IN ('trigger'::regtype, 'event_trigger'::regtype)
            GROUP BY p.oid, p.proname, p.prosecdef
        """, (list(API_ROLES), schema))
        functions = [{"name": n, "args": a, "security_definer": bool(d), "callable_by": list(c)}
                     for n, a, d, c in cur.fetchall() if c]
        # The standing rule for NEW objects, for whoever owns this schema's tables (the backend's
        # owner role) -- read from the catalog, so it works whichever role runs the check.
        cur.execute("""
            SELECT d.defaclobjtype, g.rolname, a.privilege_type
            FROM pg_default_acl d
            JOIN pg_namespace n ON n.oid = d.defaclnamespace
            CROSS JOIN LATERAL aclexplode(d.defaclacl) a
            JOIN pg_roles g ON g.oid = a.grantee
            WHERE n.nspname = %s AND g.rolname = ANY(%s)
              AND d.defaclrole IN (SELECT c.relowner FROM pg_class c WHERE c.relnamespace = n.oid AND c.relkind IN ('r', 'p'))
        """, (schema, list(API_ROLES)))
        default_grants = [tuple(r) for r in cur.fetchall()]
        # Outside this schema: reachable only through Supabase's "Exposed schemas" setting.
        cur.execute("""
            SELECT n.nspname, string_agg(DISTINCT c.relname, ', ' ORDER BY c.relname)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            CROSS JOIN (SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)) r
            WHERE n.nspname <> %s AND n.nspname NOT LIKE 'pg\\_%%' AND n.nspname <> 'information_schema'
              AND c.relkind IN ('r', 'p', 'v', 'm') AND NOT c.relrowsecurity
              AND has_schema_privilege(r.rolname, n.oid, 'USAGE')
              AND (has_table_privilege(r.rolname, c.oid, 'SELECT') OR has_table_privilege(r.rolname, c.oid, 'INSERT')
                   OR has_table_privilege(r.rolname, c.oid, 'UPDATE') OR has_table_privilege(r.rolname, c.oid, 'DELETE'))
            GROUP BY n.nspname ORDER BY 1
        """, (list(API_ROLES), schema))
        notes = [f"schema `{s}`: the API roles hold rights on {objs} with RLS off. Supabase owns these grants and "
                 f"this project's role cannot revoke them; they are reachable only if `{s}` is listed under "
                 "Project Settings -> API -> Exposed schemas (default: public, graphql_public)"
                 for s, objs in cur.fetchall()]
    present: list[str] = []
    for name, _rls, role, priv, granted in rows:
        held = tables[name]["api_privileges"].setdefault(role, [])
        if role not in present:
            present.append(role)
        if granted:
            held.append(priv)
    for table, pname, roles, cmd in policies:
        if table in tables:
            tables[table]["policies"].append({"name": pname, "roles": list(roles), "command": cmd})
    problems = judge(tables) + judge_objects(views, functions, default_grants)
    return {"ok": not problems, "problems": problems, "tables": tables, "views": views, "functions": functions,
            "default_grants": default_grants, "notes": notes, "api_roles_present": present}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    result = posture()
    if not result["api_roles_present"]:
        print("OK: no Supabase API roles exist in this database, so there is no public API to expose tables to")
        return 0
    for name, t in result["tables"].items():
        roles = "  ".join(f"{r}={','.join(p) or '-'}" for r, p in t["api_privileges"].items())
        print(f"  {name:22s} rls={'on ' if t['rls'] else 'OFF'}  {roles}  policies={len(t['policies'])}")
    print(f"  views: {len(result['views'])} · functions callable by the API roles: {len(result['functions'])} · "
          f"default grants to the API roles for new objects: {len(result['default_grants'])}")
    for note in result["notes"]:
        print("  NOTE (outside this project's control, not a failure): " + note)
    if result["ok"]:
        print(f"OK: all {len(result['tables'])} tables have RLS on and grant the public API roles nothing; "
              "no view, callable function or default grant exposes anything")
        return 0
    print("EXPOSED:")
    for p in result["problems"]:
        print("  - " + p)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
