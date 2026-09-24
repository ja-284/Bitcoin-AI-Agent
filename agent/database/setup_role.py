"""
Create the least-privilege database role in one step -- for the project owner to run, on their own
computer. Nobody else, including an AI assistant, ever sees the password.

    python -m agent.database.setup_role

What it does, in order, stopping at the first problem:
  1. makes a strong random password itself (you never have to invent or type one);
  2. using your normal connection (.env, the owner role), creates `bitcoin_agent` with that password
     and applies docs/ops/least_privilege_role.sql -- the exact SQL the integration test proves --
     all in ONE transaction, so a failure leaves nothing half-made;
  3. checks the new role holds exactly what that file grants (agent.database.role_check);
  4. builds the new connection string from your current one (same host, port and database; only the
     username and password change) and logs in with it once to prove it works
     (agent.database.try_connection's checks);
  5. puts the new connection string on your CLIPBOARD, ready to paste into the GitHub secret
     DATABASE_URL. It is never printed, never written to a file, and .env is left unchanged (your
     computer keeps using the owner role for maintenance).
"""

import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ROLE = "bitcoin_agent"
SQL_FILE = Path(__file__).resolve().parents[2] / "docs" / "ops" / "least_privilege_role.sql"


def new_connection_string(current: str, password: str, role: str = ROLE) -> str:
    """The current string with only the username and password replaced (keeps a pooler's `.project-ref`)."""
    u = urlsplit(current)
    user = u.username or ""
    new_user = role + (user[user.index("."):] if "." in user else "")
    host = u.hostname or ""
    netloc = f"{quote(new_user, safe='.')}:{quote(password, safe='')}@{host}" + (f":{u.port}" if u.port else "")
    return urlunsplit((u.scheme, netloc, u.path, u.query, u.fragment))


def to_clipboard(text: str) -> bool:
    """Windows clipboard via clip.exe (text passed on stdin, never on a command line)."""
    try:
        subprocess.run(["clip"], input=text.encode("ascii"), check=True)
        return True
    except Exception:  # noqa: BLE001
        return False


def create_role(conn, password: str) -> None:
    """
    One transaction: the role, then the proven grants and policies. Refuses if the role exists.

    The PLAIN password never reaches the server. Postgres keeps the text of executed statements
    (pg_stat_statements does not normalise utility statements like CREATE ROLE, and statement logs may
    record DDL), so `PASSWORD 'plain text'` would leave the password there. Instead libpq computes the
    SCRAM-SHA-256 verifier -- the form Postgres stores anyway -- on this computer, and only that
    one-way hash is sent.
    """
    from psycopg import sql

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
        if cur.fetchone():
            raise RuntimeError(f"the role `{ROLE}` already exists -- nothing was changed. Tell Claude; it can check the existing role.")
        verifier = conn.pgconn.encrypt_password(password.encode(), ROLE.encode(), b"scram-sha-256").decode()
        if not verifier.startswith("SCRAM-SHA-256$") or password in verifier:
            raise RuntimeError("could not compute a SCRAM verifier locally -- nothing was changed")
        cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(ROLE), sql.Literal(verifier)))
        cur.execute(SQL_FILE.read_text(encoding="utf-8"))
    conn.commit()


def main() -> int:
    import psycopg

    from agent.config.settings import DATABASE_URL
    from agent.database import role_check, try_connection

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    password = secrets.token_urlsafe(32)
    new_url = new_connection_string(DATABASE_URL, password)
    scrub = lambda text: try_connection.scrub(try_connection.scrub(str(text), new_url), DATABASE_URL)  # noqa: E731

    print("1/4  Creating the role `bitcoin_agent` with a new random password ...")
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=15) as conn:
            create_role(conn, password)
    except Exception as exc:  # noqa: BLE001
        print(f"     STOPPED: {type(exc).__name__}: {scrub(exc)}")
        print("     Nothing else was changed, and GitHub still uses the old connection.")
        return 1
    print("     done.")

    print("2/4  Checking it holds exactly the proven permissions ...")
    problems = role_check.judge(role_check.facts(), role_check.expected_from_sql(role_check.SQL_FILE.read_text(encoding="utf-8")))
    if problems:
        print("     STOPPED -- the role differs from the proven file:")
        for p in problems:
            print("       - " + p)
        print("     GitHub still uses the old connection. Tell Claude what it says above.")
        return 1
    print("     done: exactly what docs/ops/least_privilege_role.sql grants.")

    print("3/4  Logging in once as `bitcoin_agent` to prove the new connection works ...")
    try:
        with psycopg.connect(new_url, connect_timeout=15) as conn:
            facts = try_connection.describe(conn)
    except Exception as exc:  # noqa: BLE001
        print(f"     STOPPED: could not log in: {type(exc).__name__}: {scrub(exc)}")
        print("     The role exists, but GitHub still uses the old connection. Tell Claude what it says above.")
        return 1
    problems = try_connection.judge(facts)
    if problems:
        print("     STOPPED:")
        for p in problems:
            print("       - " + p)
        return 1
    print(f"     done: logged in as `{facts['role']}`, sees {facts['predictions_visible']} predictions, "
          "cannot change or delete the record.")

    print("4/4  Copying the new connection string to your clipboard ...")
    if not to_clipboard(new_url):
        print("     Could not use the clipboard. Tell Claude -- do not paste anything into the chat.")
        return 1
    print("     done. It is on your clipboard now (it was not printed or saved anywhere).")
    print()
    print("LAST STEP: GitHub -> Bitcoin-AI-Agent -> Settings -> Secrets and variables -> Actions ->")
    print("           DATABASE_URL -> Update -> paste (Ctrl+V) -> Update secret. Then tell Claude \"switched\".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
