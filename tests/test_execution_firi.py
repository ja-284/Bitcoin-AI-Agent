"""
The Firi adapter (agent/execution/firi.py), against a fake HTTP session: no request leaves the machine.

The two signature vectors were produced on 2026-11-14 by Node.js running the exact snippet in Firi's documentation
(developers.firi.com, "POST requests and HMAC authentication"), with the documentation's own example secret and a fixed
timestamp of 1700000000. They pin the signing to Firi's reference implementation, not to this module's own idea of it.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from agent.execution import firi
from agent.execution.firi import Credentials, FiriClient, FiriError, FiriExchange

DOC_SECRET = "RTk2eNs67Vpan3345pmrwYEBYsWXRXtGF3BKTFq8WMLLOLOL"  # Firi's published example, not a real key
NODE_GET = "5ec9cfa5a5a7517dd75a15861e0b8887b92c847f52c825f37c5f5797efea0e81"
NODE_POST = "2a9adbf408f9e02c603698a1d7a9b86a76d6fde93b3e1078ef19b08c49972db6"
AT = datetime(2030, 1, 1, 11, 13, tzinfo=timezone.utc)


def test_signatures_match_firis_reference_implementation():
    assert firi.signature(DOC_SECRET, "1700000000") == NODE_GET
    body = {"market": "BTCNOK", "price": "1000", "type": "ask", "amount": "1"}
    assert firi.signature(DOC_SECRET, "1700000000", body) == NODE_POST


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload
        self.text = "" if payload is None else "x"

    def json(self):
        return self._p


class FakeFiri:
    """Plays Firi: a ticker, balances that change when an order fills, an order that fills partly and is cancelled."""

    def __init__(self, fill_fraction=1.0, fee=0.007):
        self.calls, self.nok, self.btc = [], 1000.0, 0.0
        self.bid, self.ask = 625_000.0, 633_000.0
        self.fill_fraction, self.fee = fill_fraction, fee
        self.order_state = None

    def get(self, url, timeout):
        self.calls.append(("GET", url, None, None, None))
        assert url.endswith("/v2/markets/BTCNOK/ticker")
        return Resp(200, {"bid": str(self.bid), "ask": str(self.ask), "spread": str(self.ask - self.bid)})

    def request(self, method, url, params, headers, data, timeout):
        self.calls.append((method, url, params, headers, data))
        path = url.replace(firi.BASE_URL, "")
        if path == "/v2/balances":
            return Resp(200, [{"currency": "NOK", "available": str(self.nok), "balance": str(self.nok), "hold": "0"},
                              {"currency": "BTC", "available": str(self.btc), "balance": str(self.btc), "hold": "0"}])
        if method == "POST" and path == "/v2/orders":
            import json
            b = json.loads(data)
            amount, price = float(b["amount"]), float(b["price"])
            filled = amount * self.fill_fraction
            if b["type"] == "bid":
                self.nok -= filled * self.ask * (1 + self.fee)
                self.btc += filled
            else:
                self.nok += filled * self.bid * (1 - self.fee)
                self.btc -= filled
            self.order_state = {"id": 7, "remaining": str(amount - filled), "matched": str(filled)}
            return Resp(201, {"id": 7})
        if method == "GET" and path == "/v2/order/7":
            return Resp(200, [self.order_state])
        if method == "DELETE" and path == "/v2/orders/7/detailed":
            return Resp(200, {"matched": self.order_state["matched"]})
        return Resp(404, {"error": path})


CREDS = Credentials(api_key="k-test", client_id="c-test", secret=DOC_SECRET)


def client(fake):
    return FiriClient(CREDS, session=fake, clock=lambda: 1700000000)


def test_private_calls_carry_the_signature_headers_and_the_query_and_never_show_the_secret():
    fake = FakeFiri()
    client(fake).balances()
    method, url, params, headers, data = fake.calls[-1]
    assert params == {"timestamp": "1700000000", "validity": "2000"}
    assert headers["firi-user-signature"] == NODE_GET
    assert headers["firi-user-clientid"] == "c-test" and headers["firi-access-key"] == "k-test"
    assert DOC_SECRET not in repr(CREDS) and DOC_SECRET not in str(headers)


def test_a_buy_is_a_marketable_limit_order_whose_rest_is_cancelled_and_whose_fill_comes_from_the_balances():
    fake = FakeFiri(fill_fraction=0.9)
    ex = FiriExchange(client(fake), sleep=lambda s: None)
    fill = ex.place_market_order("rule-1.0:2030-01-01T10", "BUY", quote_amount=150.0, at=AT)
    post = next(c for c in fake.calls if c[0] == "POST")
    body = __import__("json").loads(post[4])
    assert list(body) == ["market", "price", "type", "amount"] and body["type"] == "bid"
    assert Decimal(body["price"]) == Decimal(str(round(633_000 * (1 + firi.MAX_SLIPPAGE), 2)))
    assert post[3]["firi-user-signature"] == firi.signature(DOC_SECRET, "1700000000", body)
    assert any(c[0] == "DELETE" for c in fake.calls), "the resting remainder must be cancelled"
    assert fill.side == "BUY" and fill.base_qty == pytest.approx(fake.btc)
    assert fill.quote_amount == pytest.approx(1000.0 - fake.nok)
    assert fill.fee > 0 and fill.client_order_id.endswith("#firi:7")


def test_a_sell_uses_an_ask_below_the_bid_and_nothing_is_cancelled_when_it_filled():
    fake = FakeFiri()
    fake.btc = 0.0002
    ex = FiriExchange(client(fake), sleep=lambda s: None)
    fill = ex.place_market_order("rule-1.0:2030-01-01T10", "SELL", base_qty=0.0002, at=AT)
    body = __import__("json").loads(next(c for c in fake.calls if c[0] == "POST")[4])
    assert body["type"] == "ask" and float(body["price"]) < fake.bid and body["amount"] == "0.00020000"
    assert not any(c[0] == "DELETE" for c in fake.calls)
    assert fill.side == "SELL" and fill.base_qty == pytest.approx(0.0002)


def test_an_order_that_did_not_fill_is_an_error_not_a_trade():
    fake = FakeFiri(fill_fraction=0.0)
    with pytest.raises(FiriError):
        FiriExchange(client(fake), sleep=lambda s: None).place_market_order("x", "BUY", quote_amount=150.0, at=AT)


def test_http_errors_and_missing_credentials_fail_loudly(monkeypatch):
    class Bad(FakeFiri):
        def request(self, *a, **k):
            return Resp(401, {"error": "Invalid Signature"})
    with pytest.raises(FiriError):
        client(Bad()).balances()
    for n in ("FIRI_API_KEY", "FIRI_CLIENT_ID", "FIRI_SECRET_KEY"):
        monkeypatch.delenv(n, raising=False)
    with pytest.raises(FiriError):
        Credentials.from_env()
    with pytest.raises(FiriError):
        FiriClient(None, session=FakeFiri()).balances()
