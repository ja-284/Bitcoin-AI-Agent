"""
Primary market data source. Binance's public market-data endpoints need no account,
no API key, and return true OHLCV (open/high/low/close/volume) candles directly --
which is exactly the shape this project needs, and is not something CoinGecko's
free tier actually provides (see coingecko.py).
"""

from datetime import datetime, timezone

import requests

from agent.data_providers.base import MarketDataProvider
from agent.shared.types import PriceBar

BASE_URL = "https://api.binance.com/api/v3/klines"
SYMBOL = "BTCUSDT"


class BinanceProvider(MarketDataProvider):
    name = "binance"

    def get_hourly_bars(self, count: int) -> list[PriceBar]:
        # Ask for one extra in case the most recent candle is still forming this hour.
        params = {"symbol": SYMBOL, "interval": "1h", "limit": count + 1}
        resp = requests.get(BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        raw = resp.json()

        now_ms = datetime.now(tz=timezone.utc).timestamp() * 1000
        bars = []
        for entry in raw:
            open_time_ms, o, h, l, c, v, close_time_ms = entry[0:7]
            if close_time_ms > now_ms:
                continue  # still-forming candle -- never use it for indicators
            bars.append(
                PriceBar(
                    as_of=datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(v),
                    source=self.name,
                )
            )
        return bars[-count:]
