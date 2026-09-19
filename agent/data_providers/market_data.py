"""
The single door the rest of the system knocks on for price data. It tries the
primary provider first and automatically falls back to the backup if that fails --
missing price data would block the entire hourly run, so this is the one place
worth having a safety net from day one.

Every provider's output is validated before it is accepted: impossible data (see
quality.py) counts as a provider failure and triggers the fallback, and gaps are
returned alongside the bars so the caller can record them.
"""

import logging
from dataclasses import dataclass

from agent.data_providers.binance import BinanceProvider
from agent.data_providers.coingecko import CoinGeckoProvider
from agent.data_providers.quality import BarQualityReport, BarValidationError, validate_bars
from agent.shared.types import PriceBar

logger = logging.getLogger(__name__)

_PROVIDERS = [BinanceProvider(), CoinGeckoProvider()]


@dataclass
class MarketData:
    bars: list[PriceBar]
    quality: BarQualityReport
    provider: str


def get_market_data(count: int) -> MarketData:
    errors = []
    for provider in _PROVIDERS:
        try:
            bars = provider.get_hourly_bars(count)
            if not bars:
                raise BarValidationError("provider returned no bars")
            report = validate_bars(bars)
            if report.gaps:
                logger.warning("%s: %d gap(s), %d missing hour(s) inside the window", provider.name, len(report.gaps), report.missing_hours)
            return MarketData(bars=bars, quality=report, provider=provider.name)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: any provider failure should trigger fallback
            logger.warning("Market data provider %s failed: %s", provider.name, exc)
            errors.append(f"{provider.name}: {exc}")
    raise RuntimeError(f"All market data providers failed: {'; '.join(errors)}")


def get_hourly_bars(count: int) -> list[PriceBar]:
    return get_market_data(count).bars
