import numpy as np
import pytest

from agent.research.metrics import (
    block_bootstrap,
    brier_score,
    classification_report,
    log_loss,
    reliability_table,
    signal_edge,
    wilson_interval,
)


def test_classification_report_known_values():
    y_true = ["UP", "UP", "DOWN", "DOWN", "NEUTRAL", "NEUTRAL"]
    y_pred = ["UP", "DOWN", "DOWN", "DOWN", "UP", "NEUTRAL"]
    rep = classification_report(y_true, y_pred, ["UP", "NEUTRAL", "DOWN"])
    assert rep.n == 6
    assert rep.accuracy == pytest.approx(4 / 6)
    assert rep.per_class["UP"]["recall"] == pytest.approx(0.5)
    assert rep.per_class["UP"]["precision"] == pytest.approx(0.5)  # predicted UP twice, right once
    assert rep.per_class["DOWN"]["recall"] == pytest.approx(1.0)
    assert rep.per_class["DOWN"]["precision"] == pytest.approx(2 / 3)
    assert rep.balanced_accuracy == pytest.approx((0.5 + 0.5 + 1.0) / 3)
    assert rep.confusion["UP"]["DOWN"] == 1
    assert rep.prediction_distribution["DOWN"] == pytest.approx(0.5)


def test_brier_and_log_loss_reference_points():
    y = np.array([1, 0, 1, 0])
    assert brier_score(np.full(4, 0.5), y) == pytest.approx(0.25)  # "always 50%" scores 0.25
    assert brier_score(np.array([1, 0, 1, 0]), y) == pytest.approx(0.0)
    assert log_loss(np.full(4, 0.5), y) == pytest.approx(np.log(2))


def test_wilson_interval_contains_the_point_estimate_and_narrows_with_n():
    lo, hi = wilson_interval(7, 10)
    assert lo < 0.7 < hi
    lo_big, hi_big = wilson_interval(700, 1000)
    assert (hi_big - lo_big) < (hi - lo)
    empty_lo, empty_hi = wilson_interval(0, 0)
    assert np.isnan(empty_lo) and np.isnan(empty_hi)


def test_reliability_table_and_ece():
    p = np.array([0.1] * 100 + [0.9] * 100)
    y = np.array([0] * 90 + [1] * 10 + [1] * 70 + [0] * 30)  # 10% observed vs 0.1 stated; 70% observed vs 0.9 stated
    buckets, ece, mce = reliability_table(p, y)
    assert [b.n for b in buckets] == [100, 100]
    assert buckets[0].observed == pytest.approx(0.10)
    assert buckets[1].observed == pytest.approx(0.70)
    assert ece == pytest.approx(0.5 * 0.0 + 0.5 * 0.2)
    assert mce == pytest.approx(0.2)
    assert buckets[1].ci_low < 0.7 < buckets[1].ci_high


def test_block_bootstrap_interval_covers_the_mean_of_iid_noise():
    rng = np.random.default_rng(1)
    values = rng.normal(0.0, 1.0, size=5000)
    point, lo, hi = block_bootstrap(values, np.mean, block=24, n_boot=300, seed=2)
    assert lo < point < hi
    assert lo < 0.0 < hi  # true mean is zero


def test_block_bootstrap_too_short_returns_nan_interval():
    point, lo, hi = block_bootstrap(np.arange(10), np.mean, block=24)
    assert point == 4.5 and np.isnan(lo) and np.isnan(hi)


def test_signal_edge():
    s = np.array(["BUY", "BUY", "SELL", "HOLD", "SELL"])
    r = np.array([0.02, 0.00, -0.01, 0.05, 0.03])
    assert signal_edge(s, r) == pytest.approx(0.01 - 0.01)
    assert np.isnan(signal_edge(np.array(["BUY"]), np.array([0.1])))
