"""
Research features are computed over the whole series at once, which is exactly where a
future value can slip in by accident (a centred window, a forward shift). So: compute
on the real series, garble everything after hour k, recompute, and require every value
at or before k to be identical. Also: gaps must blank out windows, never be bridged.
"""

import math
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.features import REGIME_FEATURES, VOLATILITY_FEATURES, all_features, bars_to_frame
from agent.shared.types import PriceBar
from tests.test_point_in_time import synthetic_bars

N = 5200  # longest window is 4800h


def _garble_after(bars, k):
    return bars[:k] + [PriceBar(b.as_of, 1e9, 2e9, 0.5e9, 1.5e9, 1e12, b.source) for b in bars[k:]]


def test_all_features_depend_only_on_the_past():
    bars = synthetic_bars(N)
    base = all_features(bars)
    for k in (4900, 5000, 5150):
        tampered = all_features(_garble_after(bars, k))
        cutoff = bars[k - 1].as_of
        a, b = base.loc[:cutoff], tampered.loc[:cutoff]
        pd.testing.assert_frame_equal(a, b)


def test_every_feature_has_values_once_its_window_is_full():
    feats = all_features(synthetic_bars(N))
    for col in VOLATILITY_FEATURES + REGIME_FEATURES:
        assert feats[col].iloc[-1] == feats[col].iloc[-1], f"{col} is NaN at the end"  # not NaN
        assert feats[col].iloc[0] != feats[col].iloc[0], f"{col} should be NaN before its window is full"


def test_gap_blanks_windows_that_touch_it_and_is_not_bridged():
    bars = synthetic_bars(400)
    del bars[200:205]  # five missing hours
    frame = bars_to_frame(bars)
    assert len(frame) == 400  # grid is complete
    assert frame["close"].isna().sum() == 5
    feats = all_features(bars)
    gap_start = bars[199].as_of + timedelta(hours=1)
    # rv_24 at the first hour after the gap must be NaN (its 24h window contains the gap)...
    assert np.isnan(feats.loc[bars[200].as_of, "rv_24"])
    # ...and valid again 24 full hours after the gap closed.
    assert not np.isnan(feats.loc[bars[200].as_of + timedelta(hours=24), "rv_24"])
    assert feats.loc[gap_start:gap_start + timedelta(hours=4)].isna().all().all()


def test_known_values():
    # Constant price: all volatility measures are zero, returns are zero, distances to averages are zero.
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [PriceBar(start + timedelta(hours=i), 100.0, 100.0, 100.0, 100.0, 1.0, "t") for i in range(N)]
    feats = all_features(bars).iloc[-1]
    for col in ("rv_24", "rv_168", "rv_720", "tr_mean_14_rel", "bb_width_20", "parkinson_24", "ret_168h", "ret_720h", "ret_2160h", "dist_sma_1200", "dist_sma_4800"):
        assert feats[col] == pytest.approx(0.0, abs=1e-12), col
    # A steady 1%/hour rise: 168h return = 1.01**168 - 1.
    bars = [PriceBar(start + timedelta(hours=i), 100 * 1.01**i, 100 * 1.01**i, 100 * 1.01**i, 100 * 1.01**i, 1.0, "t") for i in range(N)]
    assert all_features(bars).iloc[-1]["ret_168h"] == pytest.approx(1.01**168 - 1)
