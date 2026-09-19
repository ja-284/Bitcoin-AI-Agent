"""
Backup market data source, used only if Binance is unreachable.

Important limitation: CoinGecko's free-tier endpoints don't give real OHLC candles
with volume in one place. Its `/market_chart` endpoint gives a price at each point in
time, plus a volume figure -- but that volume figure is a rolling ~24h total, not the
volume traded in that specific hour. So bars built from this source are approximations:
- open/high/low are reconstructed from consecutive price points, not real intra-hour swings
- volume is a smoothed 24h figure, not a true per-hour number

Every bar from this source is marked `is_synthetic=True` so the rest of the system
(and anyone reading the logs) can tell the difference and weight it accordingly.
This is why Binance is the primary source and this is only a fallback.
"""

from datetime import datetime, timezone

import requests

from agent.config.settings import COINGECKO_API_KEY
from agent.data_providers.base import MarketDataProvider
from agent.shared.types import PriceBar

BASE_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"


class CoinGeckoProvider(MarketDataProvider):
    name = "coingecko"

    def _headers(self) -> dict:
        return {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}

    def get_hourly_bars(self, count: int) -> list[PriceBar]:
        # days=2+ gives hourly-spaced points on CoinGecko's free tier; days=1 would be ~5-minute spacing.
        days = max(2, (count // 24) + 2)
        params = {"vs_currency": "usd", "days": days}
        resp = requests.get(BASE_URL, params=params, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()

        prices = data["prices"]  # [[ts_ms, price], ...]
        volumes = dict(data["total_volumes"])  # {ts_ms: rolling_24h_volume}

        bars = []
        prev_price = None
        for ts_ms, price in prices:
            if prev_price is not None:
                bars.append(
                    PriceBar(
                        as_of=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                        open=prev_price,
                        high=max(prev_price, price),
                        low=min(prev_price, price),
                        close=price,
                        volume=volumes.get(ts_ms, 0.0),
                        source=self.name,
                        is_synthetic=True,
                    )
                )
            prev_price = price
        return bars[-count:]
