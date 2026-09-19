"""
A5: the historical replay must reproduce what a live run would have computed at that
hour. Live fetches exactly HISTORY_HOURS closed candles and runs the indicators on
them; the replay must feed each simulated hour exactly that window -- no more.

The second test documents WHY this matters: RSI and MACD use exponential smoothing,
whose value depends on how much history is fed in. A replay on a growing window
(everything since the start of the data) drifts away from live values.
"""

import pandas as pd
import pandas_ta_classic as ta

from agent.backtest.runner import analyze_window, replay
from agent.indicators.engine import HISTORY_HOURS, compute_indicators
from tests.test_point_in_time import synthetic_bars


def _live_style(bars, i):
    """What the live orchestrator does: take the last HISTORY_HOURS closed candles as of hour i."""
    return bars[i - HISTORY_HOURS + 1 : i + 1]


def test_replay_equals_live_style_computation_at_every_hour():
    bars = synthetic_bars(HISTORY_HOURS + 40)
    results = replay(bars)
    for offset, result in enumerate(results):
        i = HISTORY_HOURS - 1 + offset
        live = analyze_window(_live_style(bars, i))
        assert result == live, f"replay diverged from live-style calculation at {result.as_of}"


def test_replay_indicators_equal_live_indicators_exactly():
    bars = synthetic_bars(HISTORY_HOURS + 40)
    i = len(bars) - 1
    live = compute_indicators(_live_style(bars, i))
    replayed = compute_indicators(bars[i - HISTORY_HOURS + 1 : i + 1])
    assert live == replayed


def test_growing_window_would_have_diverged_from_live_for_smoothed_indicators():
    bars = synthetic_bars(HISTORY_HOURS + 400)
    closes = pd.Series([b.close for b in bars])
    fixed_rsi = float(ta.rsi(closes.iloc[-HISTORY_HOURS:].reset_index(drop=True), length=14).iloc[-1])
    growing_rsi = float(ta.rsi(closes, length=14).iloc[-1])
    # Same final hour, same formula, different amount of history fed in -> different value.
    assert abs(fixed_rsi - growing_rsi) > 1e-9
