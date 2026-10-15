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


# ---- the single-missed-hour signal (2026-10-14) ------------------------------------------------------------

def _run_lines(block: str) -> list[str]:
    """The shell lines of a `run: |` step."""
    lines = block.split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip() == "run: |")
    return [line.strip() for line in lines[start + 1:] if line.strip()]


def test_the_job_records_its_start_before_anything_else():
    """Rows this run saves are created after this moment; that is how a gap is reported exactly once."""
    steps = _steps()
    first = list(steps)[0]
    assert first == "Record when this job started"
    assert 'echo "JOB_STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_ENV"' in steps[first]


def test_the_missed_hour_signal_sits_right_before_the_success_ping_and_cannot_change_the_result():
    steps = _steps()
    names = list(steps)
    assert names.index("Heartbeat missed-hour signal") == names.index("Heartbeat ping") - 1
    sig = steps["Heartbeat missed-hour signal"]
    assert "continue-on-error: true" in sig
    # It runs after a failed later step too (the hour may already be saved), never after a cancellation.
    assert "if: ${{ !cancelled() && env.HEARTBEAT_URL != '' }}" in sig


def test_the_missed_hour_signal_sends_only_a_written_report_and_never_logs_the_url():
    detect, send = _run_lines(_steps()["Heartbeat missed-hour signal"])
    assert detect == 'python -m agent.healthcheck --new-gap-since "$JOB_STARTED_AT" --gap-body-file missed-hours.txt'
    # Only when the report file is non-empty: no gap, no signal. The URL stays inside curl, silenced.
    assert send.startswith("if [ -s missed-hours.txt ]; then curl -fsS -m 10 --retry 3 --data-binary @missed-hours.txt ")
    assert '"${HEARTBEAT_URL%/}/fail" > /dev/null; fi' in send and "echo" not in send


# ---- the direction shadow track (E034, 2026-10-15) ---------------------------------------------------------
def test_the_direction_track_runs_after_the_live_record_is_saved_checked_and_published():
    names = list(_steps())
    live = ("Run hourly analysis", "Self-check that this hour's prediction was saved", "Shadow move-size probability",
            "Grade shadow rows", "Publish the backend state")
    for step in ("Shadow direction probability", "Grade direction shadow rows"):
        assert all(names.index(step) > names.index(x) for x in live), step
        assert names.index(step) < names.index("Heartbeat missed-hour signal")
    assert "run: python -m agent.direction_shadow.run\n" in _steps()["Shadow direction probability"] + "\n"
    assert "--raise-errors" not in WF and "--no-save" not in WF  # the recording entry point, never the debugging one
