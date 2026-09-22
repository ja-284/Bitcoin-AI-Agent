"""
Tests for E021's volatility-scaled threshold machinery.

The experiment's validity rests on one thing above all: the threshold that decides whether an
hour counts as a "large move" must be computable from candles that had already closed. If it
could see the hour it is labelling, the target would leak into itself and the comparison would
be worthless. That is tested here by perturbation, not asserted in prose.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research import threshold_test as tt
from agent.research.labels import LabelSpec
from agent.shared.types import PriceBar

START = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _bars(closes: list[float]) -> list[PriceBar]:
    return [PriceBar(as_of=START + timedelta(hours=i), open=c, high=c, low=c, close=c,
                     volume=1.0, source="test") for i, c in enumerate(closes)]


def _walk(n: int, scale: float = 0.004, seed: int = 0) -> list[float]:
    rng = np.random.default_rng(seed)
    return list(100.0 * np.cumprod(1 + rng.normal(0, scale, size=n)))


def test_the_multiplier_and_lookback_are_the_declared_ones():
    """A silent change here would turn a pre-registered comparison into a tuned one."""
    assert tt.K == 1.0
    default = LabelSpec(horizon_hours=1)
    assert tt.VOL_LOOKBACK_HOURS == default.vol_lookback_hours
    assert tt.MIN_VOL_SAMPLES == default.min_vol_samples


def test_the_threshold_cannot_see_the_hour_it_labels():
    """
    Perturbation: garble every candle after a cut hour and recompute. Thresholds at or before
    the cut must be bit-identical. This is the test that would fail if the rolling window were
    centred, or shifted the wrong way, or built from forward returns without the shift.
    """
    closes = _walk(2000)
    cut = 1500
    before = tt.vol_scaled_threshold(_bars(closes))
    garbled = list(closes)
    for i in range(cut + 1, len(garbled)):
        garbled[i] = garbled[i] * 4.0 + 31.0
    after = tt.vol_scaled_threshold(_bars(garbled))
    cut_time = START + timedelta(hours=cut)
    a = before.loc[:cut_time].to_numpy()
    b = after.loc[:cut_time].to_numpy()
    assert np.array_equal(a, b, equal_nan=True), "the threshold used a candle from the future"


def test_the_threshold_is_unavailable_until_enough_returns_have_completed():
    th = tt.vol_scaled_threshold(_bars(_walk(1000)))
    assert np.isnan(th.iloc[10])
    assert np.isnan(th.iloc[tt.MIN_VOL_SAMPLES - 5])
    assert not np.isnan(th.iloc[900])


def test_the_threshold_tracks_the_volatility_level():
    """Calm first, then wild: the threshold must rise, but only once wild returns have completed."""
    calm = _walk(1200, scale=0.001, seed=1)
    wild = list(np.array(_walk(800, scale=0.02, seed=2)) * (calm[-1] / 100.0))
    th = tt.vol_scaled_threshold(_bars(calm + wild))
    calm_level = th.iloc[1100]
    assert th.iloc[1900] > 5 * calm_level


def test_spread_ignores_years_too_small_to_mean_anything():
    by_year = {2020: {"n": 5000, "positive_rate": 0.40}, 2021: {"n": 5000, "positive_rate": 0.62},
               2022: {"n": 12, "positive_rate": 0.99}}  # a handful of hours must not set the range
    assert tt.spread(by_year) == pytest.approx(0.22)


def test_spread_is_undefined_with_fewer_than_two_usable_years():
    assert np.isnan(tt.spread({2020: {"n": 5000, "positive_rate": 0.4}}))
    assert np.isnan(tt.spread({}))


def test_per_year_reports_the_positive_rate_and_skill_of_each_year():
    idx = pd.date_range("2020-01-01", periods=400, freq="h", tz="UTC")
    rng = np.random.default_rng(4)
    p = rng.uniform(0.2, 0.8, size=400)
    y = (rng.uniform(size=400) < p).astype(float)
    preds = pd.DataFrame({"p": p, "y": y, "year": [t.year for t in idx]}, index=idx)
    out = tt.per_year(preds)
    assert set(out) == {2020}
    assert out[2020]["n"] == 400
    assert out[2020]["positive_rate"] == pytest.approx(float(y.mean()))
    assert out[2020]["skill"] > 0  # an informative forecast beats its own base rate
