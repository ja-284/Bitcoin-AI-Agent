"""
Tests for E024's window statistics. No data, no database.

E024 reports how often the live-evaluation rules would pass or fail; those shares are only as good as
the functions that apply the rules, so each rule is checked here in both directions.
"""

import numpy as np

from agent.research import checkpoint_power as cp


def _calibrated(n, seed=0):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.3, 0.7, size=n)
    y = (rng.uniform(size=n) < p).astype(float)
    return p, y


def test_a_large_perfectly_calibrated_sample_passes_e013():
    p, y = _calibrated(200_000)
    ece_ok, buckets_ok, ece = cp.e013_passes(p, y)
    assert ece_ok and buckets_ok and ece < 0.01


def test_a_miscalibrated_forecaster_fails_e013():
    p, _ = _calibrated(50_000)
    y = (np.random.default_rng(1).uniform(size=len(p)) < np.clip(p + 0.10, 0, 1)).astype(float)  # true rate 10 points higher
    ece_ok, buckets_ok, ece = cp.e013_passes(p, y)
    assert not ece_ok and not buckets_ok and ece > 0.08


def test_the_bucket_rule_is_vacuous_when_no_bucket_reaches_100_rows():
    """Why E013's bucket column reads 100% at small window sizes: the rule applies to nothing there."""
    p, y = _calibrated(60)
    _, buckets_ok, _ = cp.e013_passes(p, y)
    assert buckets_ok


def test_window_stats_reports_every_rule_and_the_comparison_with_the_free_rule():
    p, y = _calibrated(2_000, seed=3)
    ref = np.full(len(p), float(y.mean()))           # a reference with no information
    size = np.abs(np.random.default_rng(4).normal(size=len(p))) * (1 + p)
    s = cp.window_stats(p, ref, y, size, y)
    assert s["model_ahead"] and s["brier_diff"] > 0   # an informative forecast beats a flat one
    for key in ("e012_brier", "e012_accuracy", "e012_rho_point", "e013_ece", "e013_buckets",
                "perfect_e013_ece", "perfect_e013_buckets"):
        assert key in s


def test_the_free_rule_winning_is_reported_as_the_model_behind():
    p, y = _calibrated(2_000, seed=5)
    oracle = y * 0.9 + 0.05                           # a reference that nearly knows the answer
    s = cp.window_stats(p, oracle, y, np.abs(p), y)
    assert not s["model_ahead"] and s["brier_diff"] < 0
