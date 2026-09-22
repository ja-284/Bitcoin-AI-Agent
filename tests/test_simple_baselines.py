"""
Tests for the E019 simple baselines. The experiment's whole claim rests on the rules being
causal -- each one may use only candles that had closed by the decision hour -- and on windows
being measured in time rather than in rows, so a data gap shortens a window instead of
silently reaching further back. Both are tested here by construction, not asserted in prose.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research import simple_baselines as sb
from agent.shared.types import PriceBar

START = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _bars(closes: list[float], skip: set[int] | None = None) -> list[PriceBar]:
    """One candle per hour; indices in `skip` are omitted to create a data gap."""
    skip = skip or set()
    out = []
    for i, c in enumerate(closes):
        if i in skip:
            continue
        out.append(PriceBar(as_of=START + timedelta(hours=i), open=c, high=c, low=c, close=c,
                            volume=1.0, source="test"))
    return out


def _walk(n: int, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(100.0 * np.cumprod(1 + rng.normal(0, 0.004, size=n)))


def test_indicator_marks_the_candle_that_moved():
    # +1% then +0.01%: the first candle's own move is large, the second is not
    bars = _bars([100.0, 101.0, 101.01])
    ind = sb.indicator_series(bars)
    assert np.isnan(ind.iloc[0])          # no previous close, so no return
    assert ind.iloc[1] == 1.0
    assert ind.iloc[2] == 0.0


def test_a_return_spanning_a_data_gap_is_not_counted():
    """Across a hole the 'previous close' is hours old, so that return is not a one-hour return."""
    bars = _bars([100.0, 100.05, 100.1, 100.15, 108.0, 108.01], skip={2, 3})
    ind = sb.indicator_series(bars)
    at_gap = ind.loc[START + timedelta(hours=4)]
    assert np.isnan(at_gap), "the 8% jump across a two-hour hole must not be scored as an hourly move"
    assert ind.loc[START + timedelta(hours=5)] == 0.0


def test_rules_never_use_a_candle_that_had_not_closed():
    """
    Point-in-time by perturbation: garble every candle after a cut hour and recompute. Values at
    or before the cut must be bit-identical. This is the test that would fail if a window were
    centred, shifted the wrong way, or built from a forward-looking series.
    """
    closes = _walk(900)
    cut = 600
    before = sb.simple_rules(_bars(closes))
    garbled = list(closes)
    for i in range(cut + 1, len(garbled)):
        garbled[i] = garbled[i] * 3.0 + 17.0
    after = sb.simple_rules(_bars(garbled))
    cut_time = START + timedelta(hours=cut)
    for name in before:
        a = before[name].loc[:cut_time].to_numpy()
        b = after[name].loc[:cut_time].to_numpy()
        assert np.array_equal(a, b, equal_nan=True), "%s used a candle from the future" % name


def test_windows_are_measured_in_time_not_rows():
    """With 200 hours removed, a 168-hour window must go unavailable rather than reach back 368 hours."""
    closes = _walk(1200)
    gap = set(range(400, 600))
    rules = sb.simple_rules(_bars(closes, skip=gap))
    just_after = START + timedelta(hours=600)
    value = rules["C_trailing_168h"].loc[just_after]
    assert np.isnan(value), "a 168h window with only a handful of real hours in it must not report a number"
    # and once enough real hours have accumulated again, it comes back
    later = rules["C_trailing_168h"].loc[START + timedelta(hours=790)]
    assert not np.isnan(later)


def test_every_rule_is_a_probability():
    rules = sb.simple_rules(_bars(_walk(2000, seed=2)))
    for name, s in rules.items():
        v = s.dropna().to_numpy()
        assert len(v) > 0, name
        assert v.min() >= 0.0 and v.max() <= 1.0, name


def test_paired_difference_is_zero_against_itself():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.1, 0.9, size=1500)
    y = (rng.uniform(size=1500) < p).astype(float)
    d = sb.paired_difference(p, p, y)
    assert d["diff"] == 0.0
    assert d["ci_low"] == 0.0 and d["ci_high"] == 0.0


def test_score_rewards_the_better_forecast():
    rng = np.random.default_rng(6)
    p = rng.uniform(0.05, 0.95, size=4000)
    y = (rng.uniform(size=4000) < p).astype(float)
    good = sb.score(p, y, np.abs(rng.normal(size=4000)))
    flat = sb.score(np.full(4000, float(y.mean())), y, np.abs(rng.normal(size=4000)))
    assert good["brier"] < flat["brier"]
    assert good["skill"] > 0
    assert flat["skill"] == pytest.approx(0.0, abs=1e-9)  # a flat forecast at the base rate has no skill
