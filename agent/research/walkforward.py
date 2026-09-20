"""
Walk-forward (chronological) validation for anything that is FITTED (Phases 9-11).

Why this exists: hourly predictions with an H-hour outcome window overlap. A model
trained on hours up to time T has, in its last H training rows, outcomes that occur
AFTER T -- inside the block it is about to be tested on. Ordinary train/test splitting
therefore leaks the test period's future into training. The remedy is structural:

  purge    the last H hours before a test block are dropped from training, so every
           training label was fully realised before the test block's first cutoff
  embargo  an extra margin after the purge (default 24h), because features and labels
           near the boundary are serially correlated and the volatility-scaled label
           thresholds themselves use trailing completed returns
  calib    an optional slice at the end of each training range (after its own purge)
           reserved for fitting a probability calibrator that must never see test rows

Layouts: EXPANDING (train on everything from the start) or ROLLING (train on the last
`rolling_days`). Test blocks are consecutive, non-overlapping and cover the evaluation
range exactly once, so concatenating the per-fold out-of-sample predictions gives one
continuous out-of-sample series.

The runner only hands a model the rows it is allowed to see: fit() receives training
rows, calibrate() receives calibration rows, predict() receives test rows. It also
asserts the time gaps on every fold, so a mis-built fold fails loudly.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

import numpy as np
import pandas as pd

HOUR = pd.Timedelta(hours=1)


@dataclass(frozen=True)
class Fold:
    index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp  # exclusive; last training reference hour is train_end - 1h
    calib_start: pd.Timestamp | None  # calibration slice [calib_start, calib_end), None if unused
    calib_end: pd.Timestamp | None
    test_start: pd.Timestamp  # inclusive
    test_end: pd.Timestamp  # exclusive


@dataclass(frozen=True)
class WalkForwardSpec:
    horizon_hours: int
    scheme: str = "expanding"  # "expanding" | "rolling"
    min_train_days: int = 365
    test_block_days: int = 90
    embargo_hours: int = 24
    calib_days: int = 0  # 0 = no calibration slice
    rolling_days: int = 730

    @property
    def purge(self) -> pd.Timedelta:
        # A training label at reference hour s is realised at s + H + 1h (its outcome candle closes).
        # It must be realised before the first test cutoff (test_start + 1h): s + H + 1h <= test_start + 1h
        # => s <= test_start - H. The last usable training hour is test_start - H - embargo - 1h.
        return pd.Timedelta(hours=self.horizon_hours + self.embargo_hours)

    def __post_init__(self):
        if self.scheme not in ("expanding", "rolling"):
            raise ValueError(f"unknown scheme {self.scheme!r}")
        if self.horizon_hours < 1 or self.test_block_days < 1 or self.min_train_days < 1:
            raise ValueError("horizon, test block and minimum training length must be positive")


def make_folds(times: pd.DatetimeIndex, spec: WalkForwardSpec, eval_start: pd.Timestamp | None = None) -> list[Fold]:
    """
    Deterministic folds over the hourly index `times` (sorted, tz-aware). Test blocks start at
    `eval_start` (default: data start + min_train_days + purge) and step by test_block_days.
    """
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("times must be sorted and unique")
    data_start, data_end = times[0], times[-1] + HOUR
    # The first test block starts after: the minimum training range, its purge, and (if used)
    # the calibration slice with its own purge -- so the first fold's fit range is min_train_days.
    lead = pd.Timedelta(days=spec.min_train_days) + spec.purge
    if spec.calib_days:
        lead += pd.Timedelta(days=spec.calib_days) + spec.purge
    first_test = eval_start or (data_start + lead)
    folds: list[Fold] = []
    test_start = first_test
    i = 0
    while test_start < data_end:
        test_end = min(test_start + pd.Timedelta(days=spec.test_block_days), data_end)
        train_end = test_start - spec.purge  # exclusive
        train_start = data_start if spec.scheme == "expanding" else max(data_start, train_end - pd.Timedelta(days=spec.rolling_days))
        calib_start = calib_end = None
        if spec.calib_days:
            # calibration slice is the tail of the training range; its own purge separates it from the fit rows
            calib_end = train_end
            calib_start = calib_end - pd.Timedelta(days=spec.calib_days)
            train_end = calib_start - spec.purge
        if train_end - train_start < pd.Timedelta(days=spec.min_train_days):
            raise ValueError(f"fold {i}: training range shorter than min_train_days")
        folds.append(Fold(i, train_start, train_end, calib_start, calib_end, test_start, test_end))
        test_start = test_end
        i += 1
    return folds


class Model(Protocol):
    def fit(self, X: pd.DataFrame, y: np.ndarray) -> None: ...
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray: ...  # P(positive class) per row


class Calibrator(Protocol):
    def fit(self, p: np.ndarray, y: np.ndarray) -> None: ...
    def transform(self, p: np.ndarray) -> np.ndarray: ...


def _slice(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return df[(df.index >= start) & (df.index < end)]


def check_fold(fold: Fold, spec: WalkForwardSpec, train: pd.DataFrame, calib: pd.DataFrame | None, test: pd.DataFrame) -> None:
    """Loud guard rails: every fitted row's label is realised before the first test cutoff."""
    if len(train) == 0 or len(test) == 0:
        raise ValueError(f"fold {fold.index}: empty train or test")
    last_fit_hour = train.index.max()
    if calib is not None and len(calib):
        if calib.index.min() < last_fit_hour + spec.purge + HOUR:
            raise ValueError(f"fold {fold.index}: calibration slice too close to training rows")
        last_fit_hour = calib.index.max()
    # The last fitted row s must satisfy s + purge < test_start, i.e. its label (realised at
    # s + H + 1h) closed before the first test cutoff, with the embargo on top.
    if last_fit_hour + spec.purge >= fold.test_start:
        raise ValueError(f"fold {fold.index}: training/calibration rows reach into the purge gap before the test block")
    if test.index.min() < fold.test_start or test.index.max() >= fold.test_end:
        raise ValueError(f"fold {fold.index}: test rows outside the test block")
    if len(set(train.index) & set(test.index)):
        raise ValueError(f"fold {fold.index}: train/test overlap")


