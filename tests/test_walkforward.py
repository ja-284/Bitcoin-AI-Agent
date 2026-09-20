"""
The validation framework is research infrastructure and is tested like one.

Covered: deterministic chronological folds that cover the range exactly once; the
purge/embargo gap between the last fitted row and the first test row; calibration
slices that sit after their own purge; the model never receives test rows (proved with
a model that records what it saw, and with a memorising model whose out-of-sample
accuracy must be at chance); the overlapping-label leak the purge exists to prevent is
demonstrated on synthetic data; a violated fold is rejected loudly.
"""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.walkforward import HOUR, Fold, WalkForwardSpec, check_fold, make_folds, run_walk_forward

START = pd.Timestamp(datetime(2020, 1, 1, tzinfo=timezone.utc))


def _hours(n: int) -> pd.DatetimeIndex:
    return pd.date_range(START, periods=n, freq="h", tz="UTC")


def _overlapping_label_frame(n: int, horizon: int, seed: int = 0) -> pd.DataFrame:
    """Labels built from the NEXT `horizon` hours of noise -> strongly autocorrelated over `horizon` hours."""
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=n + horizon)
    fwd = np.array([noise[i + 1 : i + 1 + horizon].sum() for i in range(n)])
    df = pd.DataFrame({"x": rng.normal(size=n), "y": (fwd > 0).astype(float)}, index=_hours(n))
    return df


class RecordingModel:
    """Fits nothing; records the time range it was shown."""

    def __init__(self):
        self.seen_fit = []
        self.seen_predict = []

    def fit(self, X, y):
        self.seen_fit.append((X.index.min(), X.index.max()))

    def predict_proba(self, X):
        self.seen_predict.append((X.index.min(), X.index.max()))
        return np.full(len(X), 0.5)


class MemorisingModel:
    """Looks labels up by timestamp. Can only score above chance if test rows were in training."""

    def fit(self, X, y):
        self.table = dict(zip(X.index, y))

    def predict_proba(self, X):
        return np.array([self.table.get(t, 0.5) for t in X.index])


class LastLabelModel:
    """Predicts the most recent training label for every test row -- exploits label autocorrelation if the gap is too small."""

    def fit(self, X, y):
        self.last = float(y[-1])

    def predict_proba(self, X):
        return np.full(len(X), self.last)


def test_folds_are_chronological_deterministic_and_cover_the_range_once():
    times = _hours(24 * 900)
    spec = WalkForwardSpec(horizon_hours=24, min_train_days=365, test_block_days=90)
    folds = make_folds(times, spec)
    again = make_folds(times, spec)
    assert folds == again  # deterministic
    assert len(folds) > 1
    for a, b in zip(folds, folds[1:]):
        assert a.test_end == b.test_start  # consecutive, no gaps, no overlap
        assert a.train_end < a.test_start and b.train_end < b.test_start
    assert folds[-1].test_end == times[-1] + HOUR
    covered = sum((f.test_end - f.test_start for f in folds), pd.Timedelta(0))
    assert covered == folds[-1].test_end - folds[0].test_start


def test_gap_between_last_fitted_row_and_test_start_equals_purge():
    df = _overlapping_label_frame(24 * 600, horizon=24)
    spec = WalkForwardSpec(horizon_hours=24, min_train_days=200, test_block_days=60, embargo_hours=24)
    model = RecordingModel()
    preds, diag = run_walk_forward(df, ["x"], "y", lambda: model, spec)
    for d in diag:
        # last fitted row is at test_start - purge - 1h (its own hour counts): gap = horizon + embargo + 1
        assert d["gap_hours_between_last_fit_row_and_test_start"] == 24 + 24 + 1
    for (fit_min, fit_max), (pred_min, pred_max) in zip(model.seen_fit, model.seen_predict):
        assert fit_max + spec.purge < pred_min  # last training label realised before the first test cutoff
    assert preds.index.is_monotonic_increasing and not preds.index.has_duplicates


def test_expanding_vs_rolling_training_ranges():
    times = _hours(24 * 1500)
    exp = make_folds(times, WalkForwardSpec(24, scheme="expanding", min_train_days=365, test_block_days=90))
    roll = make_folds(times, WalkForwardSpec(24, scheme="rolling", min_train_days=365, test_block_days=90, rolling_days=400))
    assert all(f.train_start == times[0] for f in exp)
    assert all((f.train_end - f.train_start) <= pd.Timedelta(days=400) for f in roll)
    assert [f.test_start for f in exp] == [f.test_start for f in roll]  # identical test blocks -> comparable


def test_calibration_slice_sits_after_its_own_purge_and_before_test():
    times = _hours(24 * 900)
    spec = WalkForwardSpec(horizon_hours=24, min_train_days=300, test_block_days=90, calib_days=30, embargo_hours=24)
    for f in make_folds(times, spec):
        assert f.calib_start is not None
        assert f.train_end + spec.purge == f.calib_start  # purge between fit rows and calibration rows
        assert f.calib_end + spec.purge == f.test_start  # purge between calibration rows and test rows


def test_memorising_model_scores_at_chance_out_of_sample():
    df = _overlapping_label_frame(24 * 700, horizon=6, seed=3)
    spec = WalkForwardSpec(horizon_hours=6, min_train_days=200, test_block_days=60)
    preds, _ = run_walk_forward(df, ["x"], "y", MemorisingModel, spec)
    assert (preds["p"] == 0.5).all()  # never found a test timestamp in its table


def test_purge_removes_the_overlapping_label_leak():
    horizon = 24
    df = _overlapping_label_frame(24 * 800, horizon=horizon, seed=5)
    # The leak, shown directly on the data: labels a few hours apart agree far more than chance...
    y = df["y"].to_numpy()
    agree_close = np.mean(y[:-1] == y[1:])
    agree_far = np.mean(y[: -(horizon + 1)] == y[horizon + 1 :])
    assert agree_close > 0.85 and abs(agree_far - 0.5) < 0.05
    # ...so a model that carries the last training label forward would look skilled on the first
    # test hours WITHOUT a gap. With the framework's purge, its out-of-sample accuracy is chance.
    spec = WalkForwardSpec(horizon_hours=horizon, min_train_days=100, test_block_days=30, embargo_hours=0)
    preds, _ = run_walk_forward(df, ["x"], "y", LastLabelModel, spec)
    first_hours = preds.groupby("fold").head(6)
    acc = np.mean((first_hours["p"] > 0.5) == (first_hours["y"] > 0.5))
    assert abs(acc - 0.5) < 0.12, f"leak: accuracy on first test hours {acc:.2f}"


def test_violated_fold_is_rejected():
    df = _overlapping_label_frame(24 * 400, horizon=24)
    spec = WalkForwardSpec(horizon_hours=24, min_train_days=100, test_block_days=30)
    ok = make_folds(df.index, spec)[0]
    bad = Fold(0, ok.train_start, ok.test_start - HOUR * 5, None, None, ok.test_start, ok.test_end)  # only a 5h gap
    train = df[(df.index >= bad.train_start) & (df.index < bad.train_end)]
    test = df[(df.index >= bad.test_start) & (df.index < bad.test_end)]
    with pytest.raises(ValueError, match="purge gap"):
        check_fold(bad, spec, train, None, test)


def test_spec_validation():
    with pytest.raises(ValueError):
        WalkForwardSpec(horizon_hours=24, scheme="random")
    with pytest.raises(ValueError):
        WalkForwardSpec(horizon_hours=0)
