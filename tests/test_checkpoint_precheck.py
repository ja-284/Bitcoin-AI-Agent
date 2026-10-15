"""The integrity pre-check for a registered checkpoint (master plan Phase 5). Synthetic rows; it never reads an outcome value."""

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.research import checkpoint_precheck as cp

H = timedelta(hours=1)
T0 = datetime(2026, 9, 21, 17, tzinfo=timezone.utc)


def _rows(n, gaps=()):
    from agent.shadow.model import load_model

    m = load_model(verify_features=False)
    feats = {k: 1.0 for k in m.features} | {"rv_24": 0.004, "rv_168": 0.004, "vol_ratio_24_168": 1.0}
    p = m.predict(feats)[1]
    out = []
    for i in range(n):
        if i in gaps:
            continue
        a = T0 + i * H
        out.append({"as_of": a, "fetched_at": a + H + timedelta(minutes=12), "created_at": a + H + timedelta(minutes=12),
                    "status": "ok", "status_reason": None, "model_version": "move_size_1h_v1", "features": feats,
                    "p_calibrated": p, "horizon_hours": 1, "outcome_status": "ok", "outcome_checked_at": a + 2 * H + timedelta(minutes=12)})
    return out


def test_it_never_reads_an_outcome_value():
    src = Path(cp.__file__).read_text(encoding="utf-8")
    code = ast.parse(src)
    strings = {n.value for n in ast.walk(code) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not any("outcome_large" in s or "outcome_return" in s for s in strings if "never" not in s)
    assert "outcome_large" not in cp.COLUMNS and "outcome_return" not in cp.COLUMNS
    assert "conn.read_only = True" in src


@pytest.fixture(autouse=True)
def full_history(monkeypatch):
    """The git-history item depends on the clone (GitHub's test runner checks out one commit), so the other tests
    take it as given; its own behaviour is tested below, both ways."""
    monkeypatch.setattr(cp, "changes_since_last_reading", lambda since_commit=cp.READING_500H_COMMIT:
                        cp.item("PASS", "changes to the checkpoint path since the last reading", "none (test)"))


def test_without_git_history_the_change_review_fails_and_says_why(monkeypatch):
    import subprocess

    monkeypatch.undo()  # the real function

    def shallow(*a, **kw):
        raise subprocess.CalledProcessError(128, a[0], stderr="fatal: bad revision 'ed96b2a..HEAD'")

    monkeypatch.setattr(subprocess, "run", shallow)
    it = cp.changes_since_last_reading()
    assert it["status"] == "FAIL" and "full clone" in it["detail"] and "bad revision" in it["detail"]


def test_with_git_history_every_commit_on_the_path_is_listed_for_review(monkeypatch):
    import subprocess

    monkeypatch.undo()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, stdout="abc1234 A1 code" + chr(10), stderr=""))
    it = cp.changes_since_last_reading()
    assert it["status"] == "REVIEW" and "abc1234 A1 code" in it["detail"]


def test_a_dry_run_on_a_clean_record_has_no_mandatory_failure():
    rows = _rows(30, gaps={5})
    r = cp.run(20, rows=rows, now=T0 + 40 * H, errors=0)
    status = {i["what"]: i["status"] for i in r["items"]}
    assert r["mandatory_failures"] == [] and r["ready"] is True
    assert status["window"] == "PASS" and status["reproducible from stored predictions"] == "PASS"
    assert "1 hours with no row" in r["items"][0]["detail"]


def test_not_reached_is_not_ready_but_not_a_failure():
    r = cp.run(2000, rows=_rows(30), now=T0 + 40 * H, errors=0)
    assert r["items"][0]["status"] == "NOT YET" and r["ready"] is False and r["mandatory_failures"] == []


def test_an_overdue_or_early_grading_is_a_mandatory_failure():
    rows = _rows(30)
    rows[3]["outcome_status"], rows[3]["outcome_checked_at"] = None, None                  # never graded
    rows[4]["outcome_checked_at"] = rows[4]["as_of"] + H + timedelta(minutes=30)            # graded before its candle closed
    r = cp.run(20, rows=rows, now=T0 + 40 * H, errors=0)
    assert "every available outcome graded by the original rules" in r["mandatory_failures"]
    assert "1 overdue" in next(i for i in r["items"] if i["what"].startswith("every"))["detail"]


def test_a_probability_that_does_not_reproduce_is_a_mandatory_failure():
    rows = _rows(30)
    rows[7]["p_calibrated"] = rows[7]["p_calibrated"] + 0.01
    assert "reproducible from stored predictions" in cp.run(20, rows=rows, now=T0 + 40 * H, errors=0)["mandatory_failures"]


def test_a_foreign_model_version_is_a_mandatory_failure():
    rows = _rows(30)
    rows[2]["model_version"] = "move_size_1h_v2"
    assert "frozen model" in cp.run(20, rows=rows, now=T0 + 40 * H, errors=0)["mandatory_failures"]


def test_the_registered_constants_are_the_protocols():
    assert cp.REGISTERED_BOOTSTRAP == (48, 500, 17)
    assert cp.REGISTERED_ARTEFACT["move_size_1h_v1"].startswith("7d53cd07")
