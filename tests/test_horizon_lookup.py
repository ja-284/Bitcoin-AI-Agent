"""
A4: "H hours later" must mean the candle that opened exactly H hours after the
reference candle -- found by timestamp, never by counting rows. When that candle is
missing (a gap in the exchange's history), the outcome is unavailable, not the next
row that happens to exist.
"""

from datetime import datetime, timedelta, timezone

from agent.backtest.runner import HourResult, forward_returns
from agent.shared.types import PriceBar

START = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _bar(hour_index: int, close: float) -> PriceBar:
    return PriceBar(START + timedelta(hours=hour_index), close, close, close, close, 10.0, "test")


def _result(bar: PriceBar) -> HourResult:
    return HourResult(bar.as_of, bar.as_of + timedelta(hours=1), bar.close, "HOLD", 0.0, 0.5, 0.5, 1.0, 0)


def test_outcome_is_looked_up_by_timestamp():
    bars = [_bar(i, 100.0 + i) for i in range(30)]
    rows = forward_returns(bars, [_result(bars[0])], horizons=[1, 24])
    assert rows[0]["return_1h"] == round((101.0 - 100.0) / 100.0, 6)
    assert rows[0]["return_24h"] == round((124.0 - 100.0) / 100.0, 6)


def test_missing_target_candle_gives_unavailable_not_next_row():
    # Hours 0..9 exist, hours 10..14 are missing (exchange downtime), hours 15..30 exist.
    bars = [_bar(i, 100.0 + i) for i in range(10)] + [_bar(i, 100.0 + i) for i in range(15, 31)]
    reference = bars[0]  # hour 0
    rows = forward_returns(bars, [_result(reference)], horizons=[1, 6, 12, 24])
    assert rows[0]["return_1h"] is not None  # hour 1 exists
    assert rows[0]["return_6h"] is not None  # hour 6 exists
    assert rows[0]["return_12h"] is None  # hour 12 is inside the gap: unavailable, NOT hour 15's price
    assert rows[0]["return_24h"] == round((124.0 - 100.0) / 100.0, 6)  # hour 24 exists again


def test_row_counting_would_have_been_wrong_across_the_gap():
    bars = [_bar(i, 100.0 + i) for i in range(10)] + [_bar(i, 100.0 + i) for i in range(15, 31)]
    rows = forward_returns(bars, [_result(bars[5])], horizons=[6])
    # By row count, "6 rows after hour 5" is hour 16 (close 116); by timestamp it is hour 11: missing.
    assert rows[0]["return_6h"] is None


def test_end_of_data_gives_unavailable():
    bars = [_bar(i, 100.0) for i in range(5)]
    rows = forward_returns(bars, [_result(bars[-1])], horizons=[1])
    assert rows[0]["return_1h"] is None
