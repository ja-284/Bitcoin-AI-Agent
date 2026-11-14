"""
The execution layer (agent/execution, docs/platform/PLATFORM_PLAN.md): strategy rule-1.0, its risk limits, the engine's
idempotency and reconciliation, and the layer's isolation from the prediction engine. Only the simulated exchange is
used; nothing here talks to a venue or a database.
"""

import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.execution import strategy as s
from agent.execution.engine import client_order_id, reconcile, run_hour
from agent.execution.exchange import SimulatedExchange
from agent.execution.strategy import Portfolio, Settings, Snapshot, decide

T0 = datetime(2030, 1, 1, 10, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=1, minutes=13)  # the candle closed at 11:00, the job ran at 11:13
PRICE = 600_000.0


def snap(signal="BUY", rv=0.004, p=0.35, **kw):
    base = dict(as_of=T0, signal=signal, price=PRICE, rv_24=rv, p_large=p, pipeline_version="0.2.0", scoring_version="0.2.0")
    return Snapshot(**{**base, **kw})


SETTINGS = Settings(allocation_cap=150.0, min_order_value=20.0)


def cash_only(cash=150.0):
    return Portfolio(cash=cash, peak_equity=cash, equity_24h_ago=cash)


def invested(btc_value=140.0, cash=10.0, **kw):
    return Portfolio(cash=cash, btc=btc_value / PRICE, peak_equity=cash + btc_value, equity_24h_ago=cash + btc_value, **kw)


def test_buy_from_cash_invests_the_cap_times_the_size():
    d = decide(snap("BUY"), cash_only(), SETTINGS, NOW)
    assert d.action == "BUY" and d.order.quote_amount == pytest.approx(150.0)
    assert d.factors["size"] == 1.0 and d.factors["f_conf"] == 1.0


def test_sell_exits_fully_and_hold_keeps_the_position():
    d = decide(snap("SELL"), invested(), SETTINGS, NOW)
    assert d.action == "SELL" and d.order.base_qty == pytest.approx(140.0 / PRICE) and d.target_exposure == 0.0
    assert decide(snap("HOLD"), invested(), SETTINGS, NOW).action == "NONE"
    assert decide(snap("HOLD"), cash_only(), SETTINGS, NOW).action == "NONE"


def test_high_volatility_and_a_likely_large_move_reduce_the_size_and_missing_inputs_are_conservative():
    assert s.sizing_factors(snap(rv=0.012))["f_vol"] == pytest.approx(0.5)
    assert s.sizing_factors(snap(rv=0.1))["f_vol"] == s.F_VOL_MIN
    assert s.sizing_factors(snap(p=0.8))["f_move"] == pytest.approx(0.7)
    assert s.sizing_factors(snap(p=None))["f_move"] == s.F_MOVE_MIN
    assert s.sizing_factors(snap(rv=None))["f_vol"] == s.F_VOL_MIN
    d = decide(snap("BUY", rv=0.012), cash_only(), SETTINGS, NOW)
    assert d.order.quote_amount == pytest.approx(75.0)


def test_confidence_never_changes_the_size():
    a = decide(snap("BUY", confidence=0.2), cash_only(), SETTINGS, NOW)
    b = decide(snap("BUY", confidence=0.99), cash_only(), SETTINGS, NOW)
    assert a.order == b.order


def test_the_owners_pause_and_a_halt_stop_every_order_including_exits():
    paused = Settings(allocation_cap=150.0, paused=True, min_order_value=20.0)
    assert decide(snap("SELL"), invested(), paused, NOW).order is None
    assert decide(snap("BUY"), cash_only(), paused, NOW).order is None
    halted = replace(invested(), halted="reconciliation failed")
    assert decide(snap("SELL"), halted, SETTINGS, NOW).order is None


def test_a_doubtful_hour_may_reduce_risk_but_never_add_it():
    for bad in (dict(price_is_synthetic=True), dict(scoring_version="0.1.0"), dict(as_of=T0 - timedelta(hours=5))):
        assert decide(snap("BUY", **bad), cash_only(), SETTINGS, NOW).order is None, bad
        assert decide(snap("SELL", **bad), invested(), SETTINGS, NOW).action == "SELL", bad


def test_a_small_resize_is_skipped_but_a_full_exit_only_needs_the_venue_minimum():
    p = invested(btc_value=100.0, cash=50.0)
    d = decide(snap("BUY", rv=0.0055), p, SETTINGS, NOW)  # target 150*1.0 vs 100: change 50 >= band 30 -> trade
    assert d.action == "BUY"
    d = decide(snap("BUY", rv=0.0055), invested(btc_value=130.0, cash=20.0), SETTINGS, NOW)  # change 20 < band 30
    assert d.order is None and "too small" in d.reasons[-1]
    d = decide(snap("SELL"), invested(btc_value=25.0, cash=125.0), SETTINGS, NOW)  # full exit, 25 >= minimum 20
    assert d.action == "SELL"
    d = decide(snap("SELL"), invested(btc_value=15.0, cash=135.0), SETTINGS, NOW)  # below the venue minimum
    assert d.order is None


def test_a_reversal_within_the_minimum_holding_time_is_refused():
    p = invested(last_trade_at=NOW - timedelta(hours=3), last_trade_side="BUY", trade_times=(NOW - timedelta(hours=3),))
    d = decide(snap("SELL"), p, SETTINGS, NOW)
    assert d.order is None and "reverse" in d.reasons[-1]
    p = replace(p, last_trade_at=NOW - timedelta(hours=7), trade_times=(NOW - timedelta(hours=7),))
    assert decide(snap("SELL"), p, SETTINGS, NOW).action == "SELL"


