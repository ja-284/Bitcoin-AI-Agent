"""
The manual "Alert delivery test" workflow (.github/workflows/alert_test.yml, 2026-10-14): a one-shot, clearly labelled check
of the missed-hour signal's delivery chain. It must be impossible for it to run on its own, to touch production data or
secrets it does not need, to look like a real missed hour, or to log the heartbeat URL.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import agent.healthcheck as hc

WF = Path(".github/workflows/alert_test.yml").read_text(encoding="utf-8")
CODE = "\n".join(line for line in WF.split("\n") if not line.strip().startswith("#"))


def test_it_runs_only_when_started_by_hand():
    on = CODE[CODE.index("\non:"):CODE.index("\npermissions:")]
    assert "workflow_dispatch:" in on
    for trigger in ("schedule", "push", "pull_request", "workflow_run", "cron"):
        assert trigger not in on, trigger
    assert "permissions:\n  contents: read" in CODE


def test_it_holds_only_the_heartbeat_secret_and_follows_nothing():
    assert re.findall(r"secrets\.(\w+)", CODE) == ["HEARTBEAT_URL"]
    assert "Alert delivery test" not in Path(".github/workflows/reporting.yml").read_text(encoding="utf-8")


def test_it_sends_exactly_one_labelled_report_through_the_real_signals_path_and_never_logs_the_url():
    lines = [line.strip() for line in CODE[CODE.index("run: |"):].split("\n")[1:] if line.strip()]
    assert lines[1] == "python -m agent.healthcheck --delivery-test-body test-report.txt"
    assert lines[2] == 'curl -fsS -m 10 --retry 3 --data-binary @test-report.txt "${HEARTBEAT_URL%/}/fail" > /dev/null'
    assert CODE.count("curl") == 1 and "continue-on-error" not in CODE  # a failed send must show as a failed run
    assert "echo" not in lines[2] and "$HEARTBEAT_URL" not in lines[0].split("||")[1]  # the guard's message is static
    hourly = Path(".github/workflows/hourly.yml").read_text(encoding="utf-8")
    assert '--data-binary @missed-hours.txt "${HEARTBEAT_URL%/}/fail" > /dev/null' in hourly  # the same curl shape


def test_the_test_report_says_it_is_a_test_and_nothing_is_missing():
    msg = hc.delivery_test_message(datetime(2026, 10, 14, 20, 30, tzinfo=timezone.utc))
    assert msg.startswith("Bitcoin-AI-Agent DELIVERY TEST") and "NO hour is missing and nothing failed" in msg
    assert "2026-10-14 20:30 UTC" in msg and "http" not in msg.lower() and len(msg) < 1000


def test_the_cli_writes_the_test_report_without_touching_the_database(monkeypatch, tmp_path, capsys):
    def no_db(*a, **k):
        raise AssertionError("the delivery test must not read the database")

    monkeypatch.setattr(hc, "newest_predictions", no_db)
    monkeypatch.setattr(hc, "latest_prediction_as_of", no_db)
    body = tmp_path / "test-report.txt"
    assert hc.main(["--delivery-test-body", str(body)]) == 0
    assert body.read_text(encoding="utf-8").startswith("Bitcoin-AI-Agent DELIVERY TEST")
    assert "this is a test" in capsys.readouterr().out
