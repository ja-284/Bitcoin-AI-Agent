"""
One hour of execution: reconcile with the exchange, decide, place at most one order, update the strategy's portfolio.

The engine owns the bookkeeping the pure strategy does not: the idempotent client order id, the fill accounting, the
peak and the trade history, the halt after a risk exit, and the reconciliation that halts trading when the ledger and
the exchange disagree. It persists nothing itself; the caller stores the returned decision, fill and portfolio (the
storage layer waits for the owner's approval, docs/platform/PLATFORM_PLAN.md section 12).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from agent.execution.exchange import Exchange, Fill
from agent.execution.strategy import STRATEGY_VERSION, Decision, Portfolio, Settings, Snapshot, decide

RECONCILE_TOLERANCE = 0.01  # account currency / its BTC equivalent; the ledger may never exceed the venue by more


def client_order_id(as_of: datetime, strategy_version: str = STRATEGY_VERSION) -> str:
    return f"{strategy_version}:{as_of.strftime('%Y-%m-%dT%H')}"


@dataclass(frozen=True)
class HourResult:
    decision: Decision | None
    fill: Fill | None
    portfolio: Portfolio
    note: str


def reconcile(portfolio: Portfolio, balances: dict[str, float], price: float) -> str | None:
    """None when the venue holds at least what the ledger says the strategy owns; otherwise the reason."""
    if balances.get("cash", 0.0) + RECONCILE_TOLERANCE < portfolio.cash:
        return f"exchange cash {balances.get('cash', 0.0):.2f} is below the ledger's {portfolio.cash:.2f}"
    if (balances.get("btc", 0.0) - portfolio.btc) * price < -RECONCILE_TOLERANCE:
        return f"exchange BTC {balances.get('btc', 0.0):.8f} is below the ledger's {portfolio.btc:.8f}"
    return None


def apply_fill(portfolio: Portfolio, fill: Fill) -> Portfolio:
    if fill.side == "BUY":
        cash, btc = portfolio.cash - fill.quote_amount, portfolio.btc + fill.base_qty
    else:
        cash, btc = portfolio.cash + fill.quote_amount, portfolio.btc - fill.base_qty
    return replace(portfolio, cash=max(cash, 0.0), btc=max(btc, 0.0), last_trade_at=fill.filled_at,
                   last_trade_side=fill.side, trade_times=portfolio.trade_times + (fill.filled_at,))


def run_hour(snapshot: Snapshot, portfolio: Portfolio, settings: Settings, exchange: Exchange, now: datetime) -> HourResult:
    oid = client_order_id(snapshot.as_of)
    earlier = exchange.find_order(oid)
    if earlier is not None:
        return HourResult(None, earlier, portfolio, f"this hour's order {oid} already exists; nothing new was placed")

    problem = reconcile(portfolio, exchange.balances(), snapshot.price)
    if problem and portfolio.halted is None:
        portfolio = replace(portfolio, halted=f"reconciliation failed: {problem}")

    decision = decide(snapshot, portfolio, settings, now)
    fill = None
    if decision.order is not None:
        o = decision.order
        fill = exchange.place_market_order(oid, o.side, quote_amount=o.quote_amount, base_qty=o.base_qty, at=now)
        portfolio = apply_fill(portfolio, fill)
    equity = portfolio.equity(snapshot.price)
    portfolio = replace(portfolio, peak_equity=max(portfolio.peak_equity, equity))
    if decision.halt:
        portfolio = replace(portfolio, halted=decision.halt)
    return HourResult(decision, fill, portfolio, decision.reasons[-1] if decision.reasons else "")
