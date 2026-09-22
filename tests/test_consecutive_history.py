"""
Scoring 0.2.0: "enough history" means enough CONSECUTIVE hours.

The point of this change is narrow and must stay narrow:
  - on a window with no gaps, every number is exactly what scoring 0.1.0 produced
    (tests/test_scoring_golden.py pins that, and it still passes);
  - on a window with a gap, anything whose hours are missing becomes unavailable instead of
    being computed across the hole.

Before 0.2.0 a "200-hour average" could span 233 hours, the volume category compared the close
with a candle up to 33 hours from the 6 it intended, and "the last 20 hours" of trend structure
could be 40. 9.26% of all replayed hours since 2017 had a gap inside their window.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agent.indicators.engine import HISTORY_HOURS, compute_indicators, consecutive_tail
from agent.patterns.rules import TREND_STRUCTURE_WINDOW, detect_patterns
from agent.scoring.scorer import SCORING_VERSION, score_all, score_volume
from agent.shared.types import PriceBar

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def _bars(n: int, start: datetime = START) -> list[PriceBar]:
    out = []
    for i in range(n):
        p = 100 + (i % 23) * 0.4 + (i % 7) * 0.15
        out.append(PriceBar(start + i * HOUR, p, p + 0.6, p - 0.6, p + 0.2, 10.0 + (i % 5), "binance"))
    return out


def test_the_version_was_bumped_with_the_behaviour():
    assert SCORING_VERSION == "0.2.0"


def test_consecutive_tail_finds_the_unbroken_run():
    bars = _bars(50)
    assert len(consecutive_tail(bars)) == 50
    del bars[30]  # a hole 20 hours before the end
    assert len(consecutive_tail(bars)) == 19
    assert consecutive_tail(bars)[-1].as_of == bars[-1].as_of
    assert len(consecutive_tail(_bars(1))) == 1


def test_a_gap_free_window_is_unchanged_by_the_fix():
    """The whole safety argument: on clean data 0.2.0 must compute exactly what 0.1.0 did."""
    bars = _bars(HISTORY_HOURS)
    ind = compute_indicators(bars)
    assert ind.insufficient_history == []
    assert ind.window_hours == ind.consecutive_hours == HISTORY_HOURS
    assert ind.sma_long is not None and ind.rsi is not None and ind.volume_avg is not None
    # and the values are the ones pinned in tests/golden_scoring_0_1_0.json (that test still runs)


def test_a_gap_makes_the_affected_indicators_unavailable_instead_of_wrong():
    bars = _bars(HISTORY_HOURS)
    del bars[-100]  # 99 consecutive hours remain: enough for RSI/MACD/Bollinger, not for the 200h average
    ind = compute_indicators(bars)
    assert ind.consecutive_hours == 99 and ind.window_hours == HISTORY_HOURS - 1
    assert any("window has a gap" in m for m in ind.insufficient_history)
    assert ind.sma_long is None, "a 200-hour average cannot be built from 99 consecutive hours"
    assert any("sma_200" in m and "consecutive" in m for m in ind.insufficient_history)
    assert ind.sma_short is not None and ind.rsi is not None  # these fit inside the unbroken run

    bars = _bars(HISTORY_HOURS)
    del bars[-5]  # only 4 consecutive hours left: nothing survives
    ind = compute_indicators(bars)
    assert ind.consecutive_hours == 4
    for value in (ind.sma_short, ind.sma_long, ind.rsi, ind.macd, ind.bb_upper, ind.volume_avg):
        assert value is None


def test_a_gap_inside_the_volume_window_makes_the_category_unavailable():
    """
    The real protection: the 20-hour volume average now needs 20 consecutive hours, so a gap
    anywhere inside it makes the whole category unavailable. Before 0.2.0 that average was
    computed over 20 ROWS spanning more than 20 hours, and the direction term compared the close
    with whatever candle sat six rows back -- which, with a hole, is not six hours back.
    """
    bars = _bars(HISTORY_HOURS)
    assert score_volume(compute_indicators(bars), bars).weight > 0
    holed = _bars(HISTORY_HOURS)
    del holed[-4]
    scored = score_volume(compute_indicators(holed), holed)
    assert scored.weight == 0.0


def test_the_reference_hour_lookup_refuses_to_guess():
    """
    The belt-and-braces half of the fix, tested directly: even handed indicators that claim to
    be usable, the direction term will not substitute a neighbouring candle for the hour it
    needs. (In the live path the check above fires first; this one guarantees the rest.)
    """
    clean = _bars(HISTORY_HOURS)
    holed = _bars(HISTORY_HOURS)
    del holed[-7]  # the candle six hours before the end is gone
    scored = score_volume(compute_indicators(clean), holed)
    assert scored.weight == 0.0 and "no candle at" in scored.detail["reason"]


def test_the_volume_direction_uses_the_hour_it_claims():
    """A gap further back must not shift which candle the direction compares against."""
    bars = _bars(HISTORY_HOURS)
    ind = compute_indicators(bars)
    baseline = score_volume(ind, bars)
    moved = _bars(HISTORY_HOURS)
    del moved[-60]  # a hole outside the 6-hour lookback
    scored = score_volume(compute_indicators(moved), moved)
    assert scored.detail["recent_change"] == pytest.approx(baseline.detail["recent_change"])


def test_trend_structure_needs_twenty_real_hours():
    bars = _bars(60)
    assert detect_patterns(bars, compute_indicators(bars)).trend_structure != "unknown"
    del bars[-15]  # only 14 consecutive hours remain
    assert detect_patterns(bars, compute_indicators(bars)).trend_structure == "unknown"


def test_a_gapped_window_lowers_completeness_rather_than_producing_confident_nonsense():
    clean = _bars(HISTORY_HOURS)
    holed = _bars(HISTORY_HOURS)
    del holed[-5]
    clean_result = score_all(clean, compute_indicators(clean), detect_patterns(clean, compute_indicators(clean)), news_score=None)
    ind_holed = compute_indicators(holed)
    holed_result = score_all(holed, ind_holed, detect_patterns(holed, ind_holed), news_score=None)
    assert clean_result.completeness > holed_result.completeness
    assert holed_result.completeness < 1.0
    for category in holed_result.category_scores:
        if category.weight == 0:
            assert category.score == 0.0  # unavailable means unavailable, not "neutral evidence"
