"""
Turns each analysis category into its own -1..+1 score, then combines them into one
overall score. Every formula here is deliberately simple (few adjustable knobs) --
per the project's "avoid overfitting" rule, a scoring system with lots of tunable
parameters is much easier to accidentally tune until it just matches old data.

Two categories (trend, chart_pattern) are marked is_independent=False because they're
both substantially built from the same moving averages -- if they agree, that's
expected from shared math, not confirmation from two separate signals. The confidence
calculation (in decision.py) only treats the genuinely independent categories as real
"agreement" evidence.

The `news_score` parameter is optional on purpose: the AI-based news reading module
isn't wired in yet (it needs an Anthropic API key we don't have yet), so this scorer
already works correctly with news absent -- it's simply excluded from the weighted
average, and that gap shows up honestly in the completeness figure. Once the AI module
exists, it will just pass a real CategoryScore in here; nothing in this file changes.
"""

from dataclasses import dataclass

from agent.indicators.engine import IndicatorSet
from agent.patterns.rules import PatternResult
from agent.shared.types import CategoryScore, PriceBar

SCORING_VERSION = "0.1.0"

NOMINAL_WEIGHTS = {
    "trend": 0.25,
    "momentum": 0.25,
    "volume": 0.20,
    "chart_pattern": 0.15,
    "news": 0.15,
}

TREND_FULL_SCALE_PCT = 0.10  # +-10% away from the 200h average maps to a full +-1 trend score
MOMENTUM_RSI_MIDPOINT = 50
MACD_FULL_SCALE_PCT = 0.005  # MACD histogram at 0.5% of price maps to a full +-1 momentum contribution
VOLUME_FULL_SCALE_RATIO = 1.0  # volume 100% above its 20h average maps to a full-strength confirmation
RECENT_CHANGE_LOOKBACK = 6  # hours, used to judge the price direction volume is confirming (or not)


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def score_trend(indicators: IndicatorSet) -> CategoryScore:
    if indicators.sma_long is None:
        return CategoryScore("trend", score=0.0, weight=0.0, is_independent=False, detail={"reason": "insufficient history"})
    pct_from_long_sma = (indicators.close - indicators.sma_long) / indicators.sma_long
    score = _clamp(pct_from_long_sma / TREND_FULL_SCALE_PCT)
    return CategoryScore(
        "trend",
        score=score,
        weight=NOMINAL_WEIGHTS["trend"],
        is_independent=False,
        detail={"close": indicators.close, "sma_long": indicators.sma_long, "pct_from_sma_long": pct_from_long_sma},
    )


def score_momentum(indicators: IndicatorSet) -> CategoryScore:
    components = []
    detail = {}
    if indicators.rsi is not None:
        rsi_component = _clamp((indicators.rsi - MOMENTUM_RSI_MIDPOINT) / MOMENTUM_RSI_MIDPOINT)
        components.append(rsi_component)
        detail["rsi"] = indicators.rsi
    if indicators.macd_histogram is not None:
        macd_component = _clamp((indicators.macd_histogram / indicators.close) / MACD_FULL_SCALE_PCT)
        components.append(macd_component)
        detail["macd_histogram"] = indicators.macd_histogram

    if not components:
        return CategoryScore("momentum", score=0.0, weight=0.0, is_independent=True, detail={"reason": "insufficient history"})

    return CategoryScore(
        "momentum",
        score=sum(components) / len(components),
        weight=NOMINAL_WEIGHTS["momentum"],
        is_independent=True,
        detail=detail,
    )


def score_volume(indicators: IndicatorSet, bars: list[PriceBar]) -> CategoryScore:
    if indicators.volume_avg is None or len(bars) < RECENT_CHANGE_LOOKBACK + 1:
        return CategoryScore("volume", score=0.0, weight=0.0, is_independent=True, detail={"reason": "insufficient history"})

    recent_change = bars[-1].close - bars[-1 - RECENT_CHANGE_LOOKBACK].close
    direction = 1.0 if recent_change > 0 else (-1.0 if recent_change < 0 else 0.0)

    volume_ratio = (indicators.volume - indicators.volume_avg) / indicators.volume_avg
    # Only above-average volume counts as meaningful confirmation; below-average volume
    # just means low conviction either way, so it shouldn't flip the sign toward -1.
    confirmation_strength = max(0.0, _clamp(volume_ratio / VOLUME_FULL_SCALE_RATIO))

    return CategoryScore(
        "volume",
        score=direction * confirmation_strength,
        weight=NOMINAL_WEIGHTS["volume"],
        is_independent=True,
        detail={"volume": indicators.volume, "volume_avg": indicators.volume_avg, "recent_change": recent_change},
    )


def score_chart_pattern(patterns: PatternResult) -> CategoryScore:
    components = []
    if patterns.ma_cross != "unknown":
        components.append(1.0 if patterns.ma_cross == "golden_cross" else -1.0)
    if patterns.trend_structure not in ("unknown", "mixed"):
        components.append(1.0 if patterns.trend_structure == "higher_highs_higher_lows" else -1.0)

    if not components:
        return CategoryScore("chart_pattern", score=0.0, weight=0.0, is_independent=False, detail={"reason": "insufficient history"})

    return CategoryScore(
        "chart_pattern",
        score=sum(components) / len(components),
        weight=NOMINAL_WEIGHTS["chart_pattern"],
        is_independent=False,
        # bb_position is deliberately not scored: whether "near a band edge" is bullish or
        # bearish is genuinely disputed (breakout-continuation vs mean-reversion), so rather
        # than invent an assumption, it's kept here only as context for the AI explanation step.
        detail={"ma_cross": patterns.ma_cross, "trend_structure": patterns.trend_structure, "bb_position": patterns.bb_position},
    )


@dataclass
class ScoringResult:
    overall_score: float
    category_scores: list[CategoryScore]
    completeness: float  # 0-1: how much of the nominal weight actually had data this run


def combine_scores(category_scores: list[CategoryScore]) -> ScoringResult:
    active = [c for c in category_scores if c.weight > 0]
    total_weight = sum(c.weight for c in active)
    nominal_total = sum(NOMINAL_WEIGHTS.values())

    overall = sum(c.score * c.weight for c in active) / total_weight if total_weight > 0 else 0.0
    completeness = total_weight / nominal_total if nominal_total > 0 else 0.0

    return ScoringResult(overall_score=overall, category_scores=category_scores, completeness=completeness)


def score_all(
    bars: list[PriceBar],
    indicators: IndicatorSet,
    patterns: PatternResult,
    news_score: CategoryScore | None = None,
) -> ScoringResult:
    scores = [
        score_trend(indicators),
        score_momentum(indicators),
        score_volume(indicators, bars),
        score_chart_pattern(patterns),
    ]
    scores.append(news_score if news_score is not None else CategoryScore("news", 0.0, 0.0, True, {"reason": "news scoring not yet wired in"}))
    return combine_scores(scores)
