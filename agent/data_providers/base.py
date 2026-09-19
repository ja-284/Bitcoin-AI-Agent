"""
The interface every market data provider must follow. As long as a provider returns
PriceBars in this shape, it can be swapped in without changing anything downstream.
"""

from abc import ABC, abstractmethod

from agent.shared.types import PriceBar


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def get_hourly_bars(self, count: int) -> list[PriceBar]:
        """
        Return the most recent `count` fully-closed hourly bars, oldest first.
        Must never include the current, still-forming hour (its high/low/close
        would keep changing until the hour actually ends).
        """
