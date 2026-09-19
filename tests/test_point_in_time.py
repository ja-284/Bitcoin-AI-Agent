"""
The data-leakage guard (CLAUDE.md rule 3), checked rather than assumed.

If the analysis of hour N could see anything after hour N, then wildly changing the
future bars would change the result for hour N. So: replay a synthetic price series,
then replace everything after each hour with garbage and replay again. Every result
must be byte-for-byte identical. No network, no database -- runs in a second.

    python -m pytest tests/
"""

import math
import random
from datetime import datetime, timedelta, timezone

from agent.backtest.runner import WARMUP_HOURS, analyze_window, replay
from agent.shared.types import PriceBar


def _synthetic_bars(n: int, seed: int = 7) -> list[PriceBar]:
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
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


def _garbage_future(bars: list[PriceBar], from_index: int) -> list[PriceBar]:
    """Same past, absurd future: if any of this leaks into earlier hours, it will show."""
    altered = list(bars[:from_index])
    for b in bars[from_index:]:
        altered.append(PriceBar(b.as_of, 1e9, 2e9, 0.5e9, 1.5e9, 1e12, b.source))
    return altered


def test_results_do_not_depend_on_future_bars():
    bars = _synthetic_bars(WARMUP_HOURS + 60)
    baseline = replay(bars)

    for k in range(WARMUP_HOURS + 1, len(bars), 7):
        tampered = replay(_garbage_future(bars, k))
        # Every hour strictly before k saw identical data, so must produce identical results.
        for original, altered in zip(baseline[: k - WARMUP_HOURS], tampered[: k - WARMUP_HOURS]):
            assert original == altered, f"hour {original.as_of} changed when only later bars were altered"


def test_window_output_is_a_pure_function_of_its_input():
    bars = _synthetic_bars(WARMUP_HOURS + 5)
    assert analyze_window(bars[:WARMUP_HOURS + 1]) == analyze_window(bars[:WARMUP_HOURS + 1])


if __name__ == "__main__":
    test_results_do_not_depend_on_future_bars()
    test_window_output_is_a_pure_function_of_its_input()
    print("point-in-time guard: OK")
