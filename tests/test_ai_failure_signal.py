"""
The AI-failure alarm (the user's approval, 2026-10-17, after the Anthropic key rotation). A failed AI call never fails
the hourly job (the hour is saved without a news score and/or explanation), so without this alarm an expired or invalid
key would hide behind a green heartbeat. These tests prove the report is written exactly when the newest saved hour's
news step or explanation failed, names only error TYPES, and that the workflow holds back the success ping while it
does -- so the healthchecks.io check stays down until an hour is saved with working AI calls.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import agent.healthcheck as hc

HOUR = datetime(2026, 10, 19, 5, tzinfo=timezone.utc)
CLEAN = {"news": {"items": 40}, "ai_usage": {"news": {"input_tokens": 1}, "explanation": {"input_tokens": 1}}}
SECRET_LIKE = "sk-ant-api03-THIS-MUST-NEVER-BE-REPEATED https://hc-ping.com/never"


def test_no_report_when_the_ai_calls_worked():
    assert hc.ai_failure(HOUR, CLEAN) == ""
    assert hc.ai_failure(HOUR, {}) == ""                      # no headlines at all is not a failure


def test_a_failed_news_step_is_reported_with_its_type_and_an_authentication_hint():
    r = hc.ai_failure(HOUR, {**CLEAN, "news_error": "Error code: 401 " + SECRET_LIKE, "news_error_type": "AuthenticationError"})
    assert "2026-10-19 05:00 UTC" in r and "the news step failed (AuthenticationError)" in r
    assert "ANTHROPIC_API_KEY" in r and "invalid or expired" in r
    r = hc.ai_failure(HOUR, {"news_error": "overloaded", "news_error_type": "InternalServerError"})
    assert "InternalServerError" in r and "ANTHROPIC_API_KEY" not in r   # a transient failure: reported, no key hint
    assert "error type not recorded" in hc.ai_failure(HOUR, {"news_error": "x"})


def test_a_failed_explanation_is_reported_and_its_authentication_answer_recognised():
    r = hc.ai_failure(HOUR, {**CLEAN, "explanation_error": "Error code: 401 - {'type': 'authentication_error'} " + SECRET_LIKE})
    assert "the explanation failed" in r and "ANTHROPIC_API_KEY" in r and "news step" not in r
    r = hc.ai_failure(HOUR, {"explanation_error": "Request timed out."})
    assert "the explanation failed" in r and "ANTHROPIC_API_KEY" not in r
    both = hc.ai_failure(HOUR, {"news_error": "a", "news_error_type": "APITimeoutError", "explanation_error": "b"})
    assert "the news step failed (APITimeoutError); the explanation failed" in both


def test_the_report_never_repeats_error_text_a_key_or_a_url():
    r = hc.ai_failure(HOUR, {"news_error": SECRET_LIKE, "news_error_type": "AuthenticationError", "explanation_error": SECRET_LIKE})
    assert "sk-ant" not in r and "THIS-MUST-NEVER" not in r and "http" not in r.lower()


def test_the_command_always_writes_the_file_and_never_fails(tmp_path, monkeypatch):
    body = tmp_path / "ai-failure.txt"
    monkeypatch.setattr(hc, "newest_prediction_ai_state", lambda: (HOUR, {"news_error": "x", "news_error_type": "AuthenticationError"}))
    assert hc.main(["--ai-failure-body-file", str(body)]) == 0
    assert body.read_text(encoding="utf-8").startswith("Bitcoin-AI-Agent: AI calls FAILED")
    monkeypatch.setattr(hc, "newest_prediction_ai_state", lambda: (HOUR, CLEAN))
    assert hc.main(["--ai-failure-body-file", str(body)]) == 0 and body.read_text(encoding="utf-8") == ""
    monkeypatch.setattr(hc, "newest_prediction_ai_state", lambda: None)
    assert hc.main(["--ai-failure-body-file", str(body)]) == 0 and body.read_text(encoding="utf-8") == ""


# ---- the workflow ------------------------------------------------------------------------------------------------
WF = Path(".github/workflows/hourly.yml").read_text(encoding="utf-8")


def _steps() -> dict[str, str]:
    body = WF[WF.index("    steps:"):]
    out = {}
    for b in re.split(r"\n(?=      - )", body)[1:]:
        b = "\n".join(line for line in b.split("\n") if not line.strip().startswith("#"))  # comments are not settings
        name = re.search(r"name:\s*(.+)", b)
        out[name.group(1).strip() if name else b.split("\n")[0].strip()] = b
    return out


def test_the_signal_runs_after_the_hour_is_saved_and_right_before_the_missed_hour_signal():
    names = list(_steps())
    i = names.index("Heartbeat AI-failure signal")
    assert names.index("Run hourly analysis") < names.index("Heartbeat direction track (its own check)") < i
    assert names[i + 1] == "Heartbeat missed-hour signal" and names[i + 2] == "Heartbeat ping"
    step = _steps()["Heartbeat AI-failure signal"]
    assert "if: ${{ !cancelled() && env.HEARTBEAT_URL != '' }}" in step and "continue-on-error: true" in step


def test_it_sends_only_a_written_report_and_never_logs_the_url():
    lines = [l.strip() for l in _steps()["Heartbeat AI-failure signal"].split("run: |", 1)[1].split("\n") if l.strip()]
    assert lines == [
        "python -m agent.healthcheck --ai-failure-body-file ai-failure.txt",
        'if [ -s ai-failure.txt ]; then echo "AI_FAILING=1" >> "$GITHUB_ENV"; curl -fsS -m 10 --retry 3 '
        '--data-binary @ai-failure.txt "${HEARTBEAT_URL%/}/fail" > /dev/null; fi']


def test_the_success_ping_is_held_back_while_the_ai_calls_fail():
    ping = _steps()["Heartbeat ping"]
    assert "if: env.HEARTBEAT_URL != '' && env.AI_FAILING != '1'" in ping
    assert '"AI_FAILING=1"' in _steps()["Heartbeat AI-failure signal"]  # the same flag, set only when a report exists
