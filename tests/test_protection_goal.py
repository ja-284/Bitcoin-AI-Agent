"""
E040s motor (agent/research/protection_goal.py), bare på syntetiske data: fersk start, at ingen handel teller som
«ikke tap», kostnadsregningen, stop-loss, glidende stopp og tidsstopp, sperren etter et stopp, perioder som aldri
krysser en grense, og at de nye inndataene er punkt i tid. Ingenting her leser data/.
"""

import math

import numpy as np
import pandas as pd
import pytest

from agent.research import protection_goal as pg

NAN = math.nan


def test_no_trade_is_a_success_and_a_round_trip_costs_twice():
    close = [100.0] * 6
    assert pg.run_window([NAN] * 6, close, 0, 5, 0.0125)[0] == 1.0
    final, trades, _ = pg.run_window([1, NAN, 0, NAN, NAN, NAN], close, 0, 5, 0.0125)
    assert trades == 2 and final == pytest.approx((1 - 0.0125) ** 2, rel=1e-12)


def test_stop_loss_blocks_reentry_until_the_base_rule_turns_off():
    close = [100, 95, 89, 90, 91, 92, 93, 94]
    des = [1, 1, 1, 1, 0, 1, 1, NAN]
    final, trades, _ = pg.run_window(des, close, 0, 7, 0.0, sl=0.10)
    # buy 100, stop at 89 (<= 90), blocked while des stays 1, released by the 0 on row 4, buy again at 92
    assert trades == 3 and final == pytest.approx(0.89 * 94 / 92, rel=1e-12)


def test_trailing_stop_and_time_stop():
    close = [100, 120, 101, 105, 106]
    final, trades, _ = pg.run_window([1, NAN, NAN, NAN, NAN], close, 0, 4, 0.0, tr=0.15)
    assert trades == 2 and final == pytest.approx(1.01, rel=1e-12)  # 101 <= 120 * 0.85 = 102
    final, trades, _ = pg.run_window([1, NAN, 1, NAN, NAN], [100, 101, 102, 103, 104], 0, 4, 0.0, tstop=2)
    assert trades == 2 and final == pytest.approx(1.02, rel=1e-12)  # held 2 days, sold at 102; no block, re-buy needs a trigger


def test_windows_are_exact_calendar_spans_inside_one_period():
    days = pd.date_range("2023-12-01", "2024-01-20", freq="D", tz="UTC").as_unit("ns").delete([10])
    lo, hi = 0, int(days.searchsorted(pd.Timestamp("2023-12-31", tz="UTC")))
    wins = pg.windows(days, lo, hi, 5)
    assert all((days[e] - days[s]).days == 5 and e <= hi for s, e in wins)
    assert not any(days[s] + pd.Timedelta(days=5) == days[0] + pd.Timedelta(days=10) for s, _ in wins)  # the missing day


def test_new_inputs_are_point_in_time():
    rng = np.random.default_rng(2)
    days = pd.date_range("2030-01-01", periods=400, freq="D", tz="UTC").as_unit("ns")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 400))), index=days)
    base = pd.DataFrame({"close": close, "SMA20": close.rolling(20).mean(), "SIGMA30": close.pct_change().rolling(30).std()})
    a = pg.add_inputs(base)
    later = base.copy()
    later.loc[days[300]:, ["close", "SIGMA30"]] *= 1.7
    b = pg.add_inputs(later)
    cols = ["SMA50", "SMA100", "calm", "HI20", "LO20", "HI55", "LO10"]
    x, y = a.loc[:days[299], cols], b.loc[:days[299], cols]
    assert ((x == y) | (x.isna() & y.isna())).all().all()


def test_the_registered_strategy_count():
    days = pd.date_range("2030-01-01", periods=300, freq="D", tz="UTC").as_unit("ns")
    df = pd.DataFrame(0.01, index=days, columns=["sig23", "vote", "R1", "R7", "R14", "R28", "R56", "R84", "R182",
                                                 "MA20", "MA50", "MA100", "MA200", "X20_100", "X50_200", "TREND",
                                                 "calm", "HI20", "LO20", "HI55", "LO10"])
    df["close"] = 100.0
    assert len(pg.strategies(df)) == 104
