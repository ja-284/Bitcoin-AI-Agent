"""
Papirhandelens motor (agent/papertrade/engine.py), bare på syntetiske data: helt inn / helt ut gir nøyaktig E040s
tall (protection_goal.run_window) også med stopp, størrelsesmodus handler bare utenfor båndet, Firi-bokens kjøps- og
salgskurser brukes riktig, og størrelsesreglene er som registrert i E041.
"""

import math

import numpy as np
import pytest

from agent.papertrade import engine
from agent.research import protection_goal as pg

NAN = math.nan


def _path(n=400, seed=5):
    rng = np.random.default_rng(seed)
    close = (100 * np.exp(np.cumsum(rng.normal(0, 0.04, n)))).tolist()
    des = rng.choice([1.0, 0.0, NAN], size=n, p=[0.15, 0.1, 0.75]).tolist()
    return close, des


@pytest.mark.parametrize("ov", [{}, {"sl": 0.10}, {"tr": 0.15}, {"tstop": 7}])
def test_all_in_mode_reproduces_e040_to_the_last_bit(ov):
    close, des = _path()
    for s, e in ((0, 399), (17, 60), (100, 105), (250, 330)):
        st = engine.State(cash=1.0)
        for i in range(s, e):
            st = engine.step(st, des[i], close[i], 0.0125, **ov).state
        assert st.cash + st.btc * close[e] == pg.run_window(des, close, s, e, 0.0125, **ov)[0]


def test_size_mode_trades_only_outside_the_band_and_exits_fully():
    st = engine.State(cash=1.0)
    acts = []
    for w, size in ((1.0, 0.5), (NAN, 0.6), (NAN, 0.9), (0.0, 0.9)):
        r = engine.step(st, w, 100.0, 0.0, size=size)
        st = r.state
        acts.append(r.action)
    assert acts == ["BUY", "NONE", "BUY", "SELL"] and st.btc == 0.0 and st.cash == pytest.approx(1.0)


def test_firi_prices_buy_at_ask_and_sell_at_bid_with_the_fee():
    st = engine.State(cash=500.0)
    r = engine.step(st, 1.0, 100.0, 0.007, buy_px=101.0, sell_px=99.0, mark_px=99.0)
    assert r.action == "BUY" and r.state.btc == pytest.approx(500 * (1 - 0.007) / 101.0)
    r2 = engine.step(r.state, 0.0, 100.0, 0.007, buy_px=101.0, sell_px=99.0, mark_px=99.0)
    assert r2.action == "SELL" and r2.value == pytest.approx(500 * (1 - 0.007) / 101.0 * 99.0 * (1 - 0.007))


def test_the_registered_size_rules():
    assert engine.size_for("full", 0.4, 0.03) is None
    assert engine.size_for("msmore", 0.40, None) == pytest.approx(0.5)
    assert engine.size_for("msmore", 0.10, None) == 0.25 and engine.size_for("msmore", 0.9, None) == 1.0
    assert engine.size_for("msless", 0.40, None) == pytest.approx(0.5)
    assert engine.size_for("msless", None, None) == 0.25 and engine.size_for("vol", None, NAN) == 0.25
    assert engine.size_for("vol", None, 0.0294) == 1.0 and engine.size_for("vol", None, 0.0588) == pytest.approx(0.5)


def test_the_step_never_changes_the_state_it_was_given():
    st = engine.State(cash=1.0)
    engine.step(st, 1.0, 100.0, 0.01)
    assert st == engine.State(cash=1.0)


def test_every_trade_records_why_it_happened():
    st = engine.State(cash=1.0)
    r = engine.step(st, 1.0, 100.0, 0.0, sl=0.10)
    assert (r.action, r.reason) == ("BUY", "signal")
    assert engine.step(r.state, NAN, 89.0, 0.0, sl=0.10).reason == "stop_loss"
    t = engine.step(engine.step(st, 1.0, 100.0, 0.0, tr=0.15).state, NAN, 120.0, 0.0, tr=0.15)
    assert engine.step(t.state, NAN, 101.0, 0.0, tr=0.15).reason == "trailing_stop"
    assert engine.step(engine.step(st, 1.0, 100.0, 0.0, tstop=1).state, NAN, 100.0, 0.0, tstop=1).reason == "time_stop"
    assert engine.step(r.state, 0.0, 100.0, 0.0).reason == "signal"
    assert engine.step(st, NAN, 100.0, 0.0).reason is None
    a = engine.step(st, 1.0, 100.0, 0.0, size=0.5)
    assert a.reason == "signal" and engine.step(a.state, NAN, 100.0, 0.0, size=0.9).reason == "rebalance"