def run_walk_forward(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    make_model,
    spec: WalkForwardSpec,
    folds: list[Fold] | None = None,
    make_calibrator=None,
    eval_start: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, list[dict]]:
    """
    df: indexed by reference hour (tz-aware, sorted); label_col holds 0/1 (NaN = no label).
    Returns (out-of-sample predictions indexed by hour with columns fold, p_raw, p, y;
             per-fold diagnostics).
    """
    if not df.index.is_monotonic_increasing:
        raise ValueError("df must be sorted by time")
    folds = folds or make_folds(df.index, spec, eval_start)
    usable = df[feature_cols + [label_col]].dropna()
    preds, diagnostics = [], []
    for fold in folds:
        train = _slice(usable, fold.train_start, fold.train_end)
        calib = _slice(usable, fold.calib_start, fold.calib_end) if fold.calib_start is not None else None
        test = _slice(usable, fold.test_start, fold.test_end)
        if len(test) == 0:
            continue
        check_fold(fold, spec, train, calib, test)

        model = make_model()
        model.fit(train[feature_cols], train[label_col].to_numpy(dtype=float))
        p_raw = np.asarray(model.predict_proba(test[feature_cols]), dtype=float)
        p = p_raw
        if make_calibrator is not None and calib is not None and len(calib):
            cal = make_calibrator()
            cal.fit(np.asarray(model.predict_proba(calib[feature_cols]), dtype=float), calib[label_col].to_numpy(dtype=float))
            p = np.asarray(cal.transform(p_raw), dtype=float)
        out = pd.DataFrame({"fold": fold.index, "p_raw": p_raw, "p": p, "y": test[label_col].to_numpy(dtype=float)}, index=test.index)
        preds.append(out)
        diagnostics.append({
            "fold": fold.index, "train_rows": len(train), "calib_rows": 0 if calib is None else len(calib), "test_rows": len(test),
            "train_range": [str(train.index.min()), str(train.index.max())], "test_range": [str(test.index.min()), str(test.index.max())],
            "gap_hours_between_last_fit_row_and_test_start": float((fold.test_start - (calib.index.max() if calib is not None and len(calib) else train.index.max())) / HOUR),
        })
    if not preds:
        raise ValueError("no folds produced predictions")
    return pd.concat(preds).sort_index(), diagnostics
