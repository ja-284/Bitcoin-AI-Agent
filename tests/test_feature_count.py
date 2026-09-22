"""
Tests for the E018 feature-count machinery. No network, no database, no data snapshot:
everything here runs on frames built in the test.

Each test checks a property the experiment's validity depends on, and each would fail if the
property were removed -- the ablation must cover every feature, the paired comparison must
refuse rows that are not the same rows, the exact-dependence check must not report an identity
that is not there, and the extracted bootstrap helper must agree with the one it replaced.
"""

import numpy as np
import pandas as pd
import pytest

from agent.research import feature_count as fc
from agent.research.metrics import block_bootstrap, block_bootstrap_estimates, brier_score


def _frame(n: int = 400, seed: int = 0) -> pd.DataFrame:
    """A frame with the nine inputs, where vol_ratio obeys the log identity by construction."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    rv24 = rng.normal(size=n)
    rv168 = rng.normal(size=n)
    return pd.DataFrame({
        "tr_mean_14_rel": rng.normal(size=n), "rv_24": rv24, "rv_168": rv168,
        "vol_ratio_24_168": rv24 - rv168,  # the identity after log transforms
        "trades_rel_24h": rng.normal(size=n), "trades_rel_168h": rng.normal(size=n),
        "hour_sin": np.sin(np.arange(n)), "hour_cos": np.cos(np.arange(n)),
        "is_weekend": (np.arange(n) % 7 >= 5).astype(float),
        "period": "exploration",
    }, index=idx)


def _variant(idx: pd.DatetimeIndex, p: np.ndarray, y: np.ndarray) -> dict:
    return {"predictions": pd.DataFrame({"p": p, "y": y, "period": "validation"}, index=idx)}


def test_ablation_groups_cover_every_feature_exactly_once():
    covered = [f for cols in fc.GROUPS_UNDER_TEST.values() for f in cols]
    assert sorted(covered) == sorted(fc.FULL)
    assert len(covered) == len(set(covered))


def test_log_features_are_a_subset_of_the_inputs():
    assert set(fc.LOG_FEATURES) <= set(fc.FULL)


def test_exact_dependence_finds_the_identity():
    res = fc.exact_dependence(_frame())
    assert res["exact_to_floating_point"]
    assert res["max_abs_residual"] < 1e-9


def test_exact_dependence_does_not_invent_an_identity():
    """Perturbation: break the relationship and the check must stop claiming it holds."""
    df = _frame()
    df.loc[df.index[10], "vol_ratio_24_168"] += 0.5
    res = fc.exact_dependence(df)
    assert not res["exact_to_floating_point"]
    assert res["max_abs_residual"] == pytest.approx(0.5, rel=1e-9)


def test_paired_comparison_of_a_model_with_itself_is_exactly_zero():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2024-01-01", periods=600, freq="h", tz="UTC")
    p = rng.uniform(0.2, 0.8, size=600)
    y = (rng.uniform(size=600) < p).astype(float)
    diff, se = fc.paired_brier_se(_variant(idx, p, y), _variant(idx, p, y), "validation")
    assert diff == 0.0
    assert se == 0.0


def test_paired_comparison_refuses_different_rows():
    """The whole point of the design is that variants are scored on identical hours."""
    rng = np.random.default_rng(4)
    idx = pd.date_range("2024-01-01", periods=300, freq="h", tz="UTC")
    p = rng.uniform(0.2, 0.8, size=300)
    y = (rng.uniform(size=300) < p).astype(float)
    shifted = idx + pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="different rows"):
        fc.paired_brier_se(_variant(idx, p, y), _variant(shifted, p, y), "validation")


def test_paired_se_detects_a_genuinely_worse_model():
    rng = np.random.default_rng(5)
    idx = pd.date_range("2024-01-01", periods=2000, freq="h", tz="UTC")
    p = rng.uniform(0.1, 0.9, size=2000)
    y = (rng.uniform(size=2000) < p).astype(float)
    worse = np.full(2000, 0.5)  # a constant forecast, deliberately uninformative
    diff, se = fc.paired_brier_se(_variant(idx, worse, y), _variant(idx, p, y), "validation")
    assert diff > 0            # positive = the first model is worse
    assert se > 0
    assert diff / se > 3       # and clearly so


def test_extracted_bootstrap_matches_the_interval_version():
    """block_bootstrap was refactored to call block_bootstrap_estimates; they must agree."""
    rng = np.random.default_rng(7)
    values = np.column_stack([rng.uniform(size=1500), rng.integers(0, 2, size=1500).astype(float)])
    stat = lambda a: brier_score(a[:, 0], a[:, 1])
    point, lo, hi = block_bootstrap(values, stat, block=48, n_boot=200, seed=11)
    point2, est = block_bootstrap_estimates(values, stat, block=48, n_boot=200, seed=11)
    assert point == point2
    assert lo == float(np.percentile(est, 2.5))
    assert hi == float(np.percentile(est, 97.5))


def test_bootstrap_estimates_returns_nothing_when_the_sample_is_too_short():
    values = np.column_stack([np.linspace(0, 1, 40), np.zeros(40)])
    point, est = block_bootstrap_estimates(values, lambda a: float(a[:, 0].mean()), block=48, n_boot=50)
    assert len(est) == 0
    assert point == pytest.approx(0.5, abs=0.02)
