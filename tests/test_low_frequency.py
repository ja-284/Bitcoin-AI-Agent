"""
E038's research simulator (agent/research/low_frequency.py, compared with the engine by tools/e038_low_frequency.py),
on synthetic paths only: the lean copy must reproduce the
production engine exactly, the caps must hold in every rolling 24 h, risk exits must not need the allowance, the
selectors must be point in time, and costs must be charged exactly. Nothing here reads data/ or a database.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from agent.execution import strategy as st
from agent.research import low_frequency as lf

_spec = importlib.util.spec_from_file_location("e038_low_frequency", Path("tools/e038_low_frequency.py"))
e038 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e038)

T0 = 500_000  # hours since the epoch (2027); any value works


def path(n=1500, seed=7, crash_at=900):
    rng = np.random.default_rng(seed)
    hours = np.arange(T0, T0 + n + 3, dtype=np.int64)
    hours = np.delete(hours, [400, 401, 402])  # a gap of three missing hours
    r = rng.normal(0.0003, 0.01, n)
    r[crash_at:crash_at + 6] = -0.06  # about -30% in six hours: the risk exits must fire, even at a partial size
    close = 30_000 * np.exp(np.cumsum(r))
    sig = np.zeros(n, dtype=np.int8)
    for i in range(1, n):  # sticky signals with occasional flips
        sig[i] = sig[i - 1] if rng.random() < 0.85 else rng.choice([-1, 0, 1])
    sig[crash_at - 30:crash_at + 6] = 1  # invested into the crash, so every cap meets a risk exit
    score = np.clip(sig * 0.2 + rng.normal(0, 0.12, n), -1, 1)
    rv = np.abs(rng.normal(0.006, 0.003, n))
    rv[rng.random(n) < 0.03] = np.nan
    p = np.clip(rng.normal(0.4, 0.15, n), 0.01, 0.99)
    p[rng.random(n) < 0.03] = np.nan
    return hours, close, sig, score, rv, p


@pytest.mark.parametrize("cap", [4, 2, 1])
@pytest.mark.parametrize("c", [0.0, 0.0125])
def test_the_lean_simulator_reproduces_the_production_engine_exactly(cap, c):
    hours, close, sig, score, rv, p = path()
    lean = lf.simulate(hours, close, sig, rv, p, 0, len(hours), c, cap, True)
    ref_actions, ref_eq = e038.reference_run(hours, close, sig, rv, p, 0, len(hours), c, cap)
    assert [(a[0], a[1]) for a in lean["actions"]] == ref_actions
    assert len(ref_actions) > 10 and lean["halts"] >= 1
    assert abs(lean["eq_after"][-1] - ref_eq) <= 1e-9 * ref_eq
    assert st.MAX_TRADES_24H == 4  # the override is always restored


@pytest.mark.parametrize("cap", [1, 2])
@pytest.mark.parametrize("resize", [True, False])
def test_no_rolling_24_hours_ever_holds_more_normal_actions_than_the_cap(cap, resize):
    hours, close, sig, score, rv, p = path(seed=11)
    res = lf.simulate(hours, close, sig, rv, p, 0, len(hours), 0.0011, cap, resize)
    normal = [hours[a[0]] * 60 + lf.DECISION_DELAY_MIN for a in res["actions"] if not a[4]]
    for i, t in enumerate(normal):
        assert sum(1 for u in normal[: i + 1] if t - u < 1440) <= cap


def test_a_risk_exit_sells_even_when_the_allowance_is_used_up():
    n = 60
    hours = np.arange(T0, T0 + n, dtype=np.int64)
    close = np.full(n, 30_000.0)
    close[30:] = 25_000.0  # -16.7% within 24 h of the entry
    sig = np.ones(n, dtype=np.int8)
    rv, p = np.full(n, 0.004), np.full(n, 0.3)
    res = lf.simulate(hours, close, sig, rv, p, 0, n, 0.0125, 1, False)
    sides = [(a[0], a[1], a[4]) for a in res["actions"]]
    assert sides[0][:2] == (0, 1)  # the one allowed entry
    assert (30, -1, True) in sides  # the exit, inside the same 24 h, as a risk exit
    assert res["halts"] == 1


def test_a_round_trip_costs_exactly_the_per_side_cost_twice_on_a_flat_price():
    n = 40
    hours = np.arange(T0, T0 + n, dtype=np.int64)
    close = np.full(n, 30_000.0)
    sig = np.array([1] + [0] * 29 + [-1] + [0] * 9, dtype=np.int8)  # the exit after 30 h: outside the 24 h window
    rv, p = np.full(n, 0.004), np.full(n, 0.3)
    c = 0.0125
    res = lf.simulate(hours, close, sig, rv, p, 0, n, c, 1, False)
    assert [a[1] for a in res["actions"]] == [1, -1]
    assert res["eq_after"][-1] == pytest.approx(150 * (1 - c) ** 2, rel=1e-12)


def _changed_after(arrs, t, seed=3):
    rng = np.random.default_rng(seed)
    out = [a.copy() for a in arrs]
    for a in out:
        if a.dtype == np.int8:
            a[t + 1:] = rng.choice([-1, 0, 1], size=len(a) - t - 1)
        else:
            a[t + 1:] = a[t + 1:] * rng.uniform(0.5, 1.5, size=len(a) - t - 1)
    return out


def test_every_selector_is_point_in_time():
    hours, close, sig, score, rv, p = path()
    t = int(np.where(hours % 24 == 23)[0][40])  # a 23:00 row, so the daily vote decides there
    c2, s2, sc2 = _changed_after([close, sig, score], t)
    assert (lf.persist(hours, sig)[: t + 1] == lf.persist(hours, s2)[: t + 1]).all()
    assert (lf.daily_vote(hours, score)[: t + 1] == lf.daily_vote(hours, sc2)[: t + 1]).all()
    assert np.array_equal(lf.strong_threshold(score)[: t + 1], lf.strong_threshold(sc2)[: t + 1], equal_nan=True)
    old_min = lf.GATE_MIN_OBS
    lf.GATE_MIN_OBS = 20  # the synthetic path is short; the rule is the same
    try:
        a = lf.gate_mu(hours, close, sig)[: t + 1]
        b = lf.gate_mu(hours, c2, s2)[: t + 1]
    finally:
        lf.GATE_MIN_OBS = old_min
    assert np.array_equal(a, b, equal_nan=True) and not np.isnan(a).all()


def test_the_strong_threshold_is_numpys_quantile_of_the_earlier_rows():
    rng = np.random.default_rng(5)
    score = rng.normal(0, 0.2, 2600)
    q = lf.strong_threshold(score)
    assert np.isnan(q[: lf.STRONG_MIN_HISTORY]).all()
    for i in (2000, 2301, 2599):
        assert q[i] == pytest.approx(np.quantile(np.abs(score[:i]), 0.9), rel=1e-12)


def test_the_cost_gate_needs_more_than_a_round_trip_and_never_trades_without_enough_history():
    mu = np.array([np.nan, 0.03, 0.02, -0.03, 0.0])
    assert lf.gate(mu, 0.0125).tolist() == [0, 1, 0, -1, 0]


def test_the_registered_constants_still_match_rule_1_0():
    e038.check_constants()  # raises if strategy.py changed since E038 was registered
