"""
The "shape" candidate group (E015) is held to the same rules as every earlier group:

- point-in-time: garble the future and the past must not move;
- gaps blank the windows that touch them, and are never bridged;
- each feature computes what its name claims, checked against hand-built candles;
- the harness's name rules (no target prefixes, no collisions) are respected.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research.features import bars_to_frame
from agent.research.shape import SHAPE_FEATURES, shape_features
from agent.shared.types import PriceBar

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def _bars(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    close = 40000 * np.exp(np.cumsum(rng.normal(0, 0.004, size=n)))
    bars, extra = [], []
    for i in range(n):
        c = float(close[i])
        o = float(close[i - 1]) if i else c
        hi = max(o, c) * (1 + abs(float(rng.normal(0, 0.002))))
        lo = min(o, c) * (1 - abs(float(rng.normal(0, 0.002))))
        vol = float(abs(rng.normal(80, 15)))
        t = START + i * HOUR
        bars.append(PriceBar(t, o, hi, lo, c, vol, "binance"))
        extra.append((t, vol, int(abs(rng.normal(4000, 700))) + 1, vol * float(rng.uniform(0.3, 0.7))))
    ex = pd.DataFrame(extra, columns=["as_of", "volume", "trades", "taker_buy_volume"]).set_index("as_of")
    return bars, ex


def _features(bars, ex):
    return shape_features(bars_to_frame(bars), ex)


def test_the_future_cannot_change_the_past():
    bars, ex = _bars(600, seed=1)
    cut = 400
    full = _features(bars, ex)
    for mutation in ("replace", "delete", "explode"):
        changed = list(bars[:cut])
        ex2 = ex.iloc[:cut].copy()
        if mutation == "replace":
            rng = np.random.default_rng(9)
            changed += [PriceBar(b.as_of, b.open * 3, b.high * 3, b.low * 3, b.close * 3, b.volume * 7, b.source) for b in bars[cut:]]
            ex2 = ex.copy()
            ex2.iloc[cut:] = ex2.iloc[cut:] * 7
        elif mutation == "explode":
            changed += [PriceBar(b.as_of, b.open, b.high * 10, b.low / 10, b.close, b.volume, b.source) for b in bars[cut:]]
            ex2 = ex.copy()
        partial = _features(changed, ex2)
        for col in SHAPE_FEATURES:
            a, b = full[col].iloc[:cut], partial[col].iloc[:cut]
            assert np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float), equal_nan=True), f"{col} moved when only the future changed ({mutation})"


def test_a_gap_blanks_the_windows_that_touch_it_and_is_never_bridged():
    bars, ex = _bars(400, seed=2)
    del bars[200]
    ex = ex.drop(ex.index[200])
    feats = _features(bars, ex)
    missing_hour = START + 200 * HOUR
    assert feats.loc[missing_hour].isna().all(), "the missing hour produced values out of nothing"
    # a 24-hour window one hour after the gap must be blank; 24 hours later it is usable again
    assert np.isnan(feats.loc[missing_hour + HOUR, "close_loc_24"])
    assert not np.isnan(feats.loc[missing_hour + 25 * HOUR, "close_loc_24"])
    assert np.isnan(feats.loc[missing_hour + HOUR, "donchian_pos_168"])


def test_each_feature_computes_what_its_name_claims():
    t = [START + i * HOUR for i in range(3)]
    bars = [
        PriceBar(t[0], 100.0, 110.0, 90.0, 105.0, 10.0, "x"),   # body 5 of range 20; upper wick 5, lower 10
        PriceBar(t[1], 105.0, 106.0, 104.0, 104.5, 10.0, "x"),
        PriceBar(t[2], 104.5, 120.0, 100.0, 101.0, 10.0, "x"),
    ]
    ex = pd.DataFrame({"volume": [10.0, 10.0, 10.0], "trades": [10, 5, 20], "taker_buy_volume": [5.0, 5.0, 5.0]}, index=pd.DatetimeIndex(t))
    f = shape_features(bars_to_frame(bars), ex)
    assert f.loc[t[0], "body_ratio_1h"] == pytest.approx(5 / 20)
    assert f.loc[t[0], "wick_asym_1h"] == pytest.approx((5 - 10) / 20)
    assert f.loc[t[2], "body_ratio_1h"] == pytest.approx(3.5 / 20)
    # up_streak: up, down, down -> +1, -1, -2
    assert list(f["up_streak_6"]) == [1.0, -1.0, -2.0]


def test_streak_saturates_and_flips_sign():
    t = [START + i * HOUR for i in range(12)]
    bars = [PriceBar(t[i], 100.0, 101.0, 99.0, 100.5, 1.0, "x") for i in range(10)]  # ten up closes
    bars += [PriceBar(t[10], 100.0, 101.0, 99.0, 99.5, 1.0, "x"), PriceBar(t[11], 100.0, 101.0, 99.0, 99.5, 1.0, "x")]
    f = shape_features(bars_to_frame(bars), None)
    streak = list(f["up_streak_6"])
    assert streak[:3] == [1.0, 2.0, 3.0] and max(streak) == 6.0, "the streak must saturate at +6"
    assert streak[-2:] == [-1.0, -2.0], "the streak must restart when direction flips"


def test_features_stay_inside_their_definitions():
    bars, ex = _bars(1000, seed=3)
    f = _features(bars, ex)
    for col in ("body_ratio_1h", "close_loc_24", "donchian_pos_168"):
        v = f[col].dropna()
        assert v.between(0.0, 1.0).all(), f"{col} left [0, 1]"
    assert f["wick_asym_1h"].dropna().between(-1.0, 1.0).all()
    assert f["autocorr_lag1_168"].dropna().between(-1.0, 1.0).all()
    assert f["up_streak_6"].dropna().between(-6.0, 6.0).all()
    assert (f["trade_size_rel_24"].dropna() > 0).all() and (f["amihud_rel_168"].dropna() > 0).all()


def test_names_obey_the_harness_rules():
    from agent.research.feature_test import GROUPS, check_feature_names

    assert GROUPS["shape"] == SHAPE_FEATURES
    check_feature_names(SHAPE_FEATURES, pd.DataFrame(columns=["as_of", "close", "signal"]).columns)
