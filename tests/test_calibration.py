"""
Calibrators (Phase 11) are tested like the rest of the research bench:

- a calibrator only ever sees the purged calibration slice (proved with a recording calibrator);
- a deliberately over-confident model is corrected on synthetic data (ECE falls, ranking kept);
- Platt and isotonic are monotone (they can never reverse the model's ordering);
- a calibrator is refused without a calibration slice.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.metrics import reliability_table
from agent.research.model_test import IsotonicCalibrator, PlattCalibrator
from agent.research.walkforward import WalkForwardSpec, run_walk_forward

START = pd.Timestamp(datetime(2020, 1, 1, tzinfo=timezone.utc))


def _frame(n: int, seed: int = 0) -> pd.DataFrame:
    """A feature that carries real information about y (a latent logistic model)."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    p_true = 1 / (1 + np.exp(-1.0 * x))
    y = (rng.uniform(size=n) < p_true).astype(float)
    return pd.DataFrame({"x": x, "y": y}, index=pd.date_range(START, periods=n, freq="h", tz="UTC"))


class OverconfidentModel:
    """Knows the true direction of the effect but exaggerates it 3x -- probabilities too extreme."""

    def fit(self, X, y):
        pass

    def predict_proba(self, X):
        return 1 / (1 + np.exp(-3.0 * X["x"].to_numpy()))


class RecordingCalibrator:
    def __init__(self, seen):
        self.seen = seen

    def fit(self, p, y):
        self.seen.append(len(p))

    def transform(self, p):
        return p


def test_calibrator_sees_only_the_calibration_slice():
    df = _frame(24 * 500)
    spec = WalkForwardSpec(horizon_hours=1, min_train_days=200, test_block_days=60, calib_days=30, embargo_hours=24)
    seen: list[int] = []
    preds, diag = run_walk_forward(df, ["x"], "y", OverconfidentModel, spec, make_calibrator=lambda: RecordingCalibrator(seen))
    assert len(seen) == len(diag)
    for n_seen, d in zip(seen, diag):
        assert n_seen == d["calib_rows"] == 30 * 24  # exactly the slice, nothing from train or test


@pytest.mark.parametrize("make", [PlattCalibrator, IsotonicCalibrator])
def test_calibration_corrects_overconfidence_and_keeps_ranking(make):
    df = _frame(24 * 700, seed=1)
    spec = WalkForwardSpec(horizon_hours=1, min_train_days=200, test_block_days=60, calib_days=45, embargo_hours=24)
    preds, _ = run_walk_forward(df, ["x"], "y", OverconfidentModel, spec, make_calibrator=make)
    y = preds["y"].to_numpy()
    _, ece_raw, _ = reliability_table(preds["p_raw"].to_numpy(), y)
    _, ece_cal, _ = reliability_table(preds["p"].to_numpy(), y)
    assert ece_raw > 0.08  # the raw model really is over-confident
    assert ece_cal < ece_raw / 2  # and the calibrator fixes most of it
    # ranking preserved: same Spearman correlation with y up to isotonic ties
    rank_raw = pd.Series(preds["p_raw"].to_numpy()).rank().corr(pd.Series(y).rank())
    rank_cal = pd.Series(preds["p"].to_numpy()).rank().corr(pd.Series(y).rank())
    assert abs(rank_raw - rank_cal) < 0.03


@pytest.mark.parametrize("make", [PlattCalibrator, IsotonicCalibrator])
def test_calibrators_are_monotone(make):
    rng = np.random.default_rng(2)
    p = rng.uniform(0.01, 0.99, size=3000)
    y = (rng.uniform(size=3000) < p**2).astype(float)  # observed frequency is a monotone function of p
    cal = make()
    cal.fit(p, y)
    grid = np.linspace(0.01, 0.99, 200)
    out = cal.transform(grid)
    assert np.all(np.diff(out) >= -1e-12)
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_calibrator_refused_without_slice():
    from agent.research.model_test import run

    with pytest.raises(ValueError, match="calibration slice"):
        run("TEST", "logistic", 1, [], "expanding", 0, 0.1, ["trend_score"], "x", "direction", None, None, "platt")
