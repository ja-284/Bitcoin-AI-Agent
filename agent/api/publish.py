"""
Publish the backend's outward-facing state so a frontend can read one row.

    python -m agent.api.publish            # assemble and store
    python -m agent.api.publish --dry-run  # assemble and print, store nothing

Transport decision (docs/api/contract_v1.md): the hourly job writes the assembled contract into
a single-row table, and the frontend reads that row from Supabase. No new service to host,
monitor or secure, and it fits how everything else in this project already works. The cost is
that the snapshot is up to an hour old between runs -- which is why the state carries its own
`generated_at`, `age_hours` and `health`, so a reader can always tell how fresh it is rather
than having to assume.

Two rules this module exists to keep:

1. **It never fails the hourly job.** It runs after the live record is written and self-checked,
   and a failure here leaves the previous snapshot in place -- visibly older, because the state
   says when it was made. This is the lesson of the 2026-09-21 incident: an add-on must never be
   able to cost an hour of the record it describes.
2. **It never writes anything but this cache.** It reads the record and stores a snapshot of it.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from agent.api.state import CONTRACT_VERSION, backend_state
from agent.database.db import get_connection

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("schema.sql")  # applied by `python -m agent.migrate`, never at runtime


def publish(state: dict | None = None) -> dict:
    """
    Assemble the contract (unless one is supplied) and replace the single stored row.

    No DDL here: `backend_state` is created by `python -m agent.migrate`, like every other table.
    If it is missing, the write fails and main() says exactly what to run.
    """
    state = state if state is not None else backend_state()
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO backend_state (id, contract_version, generated_at, updated_at, state)
            VALUES (1, %s, %s, now(), %s)
            ON CONFLICT (id) DO UPDATE
               SET contract_version = EXCLUDED.contract_version,
                   generated_at     = EXCLUDED.generated_at,
                   updated_at       = now(),
                   state            = EXCLUDED.state
            """,
            (state["contract_version"], state["generated_at"], json.dumps(state, default=str)),
        )
        conn.commit()
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish the backend state for a frontend to read.")
    parser.add_argument("--dry-run", action="store_true", help="assemble and print; store nothing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    try:
        state = backend_state()
        if args.dry_run:
            print(json.dumps(state, indent=2, default=str))
            return 0
        publish(state)
        health = state.get("health", {})
        logger.info("Published contract v%s (%s); health: %s %s", CONTRACT_VERSION,
                    state["generated_at"], health.get("status"), health.get("problems") or "")
        return 0
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see rule 1 in the module docstring
        # A failure here must not fail the hourly job. The previous snapshot stays, and because
        # the state carries its own timestamp, a reader can see it has stopped being refreshed.
        logger.error("Could not publish the backend state: %s: %s", type(exc).__name__, exc)
        if type(exc).__name__ == "UndefinedTable":
            logger.error("backend_state does not exist -- apply the schema: python -m agent.migrate")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
