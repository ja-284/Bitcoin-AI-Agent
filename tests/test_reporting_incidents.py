"""
The incident recorder (agent/reporting/incidents.py), without a database: it turns a failed GitHub run into one
incident row only after every field passes a strict check, builds its own sentence (nothing free-form from the
event is stored), sends nothing but its INSERT, and refuses anything unexpected loudly.
"""

from datetime import datetime, timezone

import pytest

from agent.reporting import incidents

GOOD = {"INCIDENT_WORKFLOW": "Hourly Bitcoin analysis", "INCIDENT_CONCLUSION": "failure", "INCIDENT_RUN_ID": "36879317592",
        "INCIDENT_RUN_ATTEMPT": "1", "INCIDENT_STARTED_AT": "2026-10-01T14:48:56Z",
        "INCIDENT_RUN_URL": "https://github.com/ja-284/Bitcoin-AI-Agent/actions/runs/36879317592", "INCIDENT_TRIGGER": "schedule"}


def test_a_failed_hourly_run_becomes_one_well_formed_incident():
    row = incidents.workflow_incident(GOOD)
    assert row["incident_key"] == "github:36879317592:1" and row["kind"] == "hourly_run_failed" and row["source"] == "workflow_event"
    assert row["occurred_at"] == datetime(2026, 10, 1, 14, 48, 56, tzinfo=timezone.utc)
    assert row["detail"] == "The 'Hourly Bitcoin analysis' run started at 2026-10-01 14:48 UTC (schedule, attempt 1) ended: failure."
    assert incidents.workflow_incident({**GOOD, "INCIDENT_WORKFLOW": "Watchdog"})["kind"] == "watchdog_failed"
    backfill = incidents.workflow_incident(GOOD, source="github_api_backfill")
    assert backfill["source"] == "github_api_backfill" and backfill["incident_key"] == row["incident_key"]  # the same run, once


@pytest.mark.parametrize("field, value", [
    ("INCIDENT_WORKFLOW", "Tests"),                                     # only the two operational workflows
    ("INCIDENT_WORKFLOW", "Hourly Bitcoin analysis\nDROP TABLE x"),
    ("INCIDENT_CONCLUSION", "success"),                                 # a success is not an incident
    ("INCIDENT_CONCLUSION", "cancelled"),                               # a superseded backup slot is not either
    ("INCIDENT_RUN_ID", "12; DROP TABLE predictions"),
    ("INCIDENT_RUN_ID", ""),
    ("INCIDENT_RUN_ATTEMPT", "1 OR 1=1"),
    ("INCIDENT_RUN_URL", "https://github.com/someone-else/repo/actions/runs/1"),
    ("INCIDENT_RUN_URL", "javascript:alert(1)"),
    ("INCIDENT_RUN_URL", "https://github.com/ja-284/Bitcoin-AI-Agent/actions/runs/1?x=<script>"),
    ("INCIDENT_STARTED_AT", "2026-10-01T14:48:56"),                     # no timezone
    ("INCIDENT_STARTED_AT", "yesterday"),
])
def test_anything_unexpected_is_refused(field, value):
    with pytest.raises(ValueError):
        incidents.workflow_incident({**GOOD, field: value})


def test_free_form_event_text_never_reaches_the_row():
    row = incidents.workflow_incident({**GOOD, "INCIDENT_TRIGGER": "<img src=x onerror=alert(1)>"})
    assert "<" not in row["detail"] and "another trigger" in row["detail"]
    assert set(row) == {"incident_key", "kind", "source", "occurred_at", "workflow", "conclusion", "run_url", "detail"}


def test_publisher_incidents_are_limited_to_their_two_kinds():
    t = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    row = incidents.publisher_incident("stats_snapshot_was_stale", t, "gap", "stale:x")
    assert row["incident_key"] == "publisher:stale:x" and row["source"] == "publisher" and row["run_url"] is None
    with pytest.raises(ValueError):
        incidents.publisher_incident("hourly_run_failed", t, "x", "y")
    with pytest.raises(ValueError):
        incidents.publisher_incident("stats_publish_failed", t.replace(tzinfo=None), "x", "y")


class _Cur:
    def __init__(self, log, rowcount):
        self.log, self.rowcount = log, rowcount

    def execute(self, sql, params=None):
        self.log.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, rowcount=1):
        self.log, self.commits, self.rowcount = [], 0, rowcount

    def cursor(self):
        return _Cur(self.log, self.rowcount)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_record_sends_only_its_insert_and_reports_duplicates(monkeypatch):
    conn = _Conn(rowcount=1)
    monkeypatch.setattr(incidents, "_incident_connection", lambda: conn)
    row = incidents.workflow_incident(GOOD)
    assert incidents.record(row) is True and conn.log == [(incidents.INSERT_SQL, row)] and conn.commits == 1
    assert "ON CONFLICT (incident_key) DO NOTHING" in " ".join(incidents.INSERT_SQL.split())
    dup = _Conn(rowcount=0)
    monkeypatch.setattr(incidents, "_incident_connection", lambda: dup)
    assert incidents.record(row) is False


def test_the_command_records_a_valid_event_and_refuses_a_malformed_one(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(incidents, "_incident_connection", lambda: conn)
    for k, v in GOOD.items():
        monkeypatch.setenv(k, v)
    assert incidents.main(["record-workflow-run"]) == 0 and len(conn.log) == 1
    monkeypatch.setenv("INCIDENT_CONCLUSION", "success")
    assert incidents.main(["record-workflow-run"]) == 1 and len(conn.log) == 1  # nothing written
