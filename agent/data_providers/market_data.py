"""
The single door the rest of the system knocks on for price data. It tries the
primary provider first and automatically falls back to the backup if that fails --
missing price data would block the entire hourly run, so this is the one place
worth having a safety net from day one.
"""

import logging

from agent.data_providers.binance import BinanceProvider
from agent.data_providers.coingecko import CoinGeckoProvider
from agent.shared.types import PriceBar

logger = logging.getLogger(__name__)

_PROVIDERS = [BinanceProvider(), CoinGeckoProvider()]


def get_hourly_bars(count: int) -> list[PriceBar]:
    errors = []
    for provider in _PROVIDERS:
        try:
            bars = provider.get_hourly_bars(count)
            if bars:
                return bars
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: any provider failure should trigger fallback
            logger.warning("Market data provider %s failed: %s", provider.name, exc)
            errors.append(f"{provider.name}: {exc}")
    raise RuntimeError(f"All market data providers failed: {'; '.join(errors)}")
