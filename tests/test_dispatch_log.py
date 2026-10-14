"""
The dispatch-answer log (operational change 2, 2026-10-14): agent/database/dispatch_log.sql, its pg_cron schedule
(docs/ops/dispatch_responses_cron.sql) and the read-only summary (agent/database/dispatch_log.py).

What must hold without a database (the SQL itself is exercised on real Postgres in tests/integration):
  - only the diagnostic fields are kept: never a header except GitHub's request id, never a successful answer's
    body, and free text only through dispatch_redact(), redacted before it is truncated;
  - a fixed, documented retention (90 days), no sequence, nothing granted, functions closed to PUBLIC;
  - the recorder has its own cron job and never touches the dispatch job, the token or the network;
  - nothing on the hourly job's path reads or writes it, and the job role is given nothing on it.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.database import dispatch_log as dl

SQL = Path("agent/database/dispatch_log.sql").read_text(encoding="utf-8")
CRON = Path("docs/ops/dispatch_responses_cron.sql").read_text(encoding="utf-8")


def _code(sql: str) -> str:
    """The SQL without its comments."""
    return "\n".join(line.split("--")[0] for line in sql.split("\n"))


def _recorder_select() -> str:
    code = _code(SQL)
    return code[code.index("INSERT INTO dispatch_responses"):code.index("ON CONFLICT")]


def test_only_the_diagnostic_fields_are_copied_and_free_text_is_redacted_before_truncation():
    select = _recorder_select()
    assert "left(dispatch_redact(r.error_msg), 500)" in select
    assert "CASE WHEN r.status_code BETWEEN 200 AND 299 THEN NULL ELSE left(dispatch_redact(r.content), 300) END" in select
    # the only header read is GitHub's request id; the request itself (with the token) is never read
    assert re.findall(r"r\.headers\s*->>\s*'([^']+)'", select) == ["x-github-request-id"]
    assert select.count("r.headers") == 1 and "http_request_queue" not in _code(SQL)
    assert select.count("r.content") == 1 and select.count("r.error_msg") == 1


def test_retention_is_fixed_and_applied_by_the_recorder():
    code = _code(SQL)
    assert "DELETE FROM dispatch_responses WHERE responded_at < now() - interval '90 days';" in code
    assert code.count("interval '") == 1, "one retention period, stated once"


def test_the_table_is_owner_only_and_has_no_sequence():
    code = _code(SQL)
    assert "GRANT" not in code.upper().replace("REVOKE", ""), "nothing is granted to anyone"
    assert "ENABLE ROW LEVEL SECURITY" in code and "CREATE POLICY" not in code.upper()
    for fn in ("record_dispatch_responses()", "dispatch_redact(text)"):
        assert f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC;" in code, fn
        assert f"'REVOKE ALL ON FUNCTION {fn} FROM %I'" in code, fn
    assert "'REVOKE ALL ON TABLE dispatch_responses FROM %I'" in code
    assert not re.search(r"SERIAL|IDENTITY|SEQUENCE", code, re.IGNORECASE), "the job role's sequence grant must not reach it"
    assert "SECURITY DEFINER" not in code.upper()


def test_every_kept_text_column_is_bounded_by_the_database():
    code = _code(SQL)
    for column, limit in (("error_msg", 500), ("github_request_id", 100), ("detail", 300)):
        assert f"CHECK (length({column}) <= {limit})" in code, column


def test_the_recorder_has_its_own_cron_job_and_touches_nothing_else():
    code = _code(CRON)
    assert "cron.schedule('dispatch-response-log', '47 * * * *', $$select public.record_dispatch_responses()$$)" in code
    assert code.count("cron.schedule(") == 1
    for forbidden in ("github-hourly-dispatch", "http_post", "vault", "Bearer", "token", "api.github.com"):
        assert forbidden not in code, forbidden
    # and it is not in the schema files, which the integration tests also apply to scratch schemas
    for sql in Path("agent").rglob("*.sql"):
        assert "cron.schedule" not in _code(sql.read_text(encoding="utf-8")), sql


def test_nothing_on_the_hourly_path_or_in_a_workflow_uses_it_and_the_job_role_gets_nothing():
    from tests.test_migrate import HOURLY_PATH

    for path in HOURLY_PATH + [str(p) for p in Path(".github/workflows").glob("*.yml")]:
        text = Path(path).read_text(encoding="utf-8")
        assert "dispatch_responses" not in text and "dispatch_log" not in text, path
    assert "dispatch_responses" not in Path("docs/ops/least_privilege_role.sql").read_text(encoding="utf-8")
    for module in Path("agent").rglob("*.py"):
        if module.name != "dispatch_log.py":
            assert "dispatch_log" not in module.read_text(encoding="utf-8").replace("dispatch_log.sql", ""), module


# ---- the read-only summary --------------------------------------------------------------------------------
NOW = datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc)


def _row(hour: int, status=204, timed_out=False, error=None, detail=None, minute=12):
    return (datetime(2026, 10, 14, hour, minute, 0, 300000, tzinfo=timezone.utc), status, timed_out, error, f"ID{hour}", detail)


def test_a_healthy_day_has_every_slot_answered_and_accepted():
    rows = [_row(h) for h in range(10, 17)]  # 10:12 ... 16:12
    s = dl.summarise(rows, NOW, 24)
    assert (s["answers"], s["accepted_2xx"], s["by_status"], s["slots_without_an_answer"]) == (7, 7, {"204": 7}, [])
    assert s["newest"] == rows[-1][0]


def test_a_refused_a_silent_and_a_timed_out_dispatch_are_each_visible():
    rows = [_row(10), _row(11, status=401, detail='{"message":"Bad credentials"}'), _row(13, status=None, timed_out=True,
            error="Timeout of 5000 ms reached"), _row(14), _row(15), _row(16)]
    s = dl.summarise(rows, NOW, 24)
    assert s["by_status"] == {"204": 4, "401": 1, "no HTTP answer": 1}
    assert s["accepted_2xx"] == 4 and s["timed_out"] == 1 and s["with_error_text"] == 2
    assert s["slots_without_an_answer"] == [datetime(2026, 10, 14, 12, 12, tzinfo=timezone.utc)]  # the 12:12 dispatch left nothing


def test_time_before_the_log_existed_and_a_slot_still_in_flight_are_not_called_silent():
    rows = [_row(15), _row(16)]  # the log starts at 15:12
    assert dl.summarise(rows, NOW, 168)["slots_without_an_answer"] == []
    early = datetime(2026, 10, 14, 17, 15, tzinfo=timezone.utc)  # the 17:12 slot fired 3 minutes ago
    assert dl.summarise(rows, early, 168)["slots_without_an_answer"] == []
    later = datetime(2026, 10, 14, 17, 20, tzinfo=timezone.utc)
    assert dl.summarise(rows, later, 168)["slots_without_an_answer"] == [datetime(2026, 10, 14, 17, 12, tzinfo=timezone.utc)]


def test_an_empty_log_is_reported_as_empty_not_as_healthy():
    s = dl.summarise([], NOW, 168)
    assert s["answers"] == 0 and s["newest"] is None and s["slots_without_an_answer"] == []


def test_the_summary_reads_only_through_a_read_only_select():
    assert dl.SQL.strip().upper().startswith("SELECT ") and ";" not in dl.SQL
    assert "conn.read_only = True" in Path("agent/database/dispatch_log.py").read_text(encoding="utf-8")
