"""
Primary market data source. Binance's public market-data endpoints need no account,
no API key, and return true OHLCV (open/high/low/close/volume) candles directly --
which is exactly the shape this project needs, and is not something CoinGecko's
free tier actually provides (see coingecko.py).
"""

import logging
import time
from datetime import datetime, timezone

import requests

from agent.data_providers.base import MarketDataProvider
from agent.shared.types import PriceBar

logger = logging.getLogger(__name__)

# The public market-data mirror comes first: Binance's main API refuses requests from
# US addresses, and GitHub's job runners are US-based. Same data, same format.
BASE_URLS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
]
SYMBOL = "BTCUSDT"

MAX_PER_REQUEST = 1000  # Binance's cap on candles per request
HOUR_MS = 3_600_000


class KlineSchemaError(ValueError):
    """The exchange answered, but not with candles in the documented shape."""


def _check_kline_schema(payload) -> list:
    """Binance klines are a list of 12-field lists: open time, o, h, l, c, v, close time, ... trades (8), taker buy base (9)."""
    if isinstance(payload, dict):  # {"code": -1121, "msg": "Invalid symbol."} and friends
        raise KlineSchemaError(f"exchange returned an error object: {payload}")
    if not isinstance(payload, list):
        raise KlineSchemaError(f"expected a list of candles, got {type(payload).__name__}")
    for k in payload:
        if not isinstance(k, (list, tuple)) or len(k) < 10:
            raise KlineSchemaError(f"candle with unexpected shape: {k!r}")
        try:
            int(k[0]); int(k[6]); int(k[8])
            for v in (k[1], k[2], k[3], k[4], k[5], k[9]):
                float(v)
        except (TypeError, ValueError) as exc:
            raise KlineSchemaError(f"candle with non-numeric field: {k!r}") from exc
    return payload


def _get_klines(params: dict, timeout: int = 15, retries: int = 1, backoff_s: float = 2.0) -> list:
    """
    Fetch candles, trying each endpoint with one retry for transient errors (timeouts, 5xx,
    connection resets). Rate-limit answers (429 / 418) are not retried on the same endpoint:
    hammering a limiter makes the ban longer. A malformed body is a schema error, never data.
    """
    last_error: Exception | None = None
    for url in BASE_URLS:
        for attempt in range(retries + 1):
            try:
                resp = requests.get(url, params=params, timeout=timeout)
                if resp.status_code in (429, 418):
                    logger.warning("Binance endpoint %s rate-limited (%s); not retrying it", url, resp.status_code)
                    last_error = RuntimeError(f"{url}: rate limited ({resp.status_code})")
                    break
                resp.raise_for_status()
                return _check_kline_schema(resp.json())
            except KlineSchemaError as exc:
                logger.warning("Binance endpoint %s returned a malformed body: %s", url, exc)
                last_error = exc
                break  # a wrong shape will not fix itself on retry
            except (requests.RequestException, ValueError) as exc:  # ValueError: body was not JSON
                logger.warning("Binance endpoint %s failed (attempt %d/%d): %s", url, attempt + 1, retries + 1, exc)
                last_error = exc
                if attempt < retries:
                    time.sleep(backoff_s)
    raise RuntimeError(f"all Binance endpoints failed: {last_error}")


def _to_bars(raw: list, cutoff_ms: float) -> list[PriceBar]:
    bars = []
    for entry in raw:
        open_time_ms, o, h, l, c, v, close_time_ms = entry[0:7]
        if close_time_ms > cutoff_ms:
            continue  # still-forming candle -- never use it for indicators
        bars.append(
            PriceBar(
                as_of=datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc),
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(v),
                source="binance",
            )
        )
    return bars


class BinanceProvider(MarketDataProvider):
    name = "binance"

    def get_hourly_bars(self, count: int) -> list[PriceBar]:
        # Ask for one extra in case the most recent candle is still forming this hour.
        params = {"symbol": SYMBOL, "interval": "1h", "limit": count + 1}
        now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000
        return _to_bars(_get_klines(params), now_ms)[-count:]

    def get_hourly_klines_with_extras(self, count: int) -> tuple[list[PriceBar], list[tuple[datetime, float, int, float]]]:
        """
        The most recent `count` fully-closed hourly candles as PriceBars PLUS, from the same
        response, the fields the candles alone do not carry: trade count and taker-buy volume
        (kline fields 8 and 9). One request, one consistent view -- used by the shadow record.
        """
        params = {"symbol": SYMBOL, "interval": "1h", "limit": count + 1}
        now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000
        raw = [k for k in _get_klines(params) if k[6] <= now_ms][-count:]
        bars = _to_bars(raw, now_ms)
        extras = [(datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc), float(k[5]), int(k[8]), float(k[9])) for k in raw]
        return bars, extras

    def get_bar_at(self, as_of: datetime) -> PriceBar | None:
        """The fully-closed hourly candle that opened at `as_of` (UTC), or None if it hasn't closed yet."""
        open_ms = int(as_of.timestamp() * 1000) // HOUR_MS * HOUR_MS
        params = {"symbol": SYMBOL, "interval": "1h", "startTime": open_ms, "limit": 1}
        now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000
        bars = _to_bars(_get_klines(params), now_ms)
        return bars[0] if bars and int(bars[0].as_of.timestamp() * 1000) == open_ms else None

    def get_history(self, end: datetime, hours: int) -> list[PriceBar]:
        """
        Fully-closed hourly candles ending at (and including) the candle that opened at `end`,
        going back `hours` candles. Pages through Binance's 1000-per-request cap. Used for
        backtesting, where we need far more history than a live run does.
        """
        end_open_ms = int(end.timestamp() * 1000) // HOUR_MS * HOUR_MS
        start_ms = end_open_ms - (hours - 1) * HOUR_MS
        now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000

        bars: list[PriceBar] = []
        cursor = start_ms
        while cursor <= end_open_ms:
            params = {
                "symbol": SYMBOL,
                "interval": "1h",
                "startTime": cursor,
                "endTime": end_open_ms + HOUR_MS - 1,
                "limit": MAX_PER_REQUEST,
            }
            page = _to_bars(_get_klines(params, timeout=30), now_ms)
            if not page:
                break
            bars.extend(page)
            cursor = int(page[-1].as_of.timestamp() * 1000) + HOUR_MS
        return bars
