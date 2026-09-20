"""
On-chain daily values are visible only from D+1 06:00 UTC; difficulty adjustments only
from their block time; the past never depends on the future.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.features import RESERVED_PREFIXES
from agent.research.onchain import KNOWN_AFTER, ONCHAIN_FEATURES, SERIES, onchain_features

D0 = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _daily(n: int, start=D0, base=1000.0) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    return pd.DataFrame({k: base + np.arange(n) * (i + 1) for i, k in enumerate(SERIES)}, index=idx)


def _difficulty(adjustments: list[tuple[datetime, float]]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([t for t, _ in adjustments], tz="UTC")
    return pd.DataFrame({"height": np.arange(len(adjustments)), "difficulty": 1.0, "change_factor": [c for _, c in adjustments]}, index=idx)


def test_no_feature_uses_a_reserved_prefix():
    assert all(not f.startswith(RESERVED_PREFIXES) for f in ONCHAIN_FEATURES)


def test_day_value_is_invisible_before_next_day_0600_utc_and_visible_after():
    daily = _daily(40)
    day = D0 + timedelta(days=35)  # a day well inside the data
    grid = pd.date_range(day, periods=48, freq="h", tz="UTC")
    feats = onchain_features(grid, daily, _difficulty([(D0, 1.0)]))
    # Reference hour D+1 04:00 (cutoff 05:00): day D not yet known; the 7d change uses day D-1 vs D-8.
    t_before = day + timedelta(days=1, hours=4)
    t_after = day + timedelta(days=1, hours=5)  # cutoff 06:00: day D known
    v = daily["addr"]
    def chg(d_last, d_prev):
        return v[d_last] / v[d_prev] - 1
    assert feats.loc[t_before, "addr_chg_7d"] == pytest.approx(chg(day - timedelta(days=1), day - timedelta(days=8)))
    assert feats.loc[t_after, "addr_chg_7d"] == pytest.approx(chg(day, day - timedelta(days=7)))
    assert feats.loc[t_after, "onchain_staleness_h"] == 0.0
    assert feats.loc[t_before, "onchain_staleness_h"] == pytest.approx(23.0)
    assert KNOWN_AFTER == timedelta(hours=30)


def test_difficulty_adjustment_known_only_from_its_block_time():
    daily = _daily(40)
    adj_time = D0 + timedelta(days=20, hours=13, minutes=37)
    diff = _difficulty([(D0 + timedelta(days=6), 1.02), (adj_time, 0.95)])
    grid = pd.date_range(D0 + timedelta(days=20), periods=24, freq="h", tz="UTC")
    feats = onchain_features(grid, daily, diff)
    t_12 = D0 + timedelta(days=20, hours=12)  # cutoff 13:00 < 13:37: old adjustment (+2%) still current
    t_13 = D0 + timedelta(days=20, hours=13)  # cutoff 14:00 > 13:37: new adjustment (-5%) visible
    assert feats.loc[t_12, "difficulty_adj_last_pct"] == pytest.approx(2.0)
    assert feats.loc[t_13, "difficulty_adj_last_pct"] == pytest.approx(-5.0)


def test_garbling_the_future_leaves_the_past_unchanged():
    rng = np.random.default_rng(5)
    daily = _daily(120)
    daily = daily * (1 + rng.normal(0, 0.05, size=daily.shape)).clip(0.5, 1.5)
    diff = _difficulty([(D0 + timedelta(days=d), 1 + rng.normal(0, 0.03)) for d in range(0, 120, 14)])
    grid = pd.date_range(D0 + timedelta(days=40), periods=24 * 60, freq="h", tz="UTC")
    base = onchain_features(grid, daily, diff)

    k = 24 * 30
    cutoff_k = grid[k] + timedelta(hours=1)
    garbled = daily.copy()
    garbled.loc[(garbled.index + KNOWN_AFTER) > cutoff_k] = 1e9
    garbled_diff = diff.copy()
    garbled_diff.loc[garbled_diff.index > cutoff_k, "change_factor"] = 9.0
    tampered = onchain_features(grid, garbled, garbled_diff)
    pd.testing.assert_frame_equal(base.loc[: grid[k]], tampered.loc[: grid[k]])
