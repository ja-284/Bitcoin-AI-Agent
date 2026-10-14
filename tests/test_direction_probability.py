"""
E032 (research-only, directional track): what the registration (d8a3d5f) fixed, on synthetic data (no candles,
no database). The inputs are E011's own pre-declared list; the four hypotheses apply exactly as written; the
economics are computed but never judged; development data only; nothing touches the move-size track.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

import agent.research.direction_probability as dp

RNG = np.random.default_rng(32)


def test_the_inputs_are_e011s_pre_declared_list_unchanged():
    e011 = json.loads(Path("research/experiments/E011_logistic_reversal_model.json").read_text(encoding="utf-8"))
    assert dp.INPUTS == e011["feature_sets"]["A_minus_volpct (supplementary coverage check, declared after the first run, before it ran)"]
    assert dp.ONE_FEATURE == ["taker_buy_share_1h"] and set(dp.ONE_FEATURE) <= set(dp.INPUTS)
    assert (dp.HORIZON, dp.C, dp.PRACTICAL_RATIO, dp.MIN_POSITIVE_YEARS) == (1, 0.1, 1.10, 6)
    reg = json.loads(Path("research/experiments/E032_direction_probability.json").read_text(encoding="utf-8"))
    assert "taker_buy_share_1h" in reg["candidates"]["F_one_feature"] and "C = 0.1" in reg["candidates"]["M_model"]


def test_the_return_edge_is_up_calls_minus_down_calls():
    p = np.array([0.6, 0.7, 0.4, 0.3, 0.5])
    r = np.array([0.002, 0.004, -0.001, 0.001, 9.0])  # p == 0.5 is neither side
    assert abs(dp.edge(p, r) - (0.003 - 0.0)) < 1e-12
    assert np.isnan(dp.edge(np.array([0.6, 0.7]), np.array([0.1, 0.2])))


def test_scores_on_a_planted_faint_signal():
    n = 20000
    idx = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    x = RNG.normal(size=n)
    p_true = 1 / (1 + np.exp(-(0.08 * x)))           # a faint, calibrated directional probability
    y = (RNG.uniform(size=n) < p_true).astype(float)
    ret = np.where(y > 0, 1, -1) * RNG.uniform(0.0005, 0.003, n)
    base = np.full(n, 0.5)
    s = dp.scores(p_true, y, ret, base, idx)
    assert s["skill_vs_base_rate"] > 0 and s["ece"] < 0.03 and abs(s["calibration_line"]["slope"] - 1) < 0.35
    assert s["accuracy_at_0_5"] > 0.5 and s["return_edge"]["point"] > 0
    assert set(s["by_year"]) == {"2023", "2024", "2025"}


def _result(base_minus=(0.0009, 0.0004), base_minus_val=(0.0009, 0.0003), skill_m=0.004, skill_f=0.003,
            f_minus_ci_low=0.0001, ece=(0.006, 0.006), buckets=True, years=(1, 1, 1, 1, 1, 1, -1, -1)):
    yrs = {str(2018 + i): {"skill_vs_base_rate": v * 0.001} for i, v in enumerate(years)}
    model = lambda e, yy: {"skill_vs_base_rate": skill_m, "ece": e, "e013_buckets_ok": buckets, "by_year": yy}  # noqa: E731
    return {"by_period": {
        "exploration": {"base_minus_model_brier": {"diff": base_minus[0], "ci_low": base_minus[1]},
                        "model": model(ece[0], {k: v for k, v in yrs.items() if k < "2024"})},
        "validation": {"base_minus_model_brier": {"diff": base_minus_val[0], "ci_low": base_minus_val[1]},
                       "one_feature_minus_model_brier": {"ci_low": f_minus_ci_low},
                       "model": model(ece[1], {k: v for k, v in yrs.items() if k >= "2024"}),
                       "one_feature": {"skill_vs_base_rate": skill_f}}}}


def test_the_four_hypotheses_are_applied_exactly_as_registered():
    v = dp.judge(_result())
    assert v["H_a_skill_beyond_the_base_rate"] and v["H_b_more_than_one_reversal_feature"] and v["H_c_calibrated"]
    assert v["H_d_stable"] and v["positive_years"] == 6
    assert not dp.judge(_result(base_minus_val=(0.0009, -0.0001)))["H_a_skill_beyond_the_base_rate"]  # interval touches 0
    assert not dp.judge(_result(skill_f=0.0037))["H_b_more_than_one_reversal_feature"]               # 0.004 < 1.10 x 0.0037
    assert not dp.judge(_result(f_minus_ci_low=-0.00001))["H_b_more_than_one_reversal_feature"]
    assert not dp.judge(_result(ece=(0.031, 0.01)))["H_c_calibrated"]
    assert not dp.judge(_result(buckets=False))["H_c_calibrated"]
    assert not dp.judge(_result(years=(1, 1, 1, 1, 1, -1, -1, -1)))["H_d_stable"]


def test_development_data_only_and_separate_from_the_move_size_track():
    src = Path("agent/research/direction_probability.py").read_text(encoding="utf-8")
    assert "build_frame(HORIZON, [], INPUTS, \"direction\")" in src and "allow_holdout" not in src
    assert "calib_days=0" in src and "df[INPUTS + [\"y\"]].dropna().index" in src
    import ast

    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
    for forbidden in ("agent.shadow", "agent.database", "agent.reporting", "agent.research.feature_count"):
        assert not any(m and m.startswith(forbidden) for m in imported), forbidden  # nothing from the move-size or live side
    assert "large_move" not in src, "the directional target only"