def test_the_daily_trade_cap():
    times = tuple(NOW - timedelta(hours=h) for h in (20, 15, 10, 8))
    p = replace(cash_only(), trade_times=times, last_trade_side="SELL", last_trade_at=times[-1])
    d = decide(snap("BUY"), p, SETTINGS, NOW)
    assert d.order is None and "cap" in d.reasons[-1]


def test_the_risk_exits_flatten_and_halt_whatever_the_signal_says():
    p = replace(invested(btc_value=100.0, cash=0.0), peak_equity=150.0, equity_24h_ago=105.0)  # drawdown 33%
    d = decide(snap("BUY"), p, SETTINGS, NOW)
    assert d.risk_exit and d.action == "SELL" and d.halt == "drawdown limit reached"
    p = replace(invested(btc_value=120.0, cash=0.0), peak_equity=140.0, equity_24h_ago=140.0)  # -14% in 24 h
    d = decide(snap("HOLD"), p, SETTINGS, NOW)
    assert d.risk_exit and d.halt == "daily loss limit reached"
    # a risk exit overrides the minimum holding time
    p = replace(p, last_trade_at=NOW - timedelta(hours=1), last_trade_side="BUY")
    assert decide(snap("HOLD"), p, SETTINGS, NOW).action == "SELL"


def test_the_cap_is_bounded_in_code_and_orders_never_exceed_what_the_strategy_holds():
    with pytest.raises(ValueError):
        Settings(allocation_cap=s.HARD_MAX_ALLOCATION + 1)
    with pytest.raises(ValueError):
        Settings(allocation_cap=0)
    d = decide(snap("BUY"), cash_only(cash=60.0), SETTINGS, NOW)
    assert d.order.quote_amount <= 60.0
    d = decide(snap("SELL"), invested(), SETTINGS, NOW)
    assert d.order.base_qty <= 140.0 / PRICE


def test_hold_above_a_lowered_cap_trims_to_the_cap():
    d = decide(snap("HOLD"), invested(btc_value=145.0, cash=5.0), Settings(allocation_cap=100.0, min_order_value=20.0), NOW)
    assert d.action == "SELL" and d.target_exposure == pytest.approx(100.0)


def test_one_hour_places_at_most_one_order_even_when_run_twice():
    ex = SimulatedExchange(150.0, fee_rate=0.007)
    ex.price = PRICE
    first = run_hour(snap("BUY"), cash_only(), SETTINGS, ex, NOW)
    assert first.fill is not None and first.fill.client_order_id == client_order_id(T0)
    again = run_hour(snap("BUY"), first.portfolio, SETTINGS, ex, NOW + timedelta(minutes=10))
    assert again.decision is None and again.fill == first.fill and again.portfolio == first.portfolio
    with pytest.raises(RuntimeError):
        ex.place_market_order(client_order_id(T0), "BUY", quote_amount=1.0, at=NOW)


def test_fees_are_charged_and_the_portfolio_matches_the_exchange_after_a_round_trip():
    ex = SimulatedExchange(150.0, fee_rate=0.007, slippage=0.0)
    ex.price = PRICE
    r = run_hour(snap("BUY"), cash_only(), SETTINGS, ex, NOW)
    assert r.fill.fee == pytest.approx(150.0 * 0.007)
    later = T0 + timedelta(hours=8)
    r2 = run_hour(snap("SELL", as_of=later), replace(r.portfolio, equity_24h_ago=None), SETTINGS, ex,
                  later + timedelta(hours=1, minutes=13))
    assert r2.portfolio.btc == pytest.approx(0.0, abs=1e-15)
    assert r2.portfolio.cash == pytest.approx(150.0 * 0.993 * 0.993)
    assert reconcile(r2.portfolio, ex.balances(), PRICE) is None


def test_a_ledger_the_exchange_cannot_cover_halts_trading():
    ex = SimulatedExchange(100.0)
    ex.price = PRICE
    assert reconcile(cash_only(150.0), ex.balances(), PRICE) is not None
    r = run_hour(snap("BUY"), cash_only(150.0), SETTINGS, ex, NOW)
    assert r.fill is None and r.portfolio.halted.startswith("reconciliation failed")


def test_a_risk_exit_halts_the_portfolio_after_selling():
    ex = SimulatedExchange(0.0, btc=100.0 / PRICE, slippage=0.0)
    ex.price = PRICE
    p = replace(invested(btc_value=100.0, cash=0.0), peak_equity=150.0)
    r = run_hour(snap("BUY"), p, SETTINGS, ex, NOW)
    assert r.fill.side == "SELL" and r.portfolio.halted == "drawdown limit reached"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
    return out


def test_the_prediction_engine_and_its_research_never_import_the_execution_layer():
    engine = [Path("run.py"), *Path("agent").rglob("*.py")]
    for path in engine:
        if "execution" in path.parts:
            continue
        assert not any(m.startswith("agent.execution") for m in _imports(path)), path


def test_the_execution_layer_cannot_write_the_prediction_record():
    for path in Path("agent/execution").glob("*.py"):
        mods = _imports(path)
        assert not any(m.startswith(p) for m in mods for p in ("agent.database", "agent.shadow", "agent.orchestrator",
                                                               "agent.direction_shadow", "psycopg")), path
