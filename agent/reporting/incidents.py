"""
The stats website's incident history: operational failures that leave NO trace in the record itself.

    python -m agent.reporting.incidents record-workflow-run    # in the Reporting snapshot workflow, from env vars

THIS IS A PRIVATE READ-ONLY STATISTICS INTERFACE. IT IS NOT THE FUTURE AUTOMATED-TRADING APPLICATION.

What needs recording here, and why: a missing hour, a news or fallback failure and a shadow error are already
in the record (the reporting views derive them). But a FAILED HOURLY RUN whose hour a later backup run filled,
a failed WATCHDOG run, or a stats publish that failed or went stale would vanish -- the next success looks
exactly like nothing happened. These are written to `reporting_incidents` (append-only: a trigger refuses any
update or delete), so a problem stays visible after the next hour succeeds.

Where the facts come from, and what is trusted:
- GitHub's own `workflow_run` event, passed by the Reporting snapshot workflow as environment variables (never
  interpolated into a shell line). Every field is validated against a strict pattern before anything is written:
  only the two known workflows, only failure conclusions, numeric ids, an aware ISO time, and a run URL of this
  repository. Nothing free-form from the event is stored; the `detail` sentence is built here.
- The publisher itself, for its own failures and stale periods (`publisher_incident`).

It writes nothing but `reporting_incidents`, and only INSERT ... ON CONFLICT DO NOTHING (idempotent: the same
run recorded twice is one row).
"""

import argparse
import logging
import os
import re
import sys
from datetime import datetime

from agent.database.db import get_connection
from agent.reporting import INCIDENT_CAPTURE_STARTED

logger = logging.getLogger(__name__)

TABLE = "reporting_incidents"
WORKFLOW_KINDS = {"Hourly Bitcoin analysis": "hourly_run_failed", "Watchdog": "watchdog_failed"}
FAILURE_CONCLUSIONS = ("failure", "timed_out", "startup_failure", "action_required")
TRIGGERS = ("schedule", "workflow_dispatch")
PUBLISHER_KINDS = ("stats_publish_failed", "stats_snapshot_was_stale")
SOURCES = ("workflow_event", "github_api_backfill", "publisher")
RUN_URL = re.compile(r"https://github\.com/ja-284/Bitcoin-AI-Agent/actions/runs/[0-9]{1,20}")
DIGITS = re.compile(r"[0-9]{1,20}")
CAPTURE_STARTED = INCIDENT_CAPTURE_STARTED  # earlier failed runs were backfilled from GitHub's run history (source shows it)

INSERT_SQL = """
    INSERT INTO reporting_incidents (incident_key, kind, source, occurred_at, workflow, conclusion, run_url, detail)
    VALUES (%(incident_key)s, %(kind)s, %(source)s, %(occurred_at)s, %(workflow)s, %(conclusion)s, %(run_url)s, %(detail)s)
    ON CONFLICT (incident_key) DO NOTHING
"""


def _aware(text: str) -> datetime:
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("time without a timezone")
    return t


def workflow_incident(fields: dict, source: str = "workflow_event") -> dict:
    """
    A failed GitHub run as one incident row -- or ValueError. Pure. `fields` uses the names the workflow passes:
    INCIDENT_WORKFLOW, INCIDENT_CONCLUSION, INCIDENT_RUN_ID, INCIDENT_RUN_ATTEMPT, INCIDENT_STARTED_AT,
    INCIDENT_RUN_URL, INCIDENT_TRIGGER.
    """
    name = fields.get("INCIDENT_WORKFLOW", "")
    if name not in WORKFLOW_KINDS:
        raise ValueError(f"not a workflow this records: {name[:40]!r}")
    conclusion = fields.get("INCIDENT_CONCLUSION", "")
    if conclusion not in FAILURE_CONCLUSIONS:
        raise ValueError(f"not a failure conclusion: {conclusion[:20]!r}")
    run_id, attempt = fields.get("INCIDENT_RUN_ID", ""), fields.get("INCIDENT_RUN_ATTEMPT") or "1"
    if not DIGITS.fullmatch(run_id) or not DIGITS.fullmatch(attempt):
        raise ValueError("run id and attempt must be plain numbers")
    url = fields.get("INCIDENT_RUN_URL", "")
    if not RUN_URL.fullmatch(url):
        raise ValueError("the run URL is not a run page of this repository")
    if source not in ("workflow_event", "github_api_backfill"):
        raise ValueError(f"unknown source {source!r}")
    occurred = _aware(fields.get("INCIDENT_STARTED_AT", ""))
    trigger = fields.get("INCIDENT_TRIGGER", "")
    trigger = trigger if trigger in TRIGGERS else "another trigger"
    return {"incident_key": f"github:{run_id}:{attempt}", "kind": WORKFLOW_KINDS[name], "source": source,
            "occurred_at": occurred, "workflow": name, "conclusion": conclusion, "run_url": url,
            "detail": f"The '{name}' run started at {occurred:%Y-%m-%d %H:%M} UTC ({trigger}, attempt {attempt}) ended: {conclusion}."}


def publisher_incident(kind: str, occurred_at: datetime, detail: str, key: str) -> dict:
    """The publisher's own incidents (a failed publish, a stale period). Pure."""
    if kind not in PUBLISHER_KINDS:
        raise ValueError(f"not a publisher incident: {kind!r}")
    if occurred_at.tzinfo is None:
        raise ValueError("time without a timezone")
    return {"incident_key": f"publisher:{key}", "kind": kind, "source": "publisher", "occurred_at": occurred_at,
            "workflow": None, "conclusion": None, "run_url": None, "detail": detail}


def _incident_connection():
    """This module's only connection. Everything it sends is INSERT_SQL."""
    return get_connection()


def record(row: dict) -> bool:
    """Insert one incident; False when it was already recorded. Idempotent."""
    with _incident_connection() as conn, conn.cursor() as cur:
        cur.execute(INSERT_SQL, row)
        inserted = cur.rowcount == 1
        conn.commit()
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record an operational incident for the private stats website.")
    parser.add_argument("command", choices=["record-workflow-run"])
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.command == "record-workflow-run":
        try:
            row = workflow_incident(dict(os.environ))
        except ValueError as exc:
            # A malformed event is itself worth a red run: it means the workflow passed something unexpected.
            logger.error("refusing to record this workflow run: %s", exc)
            return 1
        logger.info("%s incident %s: %s", "recorded" if record(row) else "already recorded", row["incident_key"], row["detail"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
