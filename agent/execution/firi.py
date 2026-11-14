"""
The Firi adapter (https://developers.firi.com, read 2026-11-14): BTC/NOK on the owner's own Firi account.

What Firi's API is, and what that means here:
- Private calls are signed: HMAC-SHA256 with the secret key over JSON.stringify({timestamp, validity, ...body}), hex;
  headers `firi-user-signature` and `firi-user-clientid`; `timestamp` (epoch seconds) and `validity` (milliseconds)
  in the query string. The key, client id and secret come from the environment only; nothing here prints them.
- Withdrawals are impossible through the API (Firi's own rule), so a leaked key cannot move money out.
- Orders are LIMIT orders only (`bid` / `ask`) and carry no client order id. A "market" order is therefore a
  marketable limit order a little through the best price (MAX_SLIPPAGE), followed by cancelling whatever rests.
  Idempotency comes from the caller recording the hour's intent BEFORE the order is sent (the storage layer);
  this adapter never retries an order.
- The fill is measured from the balances before and after, so the fee is counted whatever form Firi charges it in.

Nothing here runs by itself. It is used only by the execution engine, after the owner has created a key and the
storage layer and the dry run are in place (docs/platform/PLATFORM_PLAN.md).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

import requests

from agent.execution.exchange import Fill

BASE_URL = "https://api.firi.com"
MARKET = "BTCNOK"
VALIDITY_MS = "2000"
TIMEOUT_S = 15
MAX_SLIPPAGE = 0.0025  # the worst price a "market" order accepts, beyond the best quote
REST_SECONDS = 3.0  # how long a marketable order may rest before the remainder is cancelled


class FiriError(RuntimeError):
    pass


def canonical(payload: dict) -> str:
    """Exactly what Node's JSON.stringify produces for these string-valued fields: no spaces, insertion order."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def signature(secret: str, timestamp: str, body: dict | None = None, validity: str = VALIDITY_MS) -> str:
    payload = {"timestamp": timestamp, "validity": validity, **(body or {})}
    return hmac.new(secret.encode(), canonical(payload).encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Credentials:
    api_key: str
    client_id: str
    secret: str

    @staticmethod
    def from_env() -> "Credentials":
        names = ("FIRI_API_KEY", "FIRI_CLIENT_ID", "FIRI_SECRET_KEY")
        values = [os.environ.get(n, "") for n in names]
        missing = [n for n, v in zip(names, values) if not v]
        if missing:
            raise FiriError(f"missing environment variables: {', '.join(missing)}")
        return Credentials(*values)

    def __repr__(self) -> str:  # never show a key in a log or a traceback
        return "Credentials(<hidden>)"


class FiriClient:
    def __init__(self, creds: Credentials | None = None, session: requests.Session | None = None,
                 clock=time.time, base_url: str = BASE_URL):
        self.creds, self.session, self.clock, self.base = creds, session or requests.Session(), clock, base_url

    def _get_public(self, path: str) -> object:
        r = self.session.get(f"{self.base}{path}", timeout=TIMEOUT_S)
        return self._json(r, path)

    def _signed(self, method: str, path: str, body: dict | None = None) -> object:
        if self.creds is None:
            raise FiriError("this call needs credentials")
        ts = str(int(self.clock()))
        headers = {"firi-access-key": self.creds.api_key, "firi-user-clientid": self.creds.client_id,
                   "firi-user-signature": signature(self.creds.secret, ts, body), "Content-Type": "application/json"}
        params = {"timestamp": ts, "validity": VALIDITY_MS}
        data = canonical(body) if body is not None else None
        r = self.session.request(method, f"{self.base}{path}", params=params, headers=headers, data=data, timeout=TIMEOUT_S)
        return self._json(r, path)

    @staticmethod
    def _json(r, path: str) -> object:
        if r.status_code >= 400:
            raise FiriError(f"{path}: HTTP {r.status_code} {str(r.text)[:200]}")
        return r.json() if r.text else None

    # ---- public
    def ticker(self) -> tuple[float, float]:
        t = self._get_public(f"/v2/markets/{MARKET}/ticker")
        bid, ask = float(t["bid"]), float(t["ask"])
        if not 0 < bid <= ask:
            raise FiriError(f"implausible quote bid {bid} ask {ask}")
        return bid, ask

    # ---- private
    def balances(self) -> dict[str, float]:
        rows = self._signed("GET", "/v2/balances")
        return {r["currency"]: float(r["available"]) for r in rows}

    def place_limit(self, side: str, price: Decimal, amount: Decimal) -> int:
        # the field order of Firi's own signing example; the signed text and the sent body are the same string
        body = {"market": MARKET, "price": str(price), "type": {"BUY": "bid", "SELL": "ask"}[side], "amount": str(amount)}
        return int(self._signed("POST", "/v2/orders", body)["id"])

    def order(self, order_id: int) -> dict | None:
        rows = self._signed("GET", f"/v2/order/{order_id}")
        return rows[0] if rows else None

    def cancel(self, order_id: int) -> None:
        self._signed("DELETE", f"/v2/orders/{order_id}/detailed")


def _q(x: float, places: str) -> Decimal:
    return Decimal(str(x)).quantize(Decimal(places), rounding=ROUND_DOWN)


class FiriExchange:
    """The engine's exchange interface on Firi. `cash` is NOK, `btc` is BTC, as in the simulated exchange."""

    def __init__(self, client: FiriClient, sleep=time.sleep, find_order=None):
        self.client, self.sleep = client, sleep
        self._find = find_order or (lambda _oid: None)  # the storage layer supplies the hour's recorded order

    def find_order(self, client_order_id: str) -> Fill | None:
        return self._find(client_order_id)

    def balances(self) -> dict[str, float]:
        b = self.client.balances()
        return {"cash": b.get("NOK", 0.0), "btc": b.get("BTC", 0.0)}

    def place_market_order(self, client_order_id, side, *, quote_amount=0.0, base_qty=0.0, at: datetime) -> Fill:
        bid, ask = self.client.ticker()
        before = self.balances()
        if side == "BUY":
            limit = _q(ask * (1 + MAX_SLIPPAGE), "0.01")
            amount = _q(quote_amount / float(limit), "0.00000001")
        elif side == "SELL":
            limit = _q(bid * (1 - MAX_SLIPPAGE), "0.01")
            amount = _q(base_qty, "0.00000001")
        else:
            raise ValueError(f"unknown side {side}")
        if amount <= 0:
            raise FiriError("order amount rounds to zero")
        order_id = self.client.place_limit(side, limit, amount)
        self.sleep(REST_SECONDS)
        state = self.client.order(order_id)
        if state is not None and float(state.get("remaining") or 0) > 0:
            self.client.cancel(order_id)
        after = self.balances()
        nok = after["cash"] - before["cash"]
        btc = after["btc"] - before["btc"]
        if (side == "BUY" and btc <= 0) or (side == "SELL" and btc >= 0):
            raise FiriError(f"order {order_id} did not fill (NOK {nok:+.2f}, BTC {btc:+.8f})")
        mid = (bid + ask) / 2
        qty = abs(btc)
        quote = abs(nok)
        cost_vs_mid = (quote - qty * mid) if side == "BUY" else (qty * mid - quote)
        return Fill(client_order_id=f"{client_order_id}#firi:{order_id}", side=side, base_qty=qty, price=quote / qty,
                    quote_amount=quote, fee=max(cost_vs_mid, 0.0), filled_at=at)
