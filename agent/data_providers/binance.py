"""
Primary market data source. Binance's public market-data endpoints need no account,
no API key, and return true OHLCV (open/high/low/close/volume) candles directly --
which is exactly the shape this project needs, and is not something CoinGecko's
free tier actually provides (see coingecko.py).
"""

import logging
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


def _get_klines(params: dict, timeout: int = 15) -> list:
    last_error: Exception | None = None
    for url in BASE_URLS:
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.warning("Binance endpoint %s failed: %s", url, exc)
            last_error = exc
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
