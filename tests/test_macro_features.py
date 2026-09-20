"""
Macro daily bars become visible at 22:00 UTC on their trading date, never earlier; the
last known close persists over weekends; the past never depends on the future.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.features import RESERVED_PREFIXES
from agent.research.macro import MACRO_FEATURES, SERIES, macro_features

START = datetime(2026, 3, 2, tzinfo=timezone.utc)  # a Monday


def _grid(hours: int) -> pd.DatetimeIndex:
    return pd.date_range(START, periods=hours, freq="h", tz="UTC")


def _daily(values_by_date: dict) -> pd.DataFrame:
    idx = pd.DatetimeIndex(sorted(values_by_date))
    df = pd.DataFrame(index=idx)
    for name in SERIES:
        df[name] = [values_by_date[d].get(name, np.nan) for d in idx]
    return df


def _weekdays(n: int, start=datetime(2026, 2, 16)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_no_feature_uses_a_reserved_prefix():
    assert all(not f.startswith(RESERVED_PREFIXES) for f in MACRO_FEATURES)


def test_bar_for_today_is_invisible_before_22_utc_and_visible_after():
    days = _weekdays(12)
    values = {d: {n: 100.0 + i for n in SERIES} for i, d in enumerate(days)}
    daily = _daily(values)
    grid = _grid(24 * 3)
    feats = macro_features(grid, daily)
    monday = START  # 2026-03-02, which is days[10]; its bar becomes visible at 22:00 UTC
    idx_mon = days.index(datetime(2026, 3, 2))
    # Reference hour 20:00 (cutoff 21:00): Monday's close not yet known -> Friday's close is the latest.
    t_20 = monday + timedelta(hours=20)
    assert feats.loc[t_20, "spx_ret_1d"] == pytest.approx((100 + idx_mon - 1) / (100 + idx_mon - 2) - 1)
    # Reference hour 21:00 (cutoff 22:00): Monday's close is known.
    t_21 = monday + timedelta(hours=21)
    assert feats.loc[t_21, "spx_ret_1d"] == pytest.approx((100 + idx_mon) / (100 + idx_mon - 1) - 1)
    assert feats.loc[t_21, "macro_staleness_h"] == 0.0
    assert feats.loc[t_20, "macro_staleness_h"] == pytest.approx(21 + 24 * 3 - 22 + 0)  # Friday 22:00 -> Monday 21:00 cutoff: 71h


def test_yield_uses_differences_not_ratios():
    days = _weekdays(8)
    values = {d: {n: (1.0 + 0.1 * i if n == "tnx" else 50.0) for n in SERIES} for i, d in enumerate(days)}
    feats = macro_features(_grid(24), _daily(values))
    t = START + timedelta(hours=23)
    assert feats.loc[t, "tnx_chg_1d"] == pytest.approx(0.1)
    assert feats.loc[t, "spx_ret_1d"] == pytest.approx(0.0)


def test_garbling_future_bars_leaves_the_past_unchanged():
    days = _weekdays(40, start=datetime(2026, 1, 5))
    rng = np.random.default_rng(3)
    values = {d: {n: float(v) for n, v in zip(SERIES, 100 + rng.normal(size=len(SERIES)) * 5 + i)} for i, d in enumerate(days)}
    daily = _daily(values)
    grid = pd.date_range(datetime(2026, 1, 20, tzinfo=timezone.utc), periods=24 * 20, freq="h", tz="UTC")
    base = macro_features(grid, daily)

    k = 24 * 10
    cutoff_k = grid[k] + timedelta(hours=1)
    garbled = daily.copy()
    garbled.loc[pd.DatetimeIndex(garbled.index).tz_localize("UTC") + pd.Timedelta(hours=22) > cutoff_k] = 1e6
    tampered = macro_features(grid, garbled)
    pd.testing.assert_frame_equal(base.loc[: grid[k]], tampered.loc[: grid[k]])
