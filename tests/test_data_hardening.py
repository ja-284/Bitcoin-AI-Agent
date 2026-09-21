"""
Backend Phase B: the data layer must fail loudly on bad answers and never hang.

- a JSON error object or a wrongly shaped candle list is a schema error, never data;
- transient failures get one retry per endpoint, rate limits do not;
- the RSS download is bounded by a timeout and parsing happens on bytes we fetched;
- every external client is constructed with an explicit timeout.
"""

from datetime import datetime, timedelta, timezone

import pytest
import requests

import agent.data_providers.binance as bn
from agent.news import rss_source


class _Resp:
    def __init__(self, status=200, body=None, raise_exc=None):
        self.status_code, self._body, self._raise = status, body, raise_exc

    def raise_for_status(self):
        if self._raise:
            raise self._raise
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _kline(ts_ms: int):
    return [ts_ms, "100", "101", "99", "100.5", "5", ts_ms + 3_599_999, "500", 42, "2.5", "250", "0"]


def _no_sleep(monkeypatch):
    monkeypatch.setattr(bn.time, "sleep", lambda s: None)


def test_error_object_is_a_schema_error_not_data(monkeypatch):
    _no_sleep(monkeypatch)
    monkeypatch.setattr(bn.requests, "get", lambda *a, **k: _Resp(200, {"code": -1121, "msg": "Invalid symbol."}))
    with pytest.raises(RuntimeError, match="error object"):
        bn._get_klines({"symbol": "BTCUSDT"})


def test_wrong_shape_and_non_numeric_are_schema_errors(monkeypatch):
    _no_sleep(monkeypatch)
    for body in ([[1, 2, 3]], [["x"] * 12], "not a list"):
        monkeypatch.setattr(bn.requests, "get", lambda *a, _b=body, **k: _Resp(200, _b))
        with pytest.raises(RuntimeError):
            bn._get_klines({"symbol": "BTCUSDT"})


def test_valid_payload_passes_through(monkeypatch):
    _no_sleep(monkeypatch)
    payload = [_kline(1_700_000_000_000)]
    monkeypatch.setattr(bn.requests, "get", lambda *a, **k: _Resp(200, payload))
    assert bn._get_klines({"symbol": "BTCUSDT"}) == payload


def test_transient_failure_is_retried_once_per_endpoint_then_next_endpoint(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if len(calls) < 3:
            raise requests.ConnectionError("reset")
        return _Resp(200, [_kline(1_700_000_000_000)])

    monkeypatch.setattr(bn.requests, "get", fake_get)
    bn._get_klines({"symbol": "BTCUSDT"})
    assert calls == [bn.BASE_URLS[0], bn.BASE_URLS[0], bn.BASE_URLS[1]]  # 1 retry on the first, then the second


def test_rate_limit_is_not_retried_on_the_same_endpoint(monkeypatch):
    _no_sleep(monkeypatch)
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(429, None) if url == bn.BASE_URLS[0] else _Resp(200, [_kline(1_700_000_000_000)])

    monkeypatch.setattr(bn.requests, "get", fake_get)
    bn._get_klines({"symbol": "BTCUSDT"})
    assert calls == [bn.BASE_URLS[0], bn.BASE_URLS[1]]


def test_all_endpoints_down_raises_with_the_last_error(monkeypatch):
    _no_sleep(monkeypatch)
    monkeypatch.setattr(bn.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("slow")))
    with pytest.raises(RuntimeError, match="slow"):
        bn._get_klines({"symbol": "BTCUSDT"})


def test_rss_download_is_bounded_and_parsed_from_bytes(monkeypatch):
    seen = {}

    class R:
        content = b'<?xml version="1.0"?><rss><channel><item><title>t</title><link>http://x</link><pubDate>Mon, 21 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>'

        def raise_for_status(self):
            pass

    def fake_get(url, timeout=None, headers=None):
        seen["timeout"], seen["ua"] = timeout, headers.get("User-Agent")
        return R()

    monkeypatch.setattr(rss_source.requests, "get", fake_get)
    items = rss_source.fetch_feed("Test", "http://feed")
    assert seen["timeout"] == rss_source.FETCH_TIMEOUT_S and seen["ua"]
    assert len(items) == 1 and items[0].published_at == datetime(2026, 9, 21, 10, tzinfo=timezone.utc)


def test_rss_timeout_becomes_a_feed_failure_not_a_hang(monkeypatch):
    monkeypatch.setattr(rss_source.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("slow feed")))
    with pytest.raises(requests.Timeout):
        rss_source.fetch_feed("Test", "http://feed")
    items, failed = rss_source.fetch_all_feeds()
    assert items == [] and set(failed) == set(rss_source.FEEDS)


def test_external_clients_have_explicit_timeouts():
    from agent.config.settings import AI_MAX_RETRIES, AI_TIMEOUT_S, DB_CONNECT_TIMEOUT_S

    assert 0 < AI_TIMEOUT_S <= 120 and 0 <= AI_MAX_RETRIES <= 3 and 0 < DB_CONNECT_TIMEOUT_S <= 30
    import inspect

    from agent.ai import explainer, news_scorer
    from agent.database import db

    for mod in (explainer, news_scorer):
        assert "timeout=AI_TIMEOUT_S" in inspect.getsource(mod)
    assert "connect_timeout=DB_CONNECT_TIMEOUT_S" in inspect.getsource(db)
