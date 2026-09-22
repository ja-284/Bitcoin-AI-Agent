"""
Simple, deterministic chart-pattern checks. Phase 1 deliberately stays with clear,
explainable rules rather than attempting image-style pattern recognition (e.g.
"head and shoulders") -- that's complex, easy to get wrong, and can be added later
behind this same interface without touching anything else.
"""

from dataclasses import dataclass, field

from agent.indicators.engine import IndicatorSet, consecutive_tail
from agent.shared.types import PriceBar

TREND_STRUCTURE_WINDOW = 20  # hours looked at when judging higher-highs/higher-lows
BAND_EDGE_THRESHOLD = 0.15  # within the outer 15% of the Bollinger Band width counts as "near the edge"


@dataclass
class PatternResult:
    ma_cross: str  # "golden_cross" | "death_cross" | "unknown"
    trend_structure: str  # "higher_highs_higher_lows" | "lower_highs_lower_lows" | "mixed" | "unknown"
    bb_position: str  # "near_upper_band" | "near_lower_band" | "middle" | "unknown"
    detail: dict = field(default_factory=dict)


def _ma_cross(indicators: IndicatorSet) -> str:
    if indicators.sma_short is None or indicators.sma_long is None:
        return "unknown"
    return "golden_cross" if indicators.sma_short > indicators.sma_long else "death_cross"


def _trend_structure(bars: list[PriceBar]) -> str:
    # Scoring 0.2.0: "the last 20 hours" must BE the last 20 hours. Counting rows meant that a
    # window containing an exchange outage compared two halves that were not 10 hours each.
    bars = consecutive_tail(bars)
    if len(bars) < TREND_STRUCTURE_WINDOW:
        return "unknown"
    window = bars[-TREND_STRUCTURE_WINDOW:]
    mid = len(window) // 2
    first_half, second_half = window[:mid], window[mid:]

    first_high = max(b.high for b in first_half)
    second_high = max(b.high for b in second_half)
    first_low = min(b.low for b in first_half)
    second_low = min(b.low for b in second_half)

    if second_high > first_high and second_low > first_low:
        return "higher_highs_higher_lows"
    if second_high < first_high and second_low < first_low:
        return "lower_highs_lower_lows"
    return "mixed"


def _bb_position(indicators: IndicatorSet) -> str:
    if indicators.bb_upper is None or indicators.bb_lower is None:
        return "unknown"
    band_width = indicators.bb_upper - indicators.bb_lower
    if band_width <= 0:
        return "unknown"
    position = (indicators.close - indicators.bb_lower) / band_width  # 0 = at lower band, 1 = at upper band
    if position >= 1 - BAND_EDGE_THRESHOLD:
        return "near_upper_band"
    if position <= BAND_EDGE_THRESHOLD:
        return "near_lower_band"
    return "middle"


def detect_patterns(bars: list[PriceBar], indicators: IndicatorSet) -> PatternResult:
    return PatternResult(
        ma_cross=_ma_cross(indicators),
        trend_structure=_trend_structure(bars),
        bb_position=_bb_position(indicators),
        detail={"window_hours": TREND_STRUCTURE_WINDOW},
    )
