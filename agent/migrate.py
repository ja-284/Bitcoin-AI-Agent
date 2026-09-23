"""
The one way to bring a database up to date: apply every schema file, in order, atomically.

    python -m agent.migrate            # apply, then print the schema version and the API posture

Why this exists (2026-09-23). Until now each module applied its own schema file at runtime: the
shadow step re-ran `agent/shadow/schema.sql` on EVERY hourly run, publishing re-ran
`agent/api/schema.sql` on every publish, and the documented "fresh database" command
(`init_schema()`) applied only `agent/database/schema.sql` -- so a database rebuilt that way lacked
the shadow tables and `backend_state` until the job happened to create them. Three problems:

  * **reproducibility** -- the documented command did not build the whole schema;
  * **needless hourly DDL** -- `ALTER TABLE`, trigger re-creation and permission changes, each
    taking a brief exclusive lock, every hour, to achieve nothing;
  * **least privilege was impossible** -- only a table's owner may run that DDL, so the hourly job
    could never connect as anything smaller than the owner.

Now schema changes happen here, deliberately, and runtime code only reads and writes rows.

Order matters only in that the database file writes `schema_meta`; the files are otherwise
independent. All three run in ONE transaction: a migration either applies completely or not at
all, so a database can never be left half-migrated.

After a migration that raises SCHEMA_VERSION, deploy the code second: the running code accepts a
database AHEAD of it (agent/database/db.schema_is_compatible), never one behind it.
"""

import logging
import sys
from pathlib import Path

from agent.database.db import get_connection, schema_version

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
SCHEMA_FILES = [
    ROOT / "database" / "schema.sql",   # the record, its invariants, schema_meta
    ROOT / "shadow" / "schema.sql",     # the research shadow record and its error log
    ROOT / "api" / "schema.sql",        # the published backend-state cache
]


def migrate() -> str | None:
    """Apply every schema file in one transaction. Returns the resulting schema version."""
    with get_connection() as conn, conn.cursor() as cur:
        for path in SCHEMA_FILES:
            logger.info("applying %s", path.relative_to(ROOT.parent))
            cur.execute(path.read_text(encoding="utf-8"))
        conn.commit()
    return schema_version()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    version = migrate()
    print(f"schema version: {version}")
    from agent.database.security import posture

    p = posture()
    print("public-API posture:", "OK -- nothing exposed" if p["ok"] else "EXPOSED: " + "; ".join(p["problems"]))
    return 0 if p["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
