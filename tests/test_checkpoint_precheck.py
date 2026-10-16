"""
The integrity pre-check for a registered checkpoint (master plan Phase 5; addendum 2026-10-16, item 4). Every one of
its eight rules is tested on its own: the right condition, a broken input caught, and fail-closed behaviour. Synthetic
rows only; it never reads an outcome value, computes no metric, and writes nothing.
"""

import ast
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.research import checkpoint_precheck as cp

H = timedelta(hours=1)
T0 = datetime(2026, 9, 21, 17, tzinfo=timezone.utc)
NOW = T0 + 40 * H


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


def _status(r, what):
    return next(i for i in r["items"] if i["what"] == what)["status"]


@pytest.fixture(autouse=True)
def full_history(monkeypatch):
    """Rule 3 depends on the clone (GitHub's test runner checks out one commit), so the run() tests take it as given;
    its own behaviour is tested below with its git call replaced."""
    monkeypatch.setattr(cp, "changes_since_last_reading", lambda *a, **k: cp.item("PASS", "changes to the checkpoint path", "test"))


# ---- rule 1: the window
def test_1_the_window_is_exactly_the_first_n_prospective_graded_hours_in_time_order():
    rows = _rows(30, gaps={5})
    rows[2]["fetched_at"] = rows[2]["as_of"] + 3 * H  # not prospective: never counted
    it, first = cp.window(list(reversed(rows)), 20)
    eligible = [r for r in rows if r is not rows[2]]
    assert it["status"] == "PASS" and [r["as_of"] for r in first] == [r["as_of"] for r in eligible[:20]]
    assert "1 not prospective" in it["detail"] and "1 hours with no row" in it["detail"]


def test_1_a_size_not_reached_is_not_yet_and_no_rows_at_all_is_a_failure():
    it, _ = cp.window(_rows(30), 2000)
    assert it["status"] == "NOT YET"
    assert cp.window([], 20)[0]["status"] == "FAIL"


# ---- rule 2: the frozen model
def test_2_a_changed_artefact_is_a_failure(monkeypatch):
    monkeypatch.setattr(cp, "REGISTERED_ARTEFACT", {"move_size_1h_v1": "0" * 64})
    assert cp.frozen_model(_rows(5))["status"] == "FAIL"


def test_2_a_row_from_another_model_version_is_a_failure():
    rows = _rows(5)
    rows[2]["model_version"] = "move_size_1h_v2"
    assert cp.frozen_model(rows)["status"] == "FAIL"


def test_2_changed_input_definitions_are_a_failure_not_a_crash(monkeypatch):
    import agent.shadow.features as sf

    real = sf.feature_reference_values
    monkeypatch.setattr(sf, "feature_reference_values", lambda names: {k: [v * 1.01 for v in vals] for k, vals in real(names).items()})
    it = cp.safely("frozen model", cp.frozen_model, _rows(5))
    assert it["status"] == "FAIL" and "ModelVersionError" in it["detail"]


def test_2_the_registered_artefact_passes():
    assert cp.frozen_model(_rows(5))["status"] == "PASS"


# ---- rule 3: every change on the checkpoint's path is reviewed
def _reviews(tmp_path, reviews):
    p = tmp_path / "reviews.json"
    p.write_text(json.dumps({"reviews": reviews}), encoding="utf-8")
    return p


GOOD = {"verdict": "outside the checkpoint's computation", "evidence": "the functions the checkpoint uses are byte-identical before and after"}


