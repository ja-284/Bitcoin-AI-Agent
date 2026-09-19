"""
Pure deterministic math over price history. No AI, no opinions -- just standard,
well-known technical indicators, computed the same way every time.

Every indicator here has a "warm-up" requirement: e.g. a 200-hour moving average
means nothing with only 40 hours of history. Rather than silently compute a
misleading number, each indicator is left as None until there's enough history,
and that gap is recorded in `insufficient_history` so the scoring step (and the
confidence calculation) can see it and react honestly, instead of pretending
every run has full information.
"""

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import pandas_ta_classic as ta

from agent.shared.types import PriceBar

# The feature window: how many closed hourly candles every calculation sees. Live runs
# fetch exactly this many; the backtest replays with exactly this many per simulated
# hour, so the two produce identical values (RSI/MACD smoothing depends on how much
# history is fed in -- a growing window would silently diverge from live behaviour).
HISTORY_HOURS = 250  # longest warm-up is the 200h SMA, plus margin

SMA_SHORT = 50
SMA_LONG = 200
RSI_LENGTH = 14
VOLUME_AVG_LENGTH = 20


@dataclass
class IndicatorSet:
    close: float
    sma_short: Optional[float]
    sma_long: Optional[float]
    rsi: Optional[float]
    macd: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]
    bb_upper: Optional[float]
    bb_lower: Optional[float]
    volume: float
    volume_avg: Optional[float]
    insufficient_history: list[str] = field(default_factory=list)


def _bars_to_frame(bars: list[PriceBar]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"close": b.close, "high": b.high, "low": b.low, "volume": b.volume} for b in bars]
    )


def compute_indicators(bars: list[PriceBar]) -> IndicatorSet:
    if not bars:
        raise ValueError("compute_indicators requires at least one price bar")

    df = _bars_to_frame(bars)
    n = len(df)
    missing: list[str] = []

    def latest(series: Optional[pd.Series]) -> Optional[float]:
        if series is None or series.empty or pd.isna(series.iloc[-1]):
            return None
        return float(series.iloc[-1])

    sma_short = latest(ta.sma(df["close"], length=SMA_SHORT)) if n >= SMA_SHORT else None
    if sma_short is None:
        missing.append(f"sma_{SMA_SHORT} needs {SMA_SHORT}h of history, have {n}h")

    sma_long = latest(ta.sma(df["close"], length=SMA_LONG)) if n >= SMA_LONG else None
    if sma_long is None:
        missing.append(f"sma_{SMA_LONG} needs {SMA_LONG}h of history, have {n}h")

    rsi = latest(ta.rsi(df["close"], length=RSI_LENGTH)) if n >= RSI_LENGTH + 1 else None
    if rsi is None:
        missing.append(f"rsi_{RSI_LENGTH} needs {RSI_LENGTH + 1}h of history, have {n}h")

    macd_val = macd_signal = macd_hist = None
    if n >= 35:  # MACD(12,26,9) needs ~26 + 9 periods to fully settle
        macd_df = ta.macd(df["close"])
        if macd_df is not None:
            macd_val = latest(macd_df.iloc[:, 0])
            macd_hist = latest(macd_df.iloc[:, 1])
            macd_signal = latest(macd_df.iloc[:, 2])
    if macd_val is None:
        missing.append("macd needs ~35h of history, have %dh" % n)

    bb_upper = bb_lower = None
    if n >= 20:
        bb_df = ta.bbands(df["close"], length=20)
        if bb_df is not None:
            bb_lower = latest(bb_df.iloc[:, 0])
            bb_upper = latest(bb_df.iloc[:, 2])
    if bb_upper is None:
        missing.append("bollinger_bands needs 20h of history, have %dh" % n)

    volume_avg = latest(ta.sma(df["volume"], length=VOLUME_AVG_LENGTH)) if n >= VOLUME_AVG_LENGTH else None
    if volume_avg is None:
        missing.append(f"volume_avg_{VOLUME_AVG_LENGTH} needs {VOLUME_AVG_LENGTH}h of history, have {n}h")

    return IndicatorSet(
        close=float(df["close"].iloc[-1]),
        sma_short=sma_short,
        sma_long=sma_long,
        rsi=rsi,
        macd=macd_val,
        macd_signal=macd_signal,
        macd_histogram=macd_hist,
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        volume=float(df["volume"].iloc[-1]),
        volume_avg=volume_avg,
        insufficient_history=missing,
    )
