from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.features import RESERVED_PREFIXES
from agent.research.microstructure import MICROSTRUCTURE_FEATURES, microstructure_features

START = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _extra(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range(START, periods=n, freq="h", tz="UTC")
    vol = rng.uniform(100, 1000, size=n)
    share = rng.uniform(0.3, 0.7, size=n)
    return pd.DataFrame({"volume": vol, "trades": rng.integers(1000, 50000, size=n), "taker_buy_volume": vol * share}, index=idx)


def test_no_feature_uses_a_reserved_prefix():
    assert all(not f.startswith(RESERVED_PREFIXES) for f in MICROSTRUCTURE_FEATURES)


def test_known_values():
    idx = pd.date_range(START, periods=200, freq="h", tz="UTC")
    extra = pd.DataFrame({"volume": 100.0, "trades": 1000, "taker_buy_volume": 60.0}, index=idx)
    extra.loc[idx[199], "trades"] = 3000
    feats = microstructure_features(idx, extra)
    last = idx[199]
    assert feats.loc[last, "taker_buy_share_1h"] == pytest.approx(0.6)
    assert feats.loc[last, "taker_buy_share_24h"] == pytest.approx(0.6)
    assert feats.loc[last, "trades_rel_24h"] == pytest.approx(3.0)  # 3000 vs mean 1000 over the PRIOR 24h
    assert feats.loc[last, "trades_rel_168h"] == pytest.approx(3.0)
    assert np.isnan(feats.loc[idx[100], "trades_rel_168h"])  # only 100 prior hours


def test_trade_intensity_baseline_excludes_the_current_hour():
    idx = pd.date_range(START, periods=50, freq="h", tz="UTC")
    extra = pd.DataFrame({"volume": 100.0, "trades": 1000, "taker_buy_volume": 50.0}, index=idx)
    extra.loc[idx[49], "trades"] = 25000
    feats = microstructure_features(idx, extra)
    assert feats.loc[idx[49], "trades_rel_24h"] == pytest.approx(25.0)  # if the hour were in its own baseline this would be 12.5


def test_gap_blanks_windows():
    extra = _extra(100)
    extra = extra.drop(extra.index[50:53])
    grid = pd.date_range(START, periods=100, freq="h", tz="UTC")
    feats = microstructure_features(grid, extra)
    assert np.isnan(feats.loc[grid[53], "taker_buy_share_6h"])  # window touches the gap
    assert not np.isnan(feats.loc[grid[60], "taker_buy_share_6h"])


def test_garbling_the_future_leaves_the_past_unchanged():
    extra = _extra(600, seed=2)
    grid = extra.index
    base = microstructure_features(grid, extra)
    k = 400
    garbled = extra.copy()
    garbled.iloc[k + 1:] = garbled.iloc[k + 1:] * 0 + [1e9, 1, 1e9]
    tampered = microstructure_features(grid, garbled)
    pd.testing.assert_frame_equal(base.iloc[: k + 1], tampered.iloc[: k + 1])
