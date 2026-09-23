"""
The historical replay (agent/research/replay.py) must see only candles that had closed.

This test exists because mutation testing (tools/guard_mutations.py, 2026-09-23) found it missing:
shifting the replay's window one candle into the future passed the entire suite. The replay is the
engine behind E001, E017 and every research result about the scoring, and it slices its windows in
its own code -- separate from the backtest runner, whose point-in-time tests therefore never
covered it. A leak here would have contaminated all of that research silently.
"""

from datetime import datetime, timedelta, timezone

import numpy as np

from agent.indicators.engine import HISTORY_HOURS
from agent.research.replay import replay_detailed
from agent.shared.types import PriceBar

START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _bars(n: int, seed: int = 0, garble_after: int | None = None) -> list[PriceBar]:
    rng = np.random.default_rng(seed)
    closes = 100 * np.cumprod(1 + rng.normal(0, 0.005, size=n))
    out = []
    for i, c in enumerate(closes):
        if garble_after is not None and i > garble_after:
            c = c * 3.0 + 17.0  # a completely different future
        o = c * (1 + rng.normal(0, 0.001))
        out.append(PriceBar(START + timedelta(hours=i), o, max(o, c) * 1.002, min(o, c) * 0.998, c,
                            1000 + 100 * rng.random(), "test"))
    return out


def test_each_replayed_hour_is_labelled_by_the_last_candle_it_saw():
    bars = _bars(HISTORY_HOURS + 20)
    rows = replay_detailed(bars, processes=1)
    assert len(rows) == 21
    for row, bar in zip(rows, bars[HISTORY_HOURS - 1:]):
        assert row["as_of"] == bar.as_of.isoformat()
        assert row["close"] == bar.close, "the row's close must be its own reference candle's, not a later one"


def test_the_replay_never_uses_a_candle_from_the_future():
    """Garble every candle after a cut; every hour up to the cut must be bit-identical."""
    n, cut = HISTORY_HOURS + 30, HISTORY_HOURS + 10
    before = replay_detailed(_bars(n), processes=1)
    after = replay_detailed(_bars(n, garble_after=cut), processes=1)
    cut_time = (START + timedelta(hours=cut)).isoformat()
    checked = 0
    for a, b in zip(before, after):
        if a["as_of"] <= cut_time:
            assert a == b, f"the replay for {a['as_of']} changed when only later candles changed"
            checked += 1
    assert checked == cut - (HISTORY_HOURS - 1) + 1


def test_the_test_can_see_a_change_after_the_cut():
    """Control: hours after the cut DO change -- otherwise the comparison above could pass vacuously."""
    n, cut = HISTORY_HOURS + 30, HISTORY_HOURS + 10
    before = replay_detailed(_bars(n), processes=1)
    after = replay_detailed(_bars(n, garble_after=cut), processes=1)
    cut_time = (START + timedelta(hours=cut)).isoformat()
    assert any(a != b for a, b in zip(before, after) if a["as_of"] > cut_time)
