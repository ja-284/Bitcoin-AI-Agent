"""
Data-quality validation for hourly candles. Two kinds of problem, two responses:

- Impossible data (duplicates, out-of-order, NaN, negative prices, high < low, a candle
  that hasn't closed yet, timestamps not on the hour): raise. Better a loud failure than
  a quietly wrong prediction.
- Gaps (missing hours): flag them in the report, never fill them. Fabricating a missing
  observation is exactly the kind of silent data invention this project forbids; the
  consumers decide what a gap means for them (the backtest marks affected outcomes
  unavailable, the live run records it in run_meta).
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from agent.shared.types import PriceBar

HOUR = timedelta(hours=1)


class BarValidationError(ValueError):
    pass


@dataclass
class BarQualityReport:
    count: int
    first: datetime
    last: datetime
    gaps: list[tuple[datetime, int]] = field(default_factory=list)  # (last bar before the gap, hours missing)

    @property
    def missing_hours(self) -> int:
        return sum(missing for _, missing in self.gaps)

    @property
    def span_hours(self) -> int:
        return int((self.last - self.first) / HOUR) + 1

    def summary(self) -> dict:
        return {
            "bars": self.count,
            "first": self.first.isoformat(),
            "last": self.last.isoformat(),
            "gaps": len(self.gaps),
            "missing_hours": self.missing_hours,
        }


def _check_bar(i: int, bar: PriceBar) -> None:
    ts = bar.as_of
    if ts.tzinfo is None or ts.utcoffset() != timedelta(0):
        raise BarValidationError(f"bar {i}: timestamp must be timezone-aware UTC, got {ts!r}")
    if ts.minute or ts.second or ts.microsecond:
        raise BarValidationError(f"bar {i}: timestamp not aligned to the hour: {ts.isoformat()}")
    values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
    if any(v is None or not math.isfinite(v) for v in values):
        raise BarValidationError(f"bar {i} ({ts.isoformat()}): non-finite value in {values}")
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        raise BarValidationError(f"bar {i} ({ts.isoformat()}): non-positive price in {values[:4]}")
    if bar.volume < 0:
        raise BarValidationError(f"bar {i} ({ts.isoformat()}): negative volume {bar.volume}")
    if not (bar.low <= min(bar.open, bar.close) and max(bar.open, bar.close) <= bar.high):
        raise BarValidationError(f"bar {i} ({ts.isoformat()}): OHLC inconsistent: {values[:4]}")


def validate_bars(bars: list[PriceBar], now: datetime | None = None) -> BarQualityReport:
    """Raises BarValidationError on impossible data; returns a report that flags gaps."""
    if not bars:
        raise BarValidationError("no bars")
    now = now or datetime.now(tz=timezone.utc)

    gaps: list[tuple[datetime, int]] = []
    previous: PriceBar | None = None
    for i, bar in enumerate(bars):
        _check_bar(i, bar)
        if bar.as_of + HOUR > now:
            raise BarValidationError(f"bar {i} ({bar.as_of.isoformat()}) has not closed yet at {now.isoformat()}")
        if previous is not None:
            step = bar.as_of - previous.as_of
            if step <= timedelta(0):
                kind = "duplicate" if step == timedelta(0) else "out-of-order"
                raise BarValidationError(f"bar {i}: {kind} timestamp {bar.as_of.isoformat()} after {previous.as_of.isoformat()}")
            if step > HOUR:
                gaps.append((previous.as_of, int(step / HOUR) - 1))
        previous = bar

    return BarQualityReport(count=len(bars), first=bars[0].as_of, last=bars[-1].as_of, gaps=gaps)
