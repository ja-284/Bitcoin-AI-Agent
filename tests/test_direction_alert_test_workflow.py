"""
The manual "Direction alert delivery test" workflow (.github/workflows/direction_alert_test.yml, addendum 2026-10-16): a
one-shot, labelled check of the direction track alert's delivery chain. It must be impossible for it to run on its own,
to hold any secret but the direction check's, to look like a real lost hour, or to log the URL.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import agent.direction_shadow.health as dh

WF = Path(".github/workflows/direction_alert_test.yml").read_text(encoding="utf-8")
CODE = "\n".join(line for line in WF.split("\n") if not line.strip().startswith("#"))


def test_it_runs_only_when_started_by_hand():
    on = CODE[CODE.index("\non:"):CODE.index("\npermissions:")]
    assert "workflow_dispatch:" in on
    for trigger in ("schedule", "push", "pull_request", "workflow_run", "cron"):
        assert trigger not in on, trigger
    assert "permissions:\n  contents: read" in CODE


def test_it_holds_only_the_direction_checks_secret_and_follows_nothing():
    assert re.findall(r"secrets\.(\w+)", CODE) == ["DIRECTION_HEARTBEAT_URL"]
    assert "Direction alert delivery test" not in Path(".github/workflows/reporting.yml").read_text(encoding="utf-8")


def test_it_sends_one_labelled_report_through_the_real_alerts_path_and_never_logs_the_url():
    lines = [line.strip() for line in CODE[CODE.index("run: |"):].split("\n")[1:] if line.strip()]
    assert lines[1] == "python -m agent.direction_shadow.health --delivery-test-body test-report.txt"
    assert lines[2] == 'curl -fsS -m 10 --retry 3 --data-binary @test-report.txt "${DIRECTION_HEARTBEAT_URL%/}/fail" > /dev/null'
    assert CODE.count("curl") == 1 and "continue-on-error" not in CODE
    hourly = Path(".github/workflows/hourly.yml").read_text(encoding="utf-8")
    assert '--data-binary @direction-fail.txt "${DIRECTION_HEARTBEAT_URL%/}/fail" > /dev/null' in hourly  # the same curl shape


def test_the_test_report_says_it_is_a_test_and_nothing_is_lost(tmp_path, capsys, monkeypatch):
    def no_db(*a, **k):
        raise AssertionError("the delivery test must not read the database")

    monkeypatch.setattr(dh, "read_state", no_db)
    body = tmp_path / "test-report.txt"
    assert dh.main(["--delivery-test-body", str(body)]) == 0
    text = body.read_text(encoding="utf-8")
    assert text.startswith("Bitcoin-AI-Agent DELIVERY TEST of the DIRECTION TRACK") and "NO direction hour is lost" in text
    assert "http" not in text.lower() and "this is a test" in capsys.readouterr().out
    assert "DELIVERY TEST" not in dh.fail_message(dh.assess([], [], datetime(2026, 10, 16, tzinfo=timezone.utc)))
