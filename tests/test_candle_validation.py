"""
A7: impossible candle data must fail loudly; gaps must be flagged, never filled.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agent.data_providers.quality import BarValidationError, validate_bars
from agent.shared.types import PriceBar

START = datetime(2026, 3, 1, tzinfo=timezone.utc)
NOW = START + timedelta(hours=100)


def _bar(hour_index: int, **overrides) -> PriceBar:
    fields = dict(as_of=START + timedelta(hours=hour_index), open=100.0, high=101.0, low=99.0, close=100.5, volume=5.0, source="t")
    fields.update(overrides)
    return PriceBar(**fields)


def test_clean_series_has_no_gaps():
    report = validate_bars([_bar(i) for i in range(10)], now=NOW)
    assert report.count == 10 and report.gaps == [] and report.missing_hours == 0 and report.span_hours == 10


def test_gap_is_flagged_not_filled():
    bars = [_bar(0), _bar(1), _bar(5), _bar(6)]  # hours 2,3,4 missing
    report = validate_bars(bars, now=NOW)
    assert report.count == 4  # nothing was inserted
    assert report.gaps == [(START + timedelta(hours=1), 3)]
    assert report.missing_hours == 3


def test_duplicate_timestamp_raises():
    with pytest.raises(BarValidationError, match="duplicate"):
        validate_bars([_bar(0), _bar(1), _bar(1)], now=NOW)


def test_out_of_order_raises():
    with pytest.raises(BarValidationError, match="out-of-order"):
        validate_bars([_bar(0), _bar(2), _bar(1)], now=NOW)


def test_partial_candle_raises():
    with pytest.raises(BarValidationError, match="has not closed"):
        validate_bars([_bar(0), _bar(1)], now=START + timedelta(hours=1, minutes=30))


@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"high": 98.0}, "OHLC inconsistent"),
        ({"low": 100.6}, "OHLC inconsistent"),
        ({"close": float("nan")}, "non-finite"),
        ({"open": -1.0, "low": -2.0}, "non-positive"),
        ({"volume": -5.0}, "negative volume"),
        ({"as_of": START + timedelta(minutes=30)}, "not aligned"),
        ({"as_of": datetime(2026, 3, 1)}, "timezone-aware"),
    ],
)
def test_impossible_values_raise(overrides, message):
    with pytest.raises(BarValidationError, match=message):
        validate_bars([_bar(0, **overrides)], now=NOW)


def test_empty_raises():
    with pytest.raises(BarValidationError):
        validate_bars([], now=NOW)
