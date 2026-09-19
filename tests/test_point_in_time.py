"""
The data-leakage guard (CLAUDE.md rule 3), checked rather than assumed.

If the analysis of hour N could see anything after hour N, then changing the future
would change the result for hour N. So: replay a synthetic price series, then modify,
corrupt, remove or replace everything after a chosen hour and replay again. Every
result before that hour must be identical. No network, no database.

    python -m pytest tests/
"""

import math
import random
from datetime import datetime, timedelta, timezone

from agent.backtest.runner import analyze_window, replay
from agent.indicators.engine import HISTORY_HOURS
from agent.shared.types import PriceBar


def synthetic_bars(n: int, seed: int = 7, start: datetime | None = None) -> list[PriceBar]:
    rng = random.Random(seed)
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 50_000.0
    bars = []
    for i in range(n):
        drift = math.sin(i / 40) * 150 + rng.uniform(-200, 200)
        open_, close = price, price + drift
        bars.append(
            PriceBar(
                as_of=start + timedelta(hours=i),
                open=open_,
                high=max(open_, close) + rng.uniform(0, 100),
                low=min(open_, close) - rng.uniform(0, 100),
                close=close,
                volume=rng.uniform(100, 1000),
                source="synthetic",
            )
        )
        price = close
    return bars


def _results_before(results, k: int):
    """Replay results correspond to bars[HISTORY_HOURS-1:], so hour k is results[k - (HISTORY_HOURS-1)]."""
    return results[: k - (HISTORY_HOURS - 1)]


def _garbage(b: PriceBar) -> PriceBar:
    return PriceBar(b.as_of, 1e9, 2e9, 0.5e9, 1.5e9, 1e12, b.source)


def _assert_past_unchanged(bars, tampered_bars, k):
    baseline = _results_before(replay(bars), k)
    tampered = _results_before(replay(tampered_bars), k)
    assert len(baseline) == len(tampered) > 0
    for original, altered in zip(baseline, tampered):
        assert original == altered, f"hour {original.as_of} changed when only later bars were altered"


def test_corrupting_future_bars_does_not_change_earlier_results():
    bars = synthetic_bars(HISTORY_HOURS + 60)
    for k in range(HISTORY_HOURS, len(bars), 7):
        _assert_past_unchanged(bars, bars[:k] + [_garbage(b) for b in bars[k:]], k)


def test_removing_future_bars_does_not_change_earlier_results():
    bars = synthetic_bars(HISTORY_HOURS + 60)
    for k in range(HISTORY_HOURS, len(bars), 11):
        _assert_past_unchanged(bars, bars[:k], k)


def test_replacing_future_with_a_different_series_does_not_change_earlier_results():
    bars = synthetic_bars(HISTORY_HOURS + 60, seed=7)
    other = synthetic_bars(HISTORY_HOURS + 60, seed=99)
    for k in range(HISTORY_HOURS, len(bars), 13):
        _assert_past_unchanged(bars, bars[:k] + other[k:], k)


def test_window_output_is_a_pure_function_of_its_input():
    bars = synthetic_bars(HISTORY_HOURS + 5)
    window = bars[:HISTORY_HOURS]
    assert analyze_window(window) == analyze_window(list(window))


def test_each_replay_step_sees_exactly_the_feature_window():
    bars = synthetic_bars(HISTORY_HOURS + 10)
    results = replay(bars)
    assert len(results) == len(bars) - HISTORY_HOURS + 1
    assert results[0].as_of == bars[HISTORY_HOURS - 1].as_of
    assert results[-1].as_of == bars[-1].as_of
    assert all(r.window_missing_hours == 0 for r in results)
