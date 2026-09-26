"""
The live checkpoints (agent/research/live_checkpoint.py) apply the pre-registered rules exactly: the
first N prospective hours and nothing else, no verdict before its registered size, and the same pass
rules E024 measured. Synthetic rows only -- no database, no network.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from agent.research import live_checkpoint as lc

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
H = timedelta(hours=1)


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    monkeypatch.setattr(lc, "N_BOOT", 60)  # the registered 500 is used in production; tests need speed only


def _rows(n, informative=True, seed=0, start=T0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        p = float(rng.uniform(0.15, 0.85)) if informative else 0.45
        large = bool(rng.uniform() < (p if informative else 0.45))
        ret = (0.004 + 0.004 * rng.uniform()) if large else 0.002 * rng.uniform()
        out.append({"as_of": start + i * H, "fetched_at": start + i * H + H + timedelta(minutes=12), "horizon_hours": 1,
                    "status": "ok", "outcome_status": "ok", "p_calibrated": p, "outcome_large": large,
                    "outcome_return": ret if i % 2 else -ret, "features": {"rv_168": 0.002 + 0.008 * rng.uniform()}})
    return out


def test_only_prospective_graded_rows_count_in_time_order():
    rows = _rows(6)
    rows[1]["fetched_at"] = rows[1]["as_of"] + 3 * H          # written after its outcome existed
    rows[2]["status"] = "unavailable"
    rows[3]["outcome_status"] = None                           # not graded yet
    kept = lc.prospective_graded(list(reversed(rows)))
    assert [r["as_of"] for r in kept] == [rows[i]["as_of"] for i in (0, 4, 5)]


@pytest.mark.parametrize("n,due", [(0, None), (42, None), (499, None), (500, 500), (1999, 500), (2000, 2000), (9999, 5000)])
def test_the_due_checkpoint(n, due):
    assert lc.due_checkpoint(n) == due


def test_a_checkpoint_reads_exactly_the_first_n_hours_and_nothing_after():
    """Clarification 1: later hours cannot move a checkpoint -- no reading 'whenever it looks good'."""
    rows = _rows(700)
    a = lc.evaluate(rows, 500)
    garbled = [dict(r) for r in rows]
    for r in garbled[500:]:
        r["p_calibrated"], r["outcome_large"] = 0.99, False
    b = lc.evaluate(garbled, 500)
    assert a["stats"] == b["stats"] and a["last_hour"] == rows[499]["as_of"].isoformat()


def test_a_checkpoint_cannot_be_computed_early():
    with pytest.raises(ValueError, match="not reached"):
        lc.evaluate(_rows(499), 500)


def test_no_verdict_at_500_hours_by_registration():
    e = lc.evaluate(_rows(500), 500)
    assert e["verdicts"] == {} and "No verdict at this checkpoint" in lc.render(e)
    assert "rho_ci95" in e["stats"] and "ece_ci95" in e["stats"]  # intervals exist from 192 hours on


def test_the_2000_hour_verdict_separates_an_informative_model_from_a_useless_one():
    good = lc.evaluate(_rows(2000, informative=True), 2000)
    assert good["verdicts"]["E012"]["pass"], good["verdicts"]["E012"]
    useless = lc.evaluate(_rows(2000, informative=False), 2000)
    assert not useless["verdicts"]["E012"]["pass"]
    assert not useless["verdicts"]["E012"]["parts"]["brier_5pct_below_base"]
    assert set(good["slices"]) == {"weekday_weekend", "hour_block_utc"} and "E013" not in good["verdicts"]
    assert "E012: PASS" in lc.render(good) and "E012: FAIL" in lc.render(useless)


def test_the_5000_hour_checkpoint_needs_the_frozen_terciles_and_reports_regimes():
    rows = _rows(5000)
    with pytest.raises(ValueError, match="terciles"):
        lc.evaluate(rows, 5000)
    e = lc.evaluate(rows, 5000, terciles=(0.004, 0.007))
    assert {"E012", "E013"} <= set(e["verdicts"])
    assert set(e["slices"]["volatility_regime_168h"]) <= {"low", "mid", "high", "unknown"}
    assert "month" in e["slices"]


def test_the_pass_rules_are_the_ones_e024_measured():
    """One implementation of E013's rule, shared with the study of its own error rates."""
    from agent.research import checkpoint_power

    assert lc.e013_passes is checkpoint_power.e013_passes and lc.E012_SKILL_BAR == checkpoint_power.E012_SKILL_BAR == 0.05
    assert (lc.BLOCK_HOURS, lc.E012_ACCURACY_MARGIN, lc.E012_RHO_BAR) == (48, 0.05, 0.10)


def test_the_registered_resample_count_is_used_in_production():
    import importlib

    assert importlib.reload(lc).N_BOOT == 500  # rule 3 (the fixture's 60 applies to tests only)


def test_the_rho_part_requires_its_interval():
    s = {"brier_rel_gain": 0.2, "accuracy": 0.9, "naive_rate": 0.6, "rho": 0.3}
    assert not lc.e012_verdict(s)["parts"]["rho_ge_0_10_interval_above_0"], "no interval, no pass"
    assert lc.e012_verdict(s | {"rho_ci95": [0.01, 0.5]})["pass"]
    assert not lc.e012_verdict(s | {"rho_ci95": [-0.01, 0.5]})["pass"]


def test_regime_assignment():
    cuts = (0.004, 0.007)
    assert lc.regime_of({"features": {"rv_168": 0.003}}, cuts) == "low"
    assert lc.regime_of({"features": {"rv_168": 0.004}}, cuts) == "mid"
    assert lc.regime_of({"features": {"rv_168": 0.0071}}, cuts) == "high"
    assert lc.regime_of({"features": {}}, cuts) == "unknown"


