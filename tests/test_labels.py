"""
Targets must be explicit, timestamp-based, and free of lookahead -- including inside
the volatility-scaled threshold, which is the easiest place to leak the future.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agent.research.labels import DOWN, NEUTRAL, UP, LabelSpec, forward_returns, make_labels, point_in_time_thresholds
from agent.shared.types import PriceBar

START = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _bars(closes: list[float | None]) -> list[PriceBar]:
    """None = missing hour."""
    return [PriceBar(START + timedelta(hours=i), c, c, c, c, 1.0, "t") for i, c in enumerate(closes) if c is not None]


def test_forward_return_uses_the_candle_opening_h_hours_later():
    bars = _bars([100, 101, 102, 103, 104])
    ret = forward_returns(bars, 2)
    assert ret.iloc[0] == pytest.approx(0.02)  # 100 -> 102
    assert ret.iloc[2] == pytest.approx(104 / 102 - 1)
    assert ret.iloc[3] != ret.iloc[3]  # NaN: hour 5 does not exist


def test_missing_outcome_candle_gives_no_label_not_the_next_row():
    bars = _bars([100, 101, None, None, 104, 105])  # hours 2 and 3 missing
    df = make_labels(bars, LabelSpec(horizon_hours=2, kind="binary"))
    by_hour = dict(zip(df["as_of"], df["label"]))
    assert by_hour[START] is None  # hour 0 + 2h = hour 2: missing
    assert by_hour[START + timedelta(hours=1)] is None  # hour 3: missing
    assert by_hour[START + timedelta(hours=4)] is None  # hour 6: beyond data


def test_binary_labels():
    bars = _bars([100, 101, 100, 100])
    df = make_labels(bars, LabelSpec(horizon_hours=1, kind="binary"))
    assert list(df["label"])[:3] == [UP, DOWN, DOWN]  # 100->101 up; 101->100 down; 100->100 flat counts as not-up


def test_three_class_fixed_threshold():
    bars = _bars([100, 100.4, 101.0, 99.0, 100.0])
    spec = LabelSpec(horizon_hours=1, kind="three_class", threshold_kind="fixed", threshold=0.005)
    df = make_labels(bars, spec)
    assert list(df["label"])[:4] == [NEUTRAL, UP, DOWN, UP]  # +0.4% neutral; +0.6% up; -2% down; +1% up


def test_vol_scaled_threshold_uses_only_completed_returns():
    # 2000 hours: calm for the first 1000 hours (tiny moves), then wild.
    closes = [100.0]
    for i in range(1, 2000):
        step = 0.0005 if i < 1000 else 0.05
        closes.append(closes[-1] * (1 + step * (1 if i % 2 else -1)))
    bars = _bars(closes)
    spec = LabelSpec(horizon_hours=24, kind="three_class", threshold_kind="vol_scaled", threshold=1.0,
                     vol_lookback_hours=240, min_vol_samples=100)
    th = point_in_time_thresholds(forward_returns(bars, 24), spec)

    calm_hour = START + timedelta(hours=900)
    first_wild_hour = START + timedelta(hours=1000)
    # At hour 1000 the wild regime has just begun, but no wild 24h return has COMPLETED yet
    # (the first one completes at hour 1000 + 24). The threshold must still be the calm one.
    assert th[first_wild_hour] == pytest.approx(th[calm_hour], rel=0.05)
    # Well into the wild regime, completed wild returns dominate the window.
    assert th[START + timedelta(hours=1500)] > 10 * th[calm_hour]


def test_vol_scaled_threshold_is_unavailable_before_enough_completed_returns():
    bars = _bars([100 + (i % 3) for i in range(300)])
    spec = LabelSpec(horizon_hours=24, kind="three_class", threshold_kind="vol_scaled", threshold=0.5,
                     vol_lookback_hours=240, min_vol_samples=100)
    df = make_labels(bars, spec)
    assert df["label"].iloc[50] is None  # only 26 completed returns exist by hour 50
    assert df["label"].iloc[200] is not None


def test_label_spec_validation():
    with pytest.raises(ValueError):
        LabelSpec(horizon_hours=0)
    with pytest.raises(ValueError):
        LabelSpec(horizon_hours=1, kind="fuzzy")
