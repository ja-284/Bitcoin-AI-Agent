"""E033's planning tool: its fast bootstrap is the project's bootstrap, and its window test behaves as designed."""

import ast
from pathlib import Path

import numpy as np

from agent.research import direction_power as dp
from agent.research.metrics import block_bootstrap_estimates


def test_the_fast_bootstrap_is_the_projects_circular_block_bootstrap_of_the_mean():
    rng = np.random.default_rng(1)
    for n in (96, 1000, 1013, 5001):
        d = rng.normal(0.001, 0.02, size=n)
        _, slow = block_bootstrap_estimates(d, np.mean, block=dp.BLOCK, n_boot=200, seed=dp.SEED)
        fast = dp.boot_means(d, n_boot=200, seed=dp.SEED)
        assert np.allclose(fast, slow, rtol=0, atol=1e-15), n


def test_a_planted_effect_is_detected_and_the_centred_series_is_not():
    rng = np.random.default_rng(2)
    d = rng.normal(0.01, 0.02, size=6000)  # a large effect
    t = dp.window_table(d, 2000, float(d.mean()))
    assert t["power_lower_end_above_0"] == 1.0
    assert t["false_positive_rate_centred"] <= 0.1
    assert t["no_improvement_fires_real"] == 0.0


def test_no_effect_is_rarely_detected_and_no_improvement_fires_when_the_interval_is_narrow():
    rng = np.random.default_rng(3)
    d = rng.normal(0.0, 0.001, size=6000)
    t = dp.window_table(d, 3000, float(d.mean()))
    assert t["power_lower_end_above_0"] <= 0.2
    assert t["no_improvement_fires_centred"] == 1.0  # interval about +-0.00004, far below SESOI


def test_hours_needed_follows_the_normal_approximation():
    rng = np.random.default_rng(4)
    d = rng.normal(0.001, 0.02, size=40000)
    a = dp.analytic(d)
    want = len(d) * (dp.Z_SUM * a["se"] / a["mean"]) ** 2
    assert abs(a["hours_for_80pct_power"] - want) <= 1
    assert dp.analytic(-np.abs(d))["hours_for_80pct_power"] is None


def test_the_study_never_opens_the_holdout():
    tree = ast.parse(Path(dp.__file__).read_text(encoding="utf-8"))
    names = {n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword)}
    assert "allow_holdout" not in names and "data" not in names  # build_frame's default stops at the holdout
    called = {n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", None) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "load_bars" not in called and "get_history" not in called
