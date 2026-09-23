"""
The heartbeat steps in .github/workflows/hourly.yml: inert without the secret, unable to change the
job's result, the success ping last, and a failed run signalled at once. Read as text (no YAML
dependency): each step is the block starting at a "      - " line.
"""

import re
from pathlib import Path

WF = Path(".github/workflows/hourly.yml").read_text(encoding="utf-8")


def _steps() -> dict[str, str]:
    body = WF[WF.index("    steps:"):]
    blocks = re.split(r"\n(?=      - )", body)[1:]
    out = {}
    for b in blocks:
        b = "\n".join(line for line in b.split("\n") if not line.strip().startswith("#"))  # comments are not settings
        name = re.search(r"name:\s*(.+)", b)
        out[name.group(1).strip() if name else b.split("\n")[0].strip()] = b
    return out


def test_the_success_ping_is_the_last_step_and_runs_only_on_success():
    steps = _steps()
    names = list(steps)
    assert names.index("Heartbeat ping") == len(names) - 2  # only the failure signal follows it
    ping = steps["Heartbeat ping"]
    assert "if: env.HEARTBEAT_URL != ''" in ping and "failure()" not in ping and "always()" not in ping


def test_neither_heartbeat_step_can_change_the_jobs_result():
    """A heartbeat hiccup must never turn a good hour red; the service alarms on silence by itself."""
    steps = _steps()
    for name in ("Heartbeat ping", "Heartbeat failure signal"):
        assert "continue-on-error: true" in steps[name], name


def test_a_failed_run_signals_the_heartbeat_service_at_once():
    sig = _steps()["Heartbeat failure signal"]
    assert "if: failure() && env.HEARTBEAT_URL != ''" in sig
    assert '"${HEARTBEAT_URL%/}/fail"' in sig


def test_the_url_never_appears_in_a_log():
    """curl -s silences progress; -f fails on HTTP errors; output goes to /dev/null. The URL is a secret."""
    for name in ("Heartbeat ping", "Heartbeat failure signal"):
        run = re.search(r"run:\s*(.+)", _steps()[name]).group(1)
        assert run.startswith("curl -fsS") and run.endswith("> /dev/null") and "echo" not in run


def test_the_real_work_steps_are_not_allowed_to_fail_silently():
    """Only the heartbeat steps may carry continue-on-error; a failed analysis must fail the job."""
    for name, block in _steps().items():
        if not name.startswith("Heartbeat"):
            assert "continue-on-error" not in block, name
