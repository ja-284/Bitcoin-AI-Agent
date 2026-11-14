"""
The exchange boundary. A real venue (Firi or another, docs/platform/PLATFORM_PLAN.md section 12) will implement the
same small interface; until the owner chooses one, the only implementation is the simulated exchange used by the tests
and the website's fictional demo data. Orders are keyed by a client order id, so asking twice for the same hour finds
the first order instead of placing a second.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Fill:
    client_order_id: str
    side: str
    base_qty: float  # BTC bought or sold
    price: float  # average fill price, account currency per BTC
    quote_amount: float  # account currency spent (BUY, fee included) or received (SELL, fee deducted)
    fee: float  # in the account currency
    filled_at: datetime


class Exchange(Protocol):
    def find_order(self, client_order_id: str) -> Fill | None: ...

    def place_market_order(self, client_order_id: str, side: str, *, quote_amount: float = 0.0,
                           base_qty: float = 0.0, at: datetime) -> Fill: ...

    def balances(self) -> dict[str, float]: ...


class SimulatedExchange:
    """A deterministic venue for tests and demo data: fills at the set price, plus slippage, minus the fee."""

    def __init__(self, cash: float, *, fee_rate: float = 0.007, slippage: float = 0.0001, btc: float = 0.0):
        self.fee_rate, self.slippage = fee_rate, slippage
        self._balances = {"cash": cash, "btc": btc}
        self._orders: dict[str, Fill] = {}
        self.price: float | None = None

    def find_order(self, client_order_id: str) -> Fill | None:
        return self._orders.get(client_order_id)

    def place_market_order(self, client_order_id, side, *, quote_amount=0.0, base_qty=0.0, at):
        if client_order_id in self._orders:
            raise RuntimeError(f"duplicate client order id {client_order_id}: refusing a second order")
        if self.price is None or self.price <= 0:
            raise RuntimeError("no price set")
        if side == "BUY":
            if not 0 < quote_amount <= self._balances["cash"] + 1e-9:
                raise RuntimeError("insufficient cash")
            px = self.price * (1 + self.slippage)
            fee = quote_amount * self.fee_rate
            qty = (quote_amount - fee) / px
            self._balances["cash"] -= quote_amount
            self._balances["btc"] += qty
            fill = Fill(client_order_id, side, qty, px, quote_amount, fee, at)
        elif side == "SELL":
            if not 0 < base_qty <= self._balances["btc"] + 1e-12:
                raise RuntimeError("insufficient BTC")
            px = self.price * (1 - self.slippage)
            gross = base_qty * px
            fee = gross * self.fee_rate
            self._balances["btc"] -= base_qty
            self._balances["cash"] += gross - fee
            fill = Fill(client_order_id, side, base_qty, px, gross - fee, fee, at)
        else:
            raise ValueError(f"unknown side {side}")
        self._orders[client_order_id] = fill
        return fill

    def balances(self) -> dict[str, float]:
        return dict(self._balances)
