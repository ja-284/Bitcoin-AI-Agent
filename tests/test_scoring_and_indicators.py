"""
Known-value checks for the formulas the whole system rests on. If any of these move,
scoring 0.1.0 is no longer the baseline that was evaluated.
"""

from datetime import datetime, timedelta, timezone

import pytest

from agent.decision.decision import BUY_THRESHOLD, SELL_THRESHOLD, compute_confidence, decide_signal
from agent.indicators.engine import HISTORY_HOURS, IndicatorSet, compute_indicators
from agent.scoring.scorer import NOMINAL_WEIGHTS, combine_scores, score_momentum, score_trend
from agent.shared.types import CategoryScore, PriceBar

START = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _flat_indicators(**overrides) -> IndicatorSet:
    base = dict(close=100.0, sma_short=100.0, sma_long=100.0, rsi=50.0, macd=0.0, macd_signal=0.0, macd_histogram=0.0,
                bb_upper=102.0, bb_lower=98.0, volume=10.0, volume_avg=10.0)
    base.update(overrides)
    return IndicatorSet(**base)


def test_sma_and_rsi_on_a_known_series():
    # Closes rise by exactly 1 each hour: SMA200 of the last 200 is the mean of 51..250; RSI of a
    # series that only ever rises is 100 by definition.
    bars = [PriceBar(START + timedelta(hours=i), 1.0 + i, 2.0 + i, 0.5 + i, 1.0 + i, 1.0, "t") for i in range(HISTORY_HOURS)]
    ind = compute_indicators(bars)
    assert ind.sma_long == pytest.approx(sum(range(51, 251)) / 200)
    assert ind.sma_short == pytest.approx(sum(range(201, 251)) / 50)
    assert ind.rsi == pytest.approx(100.0)
    assert ind.insufficient_history == []


def test_short_history_marks_indicators_unavailable():
    bars = [PriceBar(START + timedelta(hours=i), 100.0, 101.0, 99.0, 100.0, 1.0, "t") for i in range(10)]
    ind = compute_indicators(bars)
    assert ind.sma_long is None and ind.rsi is None and ind.macd is None
    assert len(ind.insufficient_history) == 6


@pytest.mark.parametrize("pct_above,expected", [(0.05, 0.5), (0.10, 1.0), (0.25, 1.0), (-0.05, -0.5), (0.0, 0.0)])
def test_trend_score_is_distance_from_long_average_capped_at_ten_percent(pct_above, expected):
    score = score_trend(_flat_indicators(close=100.0 * (1 + pct_above)))
    assert score.score == pytest.approx(expected)
    assert score.weight == NOMINAL_WEIGHTS["trend"]


def test_momentum_averages_rsi_and_macd_components():
    # RSI 75 -> (75-50)/50 = 0.5 ; MACD histogram 0.25% of price -> 0.0025/0.005 = 0.5 ; average 0.5
    score = score_momentum(_flat_indicators(rsi=75.0, macd_histogram=0.25))
    assert score.score == pytest.approx(0.5)


def test_momentum_with_only_rsi_available_uses_rsi_alone():
    assert score_momentum(_flat_indicators(rsi=100.0, macd_histogram=None)).score == pytest.approx(1.0)


def test_combine_normalises_by_active_weight_and_reports_completeness():
    scores = [
        CategoryScore("trend", 1.0, 0.25, False),
        CategoryScore("momentum", 0.0, 0.25, True),
        CategoryScore("volume", 0.0, 0.0, True, {"reason": "unavailable"}),
        CategoryScore("chart_pattern", 0.0, 0.0, False, {"reason": "unavailable"}),
        CategoryScore("news", 0.0, 0.0, True, {"reason": "unavailable"}),
    ]
    result = combine_scores(scores)
    assert result.overall_score == pytest.approx(0.5)  # (1*0.25 + 0*0.25) / 0.50
    assert result.completeness == pytest.approx(0.5)  # 0.50 of 1.00 nominal weight had data


@pytest.mark.parametrize("score,signal", [(0.15, "BUY"), (0.149, "HOLD"), (-0.15, "SELL"), (-0.149, "HOLD"), (0.0, "HOLD")])
def test_signal_thresholds(score, signal):
    assert decide_signal(score) == signal
    assert BUY_THRESHOLD == 0.15 and SELL_THRESHOLD == -0.15


def test_confidence_ignores_non_independent_categories_and_uses_spread():
    agreeing = combine_scores([
        CategoryScore("trend", 1.0, 0.25, False),
        CategoryScore("momentum", 0.4, 0.25, True),
        CategoryScore("volume", 0.4, 0.20, True),
        CategoryScore("news", 0.4, 0.15, True),
        CategoryScore("chart_pattern", -1.0, 0.15, False),
    ])
    conf = compute_confidence(agreeing)
    assert conf.agreement_score == pytest.approx(1.0)  # trend/chart_pattern disagreement is deliberately ignored
    assert conf.completeness_score == pytest.approx(1.0)
    assert conf.overall_confidence == pytest.approx(1.0)


def test_confidence_is_a_heuristic_not_tied_to_signal_strength():
    # Documents a known weakness (CLAUDE.md): a weak and a strong overall score get identical confidence
    # when their independent categories are equally spread. This is why it is NOT a probability.
    weak = combine_scores([CategoryScore("momentum", 0.1, 0.25, True), CategoryScore("volume", 0.1, 0.20, True),
                           CategoryScore("news", 0.1, 0.15, True), CategoryScore("trend", 0.0, 0.25, False),
                           CategoryScore("chart_pattern", 0.0, 0.15, False)])
    strong = combine_scores([CategoryScore("momentum", 0.9, 0.25, True), CategoryScore("volume", 0.9, 0.20, True),
                             CategoryScore("news", 0.9, 0.15, True), CategoryScore("trend", 1.0, 0.25, False),
                             CategoryScore("chart_pattern", 1.0, 0.15, False)])
    assert compute_confidence(weak).overall_confidence == compute_confidence(strong).overall_confidence
