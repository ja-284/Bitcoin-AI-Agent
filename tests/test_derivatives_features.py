"""
Derivatives features must use only settlements/candles visible at the cutoff (t + 1h):
a settlement exactly at the cutoff counts; one second later does not. And, as for every
research feature, garbling the future must leave the past untouched.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.derivatives import DERIVATIVES_FEATURES, derivatives_features
from agent.research.features import RESERVED_PREFIXES

START = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _grid(hours: int) -> pd.DatetimeIndex:
    return pd.date_range(START, periods=hours, freq="h", tz="UTC")


def _funding(times_values: list[tuple[datetime, float]]) -> pd.Series:
    return pd.Series([v for _, v in times_values], index=pd.DatetimeIndex([t for t, _ in times_values], tz="UTC"))


def _premium(grid: pd.DatetimeIndex, closes) -> pd.DataFrame:
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes}, index=grid)


def test_no_feature_uses_a_reserved_prefix():
    assert all(not f.startswith(RESERVED_PREFIXES) for f in DERIVATIVES_FEATURES)


def test_settlement_at_the_cutoff_is_visible_but_one_second_later_is_not():
    grid = _grid(48)
    # Settlements at 08:00 and 16:00 on day 1 -- and one at 16:00:01 that must be invisible at the 16:00 cutoff.
    funding = _funding([
        (START + timedelta(hours=8), 0.001),
        (START + timedelta(hours=16), 0.002),
    ])
    feats = derivatives_features(grid, funding, _premium(grid, np.zeros(48)))
    t_15 = START + timedelta(hours=15)  # cutoff 16:00 -> the 16:00 settlement counts
    t_14 = START + timedelta(hours=14)  # cutoff 15:00 -> only the 08:00 settlement is visible
    assert feats.loc[t_15, "funding_last"] == pytest.approx(0.002)
    assert feats.loc[t_14, "funding_last"] == pytest.approx(0.001)
    assert np.isnan(feats.loc[START + timedelta(hours=6), "funding_last"])  # nothing settled yet

    late = _funding([(START + timedelta(hours=8), 0.001), (START + timedelta(hours=16, seconds=1), 0.002)])
    feats_late = derivatives_features(grid, late, _premium(grid, np.zeros(48)))
    assert feats_late.loc[t_15, "funding_last"] == pytest.approx(0.001)  # 16:00:01 is after the 16:00 cutoff


def test_funding_windows_use_the_last_k_visible_settlements():
    grid = _grid(24 * 10)
    times = [START + timedelta(hours=8 * i) for i in range(1, 30)]
    funding = _funding([(t, float(i)) for i, t in enumerate(times, start=1)])  # values 1, 2, 3, ...
    feats = derivatives_features(grid, funding, _premium(grid, np.zeros(len(grid))))
    t = START + timedelta(hours=8 * 25 - 1)  # cutoff = 25th settlement time
    assert feats.loc[t, "funding_last"] == 25
    assert feats.loc[t, "funding_mean_3"] == pytest.approx((23 + 24 + 25) / 3)
    assert feats.loc[t, "funding_sum_21"] == pytest.approx(sum(range(5, 26)))
    early = START + timedelta(hours=8 * 2 - 1)  # only 2 settlements visible: mean_3 and sum_21 unavailable
    assert np.isnan(feats.loc[early, "funding_mean_3"]) and np.isnan(feats.loc[early, "funding_sum_21"])


def test_premium_uses_candle_closed_at_the_cutoff_and_trailing_means():
    grid = _grid(200)
    closes = np.arange(200, dtype=float)
    feats = derivatives_features(grid, _funding([(START, 0.0)]), _premium(grid, closes))
    t = grid[100]
    assert feats.loc[t, "premium_close"] == 100.0
    assert feats.loc[t, "premium_mean_24"] == pytest.approx(np.mean(closes[77:101]))
    assert np.isnan(feats.loc[t, "premium_mean_168"])  # only 101 candles so far: unavailable, not approximated
    t2 = grid[180]
    assert feats.loc[t2, "premium_mean_168"] == pytest.approx(np.mean(closes[13:181]))
    assert np.isnan(feats.loc[grid[10], "premium_mean_24"])


def test_garbling_the_future_leaves_the_past_unchanged():
    grid = _grid(400)
    times = [START + timedelta(hours=8 * i) for i in range(1, 50)]
    funding = _funding([(t, np.sin(i)) for i, t in enumerate(times)])
    prem = _premium(grid, np.cos(np.arange(400) / 7.0))
    base = derivatives_features(grid, funding, prem)

    k = 250  # garble everything after hour k
    cutoff_k = grid[k]
    garbled_funding = funding.copy()
    garbled_funding[garbled_funding.index > cutoff_k + timedelta(hours=1)] = 99.0
    garbled_prem = prem.copy()
    garbled_prem.loc[garbled_prem.index > cutoff_k] = 99.0
    tampered = derivatives_features(grid, garbled_funding, garbled_prem)
    pd.testing.assert_frame_equal(base.loc[:cutoff_k], tampered.loc[:cutoff_k])