def test_the_integrity_check_confirms_reproducible_probabilities_and_catches_one_that_is_not():
    """Rows whose probability is exactly the frozen artefact's output pass; one altered probability is caught."""
    from agent.shadow.model import load_model

    m = load_model(verify_features=False)
    rng = np.random.default_rng(9)
    rows = []
    for _ in range(20):
        feats = {"tr_mean_14_rel": float(rng.uniform(0.004, 0.012)), "rv_24": float(rng.uniform(0.002, 0.009)),
                 "rv_168": float(rng.uniform(0.003, 0.009)), "vol_ratio_24_168": float(rng.uniform(0.6, 1.4)),
                 "trades_rel_24h": float(rng.uniform(0.6, 1.4)), "trades_rel_168h": float(rng.uniform(0.6, 1.4)),
                 "hour_sin": 0.5, "hour_cos": 0.5, "is_weekend": 0.0}
        rows.append({"features": feats, "p_calibrated": m.predict(feats)[1], "model_version": m.version})
    ok = lc.reproducibility(rows)
    assert ok["ok"] and ok["not_reproducible"] == 0 and ok["max_abs_diff"] < 1e-12
    rows[5] = dict(rows[5], p_calibrated=rows[5]["p_calibrated"] + 0.01)
    bad = lc.reproducibility(rows)
    assert not bad["ok"] and bad["not_reproducible"] == 1
    other = [dict(r, model_version="move_size_1h_v2") for r in rows[:3]]
    assert not lc.reproducibility(other)["ok"], "rows from another model version must not pass as this artefact's"
    e = lc.evaluate(_rows(500), 500)
    assert "Integrity: every judged probability reproduces" in lc.render(e | {"reproducibility": ok})
    assert "INTEGRITY WARNING: 1 of 20" in lc.render(e | {"reproducibility": bad})


def _artefact_rows(n, seed=11):
    """Prospective rows whose probabilities are exactly the frozen artefact's, as the live shadow writes them."""
    import math

    from agent.shadow.model import load_model

    m = load_model(verify_features=False)
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        t = T0 + i * H
        feats = {"tr_mean_14_rel": float(rng.uniform(0.004, 0.012)), "rv_24": float(rng.uniform(0.002, 0.009)),
                 "rv_168": float(rng.uniform(0.003, 0.009)), "vol_ratio_24_168": float(rng.uniform(0.6, 1.4)),
                 "trades_rel_24h": float(rng.uniform(0.6, 1.4)), "trades_rel_168h": float(rng.uniform(0.6, 1.4)),
                 "hour_sin": math.sin(2 * math.pi * t.hour / 24), "hour_cos": math.cos(2 * math.pi * t.hour / 24),
                 "is_weekend": float(t.weekday() >= 5)}
        p = m.predict(feats)[1]
        large = bool(rng.uniform() < p)
        ret = (0.003 + 0.004 * rng.uniform()) if large else 0.002 * rng.uniform()
        rows.append({"as_of": t, "fetched_at": t + H + timedelta(minutes=12), "horizon_hours": 1, "status": "ok",
                     "outcome_status": "ok", "p_calibrated": p, "outcome_large": large, "outcome_return": ret,
                     "features": feats, "model_version": m.version, "threshold": 0.0025})
    return rows


def test_the_checkpoint_command_runs_end_to_end_and_writes_its_reading(tmp_path, monkeypatch):
    """
    K1 (interim plan): the parts are tested elsewhere; here the COMMAND runs -- fetch, the free-rule comparison,
    the evaluation, the integrity precondition and both files -- so that it cannot fail for the first time on
    the day 500 hours are reached. Synthetic rows only; output to a temporary folder.
    """
    import json
    import sys

    import pandas as pd

    import agent.research.weekly_report as wr

    rows = _artefact_rows(530)
    ewma = pd.Series([0.4] * len(rows), index=pd.DatetimeIndex([r["as_of"] for r in rows]))
    monkeypatch.setattr(wr, "fetch_shadow_rows", lambda: rows)
    monkeypatch.setattr(wr, "ewma_reference_series", lambda now, lookback_hours=800: ewma)
    monkeypatch.setattr(lc, "OUT_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["live_checkpoint"])

    assert lc.main() == 0
    md = (tmp_path / "checkpoint_500h.md").read_text(encoding="utf-8")
    doc = json.loads((tmp_path / "checkpoint_500h.json").read_text(encoding="utf-8"))
    assert "Live checkpoint — 500 prospective hours" in md and "No verdict at this checkpoint" in md
    assert "Integrity: every judged probability reproduces" in md
    assert doc["reproducibility"]["ok"] and doc["reproducibility"]["rows"] == 500
    assert doc["vs_free_ewma_rule"]["hours_compared"] == 500
    assert doc["last_hour"] == rows[499]["as_of"].isoformat(), "exactly the first 500 prospective hours"

    before = (tmp_path / "checkpoint_500h.md").read_bytes()
    assert lc.main() == 0 and (tmp_path / "checkpoint_500h.md").read_bytes() == before, "a second run must not rewrite it"


def test_the_checkpoint_command_is_quiet_before_500_hours(tmp_path, monkeypatch, capsys):
    import sys

    import agent.research.weekly_report as wr

    monkeypatch.setattr(wr, "fetch_shadow_rows", lambda: _artefact_rows(120))
    monkeypatch.setattr(lc, "OUT_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["live_checkpoint"])
    assert lc.main() == 0 and "No checkpoint reached: 120 of 500" in capsys.readouterr().out
    assert not list(tmp_path.iterdir()), "nothing is written before the checkpoint"


def test_the_terciles_are_never_recomputed(tmp_path):
    frozen = tmp_path / "regime_terciles_v1.json"
    frozen.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        lc.freeze_regime_terciles(frozen)