def test_3_an_unreviewed_commit_on_the_path_is_a_failure(tmp_path, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(cp, "commits_on_path", lambda since: ["a" * 40, "b" * 40])
    it = cp.changes_since_last_reading(reviews_path=_reviews(tmp_path, {"a" * 40: GOOD}))
    assert it["status"] == "FAIL" and "bbbbbbb" in it["detail"] and "aaaaaaa" not in it["detail"]


@pytest.mark.parametrize("bad", [{"verdict": "looks fine", "evidence": GOOD["evidence"]}, {"verdict": GOOD["verdict"], "evidence": "ok"}])
def test_3_a_review_without_an_allowed_verdict_or_real_evidence_is_no_review(tmp_path, monkeypatch, bad):
    monkeypatch.undo()
    monkeypatch.setattr(cp, "commits_on_path", lambda since: ["a" * 40])
    assert cp.changes_since_last_reading(reviews_path=_reviews(tmp_path, {"a" * 40: bad}))["status"] == "FAIL"


def test_3_every_reviewed_commit_passes_and_is_listed(tmp_path, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(cp, "commits_on_path", lambda since: ["a" * 40])
    it = cp.changes_since_last_reading(reviews_path=_reviews(tmp_path, {"a" * 40: GOOD}))
    assert it["status"] == "PASS" and "aaaaaaa (outside the checkpoint's computation)" in it["detail"]


def test_3_without_git_history_the_review_fails_and_says_why(monkeypatch):
    import subprocess

    monkeypatch.undo()

    def shallow(*a, **kw):
        raise subprocess.CalledProcessError(128, a[0], stderr="fatal: bad revision 'ed96b2a..HEAD'")

    monkeypatch.setattr(subprocess, "run", shallow)
    it = cp.changes_since_last_reading()
    assert it["status"] == "FAIL" and "full clone" in it["detail"] and "bad revision" in it["detail"]


def test_3_the_real_review_file_covers_the_real_history(monkeypatch):
    """In a full clone, every commit on the path since the last reading must already be reviewed."""
    monkeypatch.undo()
    try:
        commits = cp.commits_on_path()
    except Exception:  # noqa: BLE001 -- a shallow clone (CI) cannot list the history; the FAIL path is tested above
        pytest.skip("no git history in this clone")
    assert commits, "the path has changed since the reading (Amendment A1), so there must be commits to review"
    assert cp.changes_since_last_reading()["status"] == "PASS"


# ---- rule 4: the holdout
def test_4_an_access_log_is_a_failure(tmp_path, monkeypatch):
    log = tmp_path / "HOLDOUT_ACCESS.log"
    log.write_text("opened")
    monkeypatch.setattr(cp, "HOLDOUT_LOG", log)
    assert cp.holdout(_rows(5), NOW)["status"] == "FAIL" and cp.holdout([], NOW)["status"] == "FAIL"


def test_4_a_warm_up_reaching_into_the_holdout_is_a_failure(monkeypatch, tmp_path):
    import agent.research.weekly_report as wr

    monkeypatch.setattr(cp, "HOLDOUT_LOG", tmp_path / "absent.log")
    monkeypatch.setattr(wr, "ewma_fetch_hours", lambda end, lookback: 10 ** 5)
    assert cp.holdout(_rows(5), NOW)["status"] == "FAIL"


def test_4_the_clipped_warm_up_with_no_log_passes_and_an_impossible_window_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(cp, "HOLDOUT_LOG", tmp_path / "absent.log")
    assert cp.holdout(_rows(5), NOW)["status"] == "PASS"
    early = datetime(2026, 8, 1, tzinfo=timezone.utc)  # inside the holdout: ewma_fetch_hours refuses it
    assert cp.safely("holdout", cp.holdout, _rows(5), early)["status"] == "FAIL"


# ---- rule 5: grading
def test_5_an_overdue_row_alone_is_a_failure():
    rows = _rows(30)
    rows[3]["outcome_status"], rows[3]["outcome_checked_at"] = None, None
    it = cp.all_graded(rows, NOW)
    assert it["status"] == "FAIL" and it["detail"].startswith("1 overdue") and "0 graded before" in it["detail"]


def test_5_an_early_grading_alone_is_a_failure():
    rows = _rows(30)
    rows[4]["outcome_checked_at"] = rows[4]["as_of"] + H + timedelta(minutes=30)  # before its target candle closed
    it = cp.all_graded(rows, NOW)
    assert it["status"] == "FAIL" and it["detail"].startswith("0 overdue") and "1 graded before" in it["detail"]


def test_5_a_row_still_within_its_grace_is_not_overdue():
    rows = _rows(30)
    rows[-1]["outcome_status"], rows[-1]["outcome_checked_at"] = None, None
    assert cp.all_graded(rows, rows[-1]["as_of"] + 3 * H)["status"] == "PASS"


# ---- rule 6: the registered settings
def test_6_as_registered_passes():
    assert cp.registered_settings()["status"] == "PASS"


@pytest.mark.parametrize("module,name,value", [("live_checkpoint", "N_BOOT", 2000), ("live_checkpoint", "SEED", 18),
                                               ("live_checkpoint", "CHECKPOINTS", (500, 1500, 5000)),
                                               ("checkpoint_power", "E012_SKILL_BAR", 0.04), ("live_checkpoint", "E012_RHO_BAR", 0.05),
                                               ("checkpoint_power", "E013_ECE_BAR", 0.05)])
def test_6_any_changed_setting_or_threshold_is_a_failure(monkeypatch, module, name, value):
    import importlib

    monkeypatch.setattr(importlib.import_module(f"agent.research.{module}"), name, value)
    assert cp.registered_settings()["status"] == "FAIL"


def test_6_a_loosened_bucket_rule_is_a_failure(monkeypatch):
    import numpy as np

    import agent.research.checkpoint_power as cpw
    from agent.research.metrics import reliability_table

    def loose(p, y):
        buckets, ece, _ = reliability_table(p, y)
        return ece <= 0.03, all(abs(b.observed - b.mean_predicted) <= 0.10 for b in buckets if b.n >= 100), ece

    monkeypatch.setattr(cpw, "e013_passes", loose)
    assert cp.registered_settings()["status"] == "FAIL"
    assert np.isclose(cp.REGISTERED_THRESHOLDS["E013_ECE_BAR"], 0.03)


# ---- rule 7: reproducibility
def test_7_a_probability_that_does_not_reproduce_is_a_failure():
    rows = _rows(30)
    rows[7]["p_calibrated"] += 0.01
    assert cp.reproducible(rows)["status"] == "FAIL" and cp.reproducible(_rows(30))["status"] == "PASS"
    assert cp.reproducible([])["status"] == "FAIL"


# ---- rule 8: the facts to document
def test_8_lists_the_facts_from_inputs_only():
    it = cp.deviations(_rows(10), 2)
    assert it["status"] == "REVIEW" and "errors recorded during the window: 2" in it["detail"] and "{'low': 10}" in it["detail"]


# ---- the whole: fail closed, exit codes, read-only, outcome-blind
def test_a_clean_dry_run_is_ready_only_when_the_size_is_reached(monkeypatch, tmp_path):
    monkeypatch.setattr(cp, "HOLDOUT_LOG", tmp_path / "absent.log")
    r = cp.run(20, rows=_rows(30, gaps={5}), now=NOW, errors=0)
    assert r["mandatory_failures"] == [] and r["ready"] is True and cp.exit_code(r) == 0
    r = cp.run(2000, rows=_rows(30), now=NOW, errors=0)
    assert r["ready"] is False and r["mandatory_failures"] == [] and cp.exit_code(r) == 3


def test_any_failure_blocks_readiness_and_exits_1(monkeypatch, tmp_path):
    monkeypatch.setattr(cp, "HOLDOUT_LOG", tmp_path / "absent.log")
    rows = _rows(30)
    rows[3]["outcome_status"], rows[3]["outcome_checked_at"] = None, None
    r = cp.run(20, rows=rows, now=NOW, errors=0)
    assert _status(r, "window") == "PASS" and r["ready"] is False and cp.exit_code(r) == 1
    assert r["mandatory_failures"] == ["every available outcome graded by the original rules"]


def test_a_check_that_raises_is_a_failure_not_a_crash_and_not_a_pass():
    def boom():
        raise RuntimeError("database gone")
    it = cp.safely("registered settings", boom)
    assert it["status"] == "FAIL" and "database gone" in it["detail"]


def test_main_returns_the_registered_exit_codes(monkeypatch):
    for result, code in (({"items": [], "mandatory_failures": ["x"], "ready": False}, 1),
                         ({"items": [], "mandatory_failures": [], "ready": False}, 3),
                         ({"items": [], "mandatory_failures": [], "ready": True}, 0)):
        monkeypatch.setattr(cp, "run", lambda n, r=result: r)
        assert cp.main(["--hours", "2000"]) == code


def test_it_reads_no_outcome_value_and_no_holdout_and_writes_nothing():
    assert "outcome_large" not in cp.COLUMNS and "outcome_return" not in cp.COLUMNS
    assert cp.SQL_ROWS == "SELECT " + ", ".join(cp.COLUMNS) + " FROM shadow_move_size ORDER BY as_of"
    src = Path(cp.__file__).read_text(encoding="utf-8")
    assert src.count("conn.read_only = True") == 2, "both queries must run on a read-only connection"
    for word in ("INSERT", "UPDATE ", "DELETE", "allow_holdout", "load_bars", "get_history", "write_text", "write_bytes"):
        assert word not in src, word


def test_it_computes_no_metric_from_outcomes():
    """Only reviewed names are used from the checkpoint module, and no statistics function is imported at all."""
    tree = ast.parse(Path(cp.__file__).read_text(encoding="utf-8"))
    imported = {(n.module, a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not any(m == "agent.research.metrics" for m, _ in imported)
    from_lc = {name for m, name in imported if m == "agent.research.live_checkpoint"}
    via_lc = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "lc"}
    assert from_lc | via_lc <= cp.LIVE_CHECKPOINT_NAMES_USED, (from_lc | via_lc) - cp.LIVE_CHECKPOINT_NAMES_USED
    via_cpw = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "cpw"}
    assert via_cpw <= {"E012_SKILL_BAR", "E013_ECE_BAR", "e013_passes"}  # e013_passes runs on synthetic numbers only


def test_running_it_leaves_models_results_and_rules_byte_identical(monkeypatch, tmp_path):
    monkeypatch.setattr(cp, "HOLDOUT_LOG", tmp_path / "absent.log")
    watched = [*Path("agent/shadow/models").glob("*.json"), *Path("research/monitoring").glob("checkpoint_*"),
               Path("research/LIVE_EVALUATION.md"), cp.REVIEWS_PATH]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    cp.run(20, rows=_rows(30), now=NOW, errors=0)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched} == before
