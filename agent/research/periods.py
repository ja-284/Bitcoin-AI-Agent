"""
The time split, as code. Mirrors research/EXPERIMENTS.md -- if the two ever disagree,
that is a bug to fix immediately, not a detail.

Why a sealed holdout: every time a period is looked at while making decisions, it stops
being a fair test of those decisions. The final holdout is evaluated once, at the end.
The loader in history.py refuses to return holdout candles unless explicitly allowed,
and every allowed access is written to research/HOLDOUT_ACCESS.log.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Period:
    name: str
    start: datetime  # inclusive, candle open time
    end: datetime  # exclusive

    def contains(self, as_of: datetime) -> bool:
        return self.start <= as_of < self.end


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


DATA_START = _utc(2017, 8, 17, 4)  # first Binance BTCUSDT hourly candle

EXPLORATION = Period("exploration", DATA_START, _utc(2024, 1, 1))
VALIDATION = Period("validation", _utc(2024, 1, 1), _utc(2025, 7, 1))
HOLDOUT = Period("holdout", _utc(2025, 7, 1), _utc(2026, 8, 20))  # SEALED
BUFFER = Period("buffer", _utc(2026, 8, 20), _utc(2026, 9, 19, 9))  # seen once during build; not for confirmatory use
LIVE = Period("live", _utc(2026, 9, 19, 9), _utc(2100, 1, 1))

DEVELOPMENT_PERIODS = [EXPLORATION, VALIDATION]
ALL_PERIODS = [EXPLORATION, VALIDATION, HOLDOUT, BUFFER, LIVE]


def period_of(as_of: datetime) -> str:
    for p in ALL_PERIODS:
        if p.contains(as_of):
            return p.name
    return "before_data"
