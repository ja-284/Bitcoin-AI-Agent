"""
A6: fallback (CoinGecko) bars carry a rolling 24h volume, not hourly volume. The volume
category must be marked unavailable on such data, never scored at full weight.
"""

from dataclasses import replace

from agent.indicators.engine import HISTORY_HOURS, compute_indicators
from agent.scoring.scorer import score_volume
from tests.test_point_in_time import synthetic_bars


def test_real_bars_score_volume_at_full_weight():
    bars = synthetic_bars(HISTORY_HOURS)
    score = score_volume(compute_indicators(bars), bars)
    assert score.weight > 0


def test_synthetic_bars_make_volume_unavailable():
    bars = [replace(b, is_synthetic=True, source="coingecko") for b in synthetic_bars(HISTORY_HOURS)]
    score = score_volume(compute_indicators(bars), bars)
    assert score.weight == 0
    assert score.score == 0.0
    assert "synthetic" in score.detail["reason"]


def test_a_single_synthetic_bar_inside_the_volume_lookback_is_enough():
    bars = synthetic_bars(HISTORY_HOURS)
    bars[-3] = replace(bars[-3], is_synthetic=True)
    assert score_volume(compute_indicators(bars), bars).weight == 0
