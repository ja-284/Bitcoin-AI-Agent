"""
E039's daily direction study (agent/research/daily_direction.py), on synthetic data only: daily closes come from the
23:00 candle, every signal is point in time, forward returns only look forward, period masks never let an outcome
cross a boundary, funding is read unit-safely, and the trading arithmetic is exact. Nothing here reads data/.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from agent.research import daily_direction as dd
from agent.shared.types import PriceBar

DAY0 = pd.Timestamp("2030-01-01", tz="UTC")


def synthetic(n_days=700, seed=4):
    rng = np.random.default_rng(seed)
    days = pd.date_range(DAY0, periods=n_days, freq="D", tz="UTC").as_unit("ns")
    days = days.delete([100, 101, 350])  # missing days
    close = pd.Series(30_000 * np.exp(np.cumsum(rng.normal(0.001, 0.03, len(days)))), index=days)
    taker24 = pd.Series(rng.uniform(0.45, 0.55, len(days)), index=days)
    funding21 = pd.Series(rng.normal(21e-4, 5e-4, len(days)), index=days)
    return close, taker24, funding21


def test_daily_closes_come_from_the_23_00_candle_only():
    t0 = datetime(2030, 1, 1, tzinfo=timezone.utc)
    bars = [PriceBar(as_of=t0 + timedelta(hours=h), open=1, high=1, low=1, close=float(h), volume=1, source="test") for h in range(72)]
    s = dd.daily_closes(bars)
    assert s.tolist() == [23.0, 47.0, 71.0] and s.index[0] == pd.Timestamp("2030-01-01", tz="UTC")


def test_every_signal_is_point_in_time():
    close, taker, funding = synthetic()
    full = dd.build_signals(close, taker, funding)
    cut = close.index[500]
    later = close.copy()
    later[later.index > cut] *= np.random.default_rng(9).uniform(0.5, 1.5, (later.index > cut).sum())
    f2 = funding.copy()
    f2[f2.index > cut] *= -3
    t2 = taker.copy()
    t2[t2.index > cut] = 0.1
    changed = dd.build_signals(later, t2, f2)
    cols = [c for c in full.columns if c != "close"]
    a, b = full.loc[:cut, cols], changed.loc[:cut, cols]
    assert ((a == b) | (a.isna() & b.isna())).all().all()


def test_forward_returns_look_only_forward_and_end_inside_the_data():
    close, _, _ = synthetic()
    f7 = dd.forward_returns(close, 7)
    d = close.index[200]
    assert f7[d] == pytest.approx(close[d + pd.Timedelta(days=7)] / close[d] - 1)
    assert f7.iloc[-7:].isna().all()
    # the lookup is by calendar date, never by row position: a missing target day gives no value
    before_gap = DAY0 + pd.Timedelta(days=94)  # + 7 days = DAY0 + 101, a deleted day
    assert np.isnan(f7[before_gap])


def test_period_masks_never_let_an_outcome_cross_a_boundary():
    idx = pd.date_range("2023-12-20", "2024-01-10", freq="D", tz="UTC")
    m = dd.period_mask(idx, 7, "exploration")
    assert idx[m].max() == pd.Timestamp("2023-12-24", tz="UTC")  # 12-24 + 7 = 12-31, still exploration
    v = dd.period_mask(pd.date_range("2025-06-20", "2025-06-30", freq="D", tz="UTC"), 7, "validation")
    assert pd.date_range("2025-06-20", "2025-06-30", freq="D", tz="UTC")[v].max() == pd.Timestamp("2025-06-23", tz="UTC")


def test_reviewed_route_features_are_taken_at_each_days_23_00_row_whatever_the_time_unit():
    hours = pd.date_range("2030-01-01", periods=72, freq="h", tz="UTC").as_unit("us")
    feats = pd.DataFrame({"funding_sum_21": np.arange(72, dtype=float)}, index=hours)
    s = dd.day_rows(feats, "funding_sum_21")
    assert s.tolist() == [23.0, 47.0, 71.0] and s.index.unit == "ns" and s.index[1] == pd.Timestamp("2030-01-02", tz="UTC")
    close, taker, funding = synthetic()
    sig = dd.build_signals(close, taker, funding)
    d = close.index[300]
    assert sig.loc[d, "FUND7"] == pytest.approx(funding[d] / 21)
    window = taker.reindex(pd.date_range(d - pd.Timedelta(days=6), d, freq="D", tz="UTC"))
    assert sig.loc[d, "TAKER7"] == pytest.approx(window.mean()) if window.notna().all() else np.isnan(sig.loc[d, "TAKER7"])


def test_the_moving_average_is_sum_over_n_like_e038():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = dd.rolling_mean_available(vals, 3)
    assert np.isnan(out[1]) and out[2] == sum([1.0, 2.0, 3.0]) / 3 and out[4] == sum([3.0, 4.0, 5.0]) / 3


def test_trading_arithmetic_round_trip_and_keep_on_nan():
    close = np.full(10, 100.0)
    tg = np.array([1, np.nan, np.nan, 0, np.nan, 1, 1, 0, np.nan, np.nan], dtype=float)
    r = dd.simulate(close, tg, 0.0125)
    assert [a[1] for a in r["actions"]] == [1, -1, 1, -1]
    assert r["eq"][-1] == pytest.approx(150 * (1 - 0.0125) ** 4, rel=1e-12)
    frac = dd.simulate(close[:4], np.array([0.5, 0.6, 0.9, 0.0]), 0.0, fractional=True)
    assert [a[1] for a in frac["actions"]] == [1, 1, -1]  # 0.5 -> 0.6 is inside the 20% band; 0.9 and the exit are not


def test_holm_adjusts_in_order():
    adj = dd.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] == pytest.approx(0.06) and adj["b"] == pytest.approx(0.06)


def test_the_research_module_never_imports_the_execution_layer():
    import ast
    from pathlib import Path
    tree = ast.parse(Path("agent/research/daily_direction.py").read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | \
            {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.startswith("agent.execution") for m in names)
