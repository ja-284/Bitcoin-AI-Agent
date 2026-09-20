"""
Candidate features for the research programme, computed causally over a full candle
series: every value at hour t is a function of candles with as_of <= t only (trailing
windows, min_periods = window, so a value exists only once the whole window is real).
tests/test_features_point_in_time.py garbles the future and checks the past is unchanged.

Why compute over the full series instead of the live 250-bar window: several of these
need up to 4,800 hours of history. If one is ever adopted by the live system, the live
window is widened to match and the replay = live equivalence test is re-run -- until
then these are research quantities, clearly separated from the live pipeline.

Groups:
  volatility  rv_24 / rv_168 / rv_720  std of hourly log returns over the trailing window
              vol_ratio_24_168          short vs medium volatility (expansion > 1, contraction < 1)
              tr_mean_14_rel            mean true range over 14h, relative to close
              bb_width_20               Bollinger band width (2 sigma) relative to the middle band
              parkinson_24              high/low-based volatility estimator over 24h
              vol_pct_720               percentile rank of rv_24 within its own trailing 720h
  regime      trail_ret_168h / _720h / _2160h   trailing 7-day / 30-day / 90-day return
              dist_sma_1200 / dist_sma_4800     close vs 50-day / 200-day hourly-candle average
  calendar    hour_sin / hour_cos       hour of day (UTC) on a circle, so 23:00 sits next to 00:00
              is_weekend                Saturday/Sunday flag (UTC) -- known only from the clock,
                                        so trivially point-in-time safe; a move-SIZE input (E007/E008)

Naming rule: feature names never start with "ret_" or "fwd_" -- those prefixes belong to
the forward-return (target) columns in the test harness. A name collision once let the
target overwrite a feature and produced a perfect "correlation" with the future (E004,
first run). The harness now refuses such names.
"""

import numpy as np
import pandas as pd

from agent.shared.types import PriceBar

VOLATILITY_FEATURES = ["rv_24", "rv_168", "rv_720", "vol_ratio_24_168", "tr_mean_14_rel", "bb_width_20", "parkinson_24", "vol_pct_720"]
REGIME_FEATURES = ["trail_ret_168h", "trail_ret_720h", "trail_ret_2160h", "dist_sma_1200", "dist_sma_4800"]
CALENDAR_FEATURES = ["hour_sin", "hour_cos", "is_weekend"]
RESERVED_PREFIXES = ("ret_", "fwd_")  # target columns in the harness; never use for features


def bars_to_frame(bars: list[PriceBar]) -> pd.DataFrame:
    """
    Candles on a complete hourly grid. Missing hours (exchange downtime) become blank
    rows, so a shift of N rows is exactly N hours and any trailing window that touches
    a gap yields NaN (min_periods = window) instead of a value computed over the wrong
    span. Gaps are never filled.
    """
    df = pd.DataFrame(
        {"open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars
    )
    df.index = pd.DatetimeIndex([b.as_of for b in bars], name="as_of")
    full = pd.date_range(df.index[0], df.index[-1], freq="h", name="as_of")
    return df.reindex(full)


def _rolling_rank_pct(series: pd.Series, window: int) -> pd.Series:
    """Percentile rank (0-1) of the latest value within the trailing window, computed per hour."""
    return series.rolling(window, min_periods=window).apply(lambda w: (w[:-1] < w[-1]).mean(), raw=True)


def volatility_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    log_ret = np.log(df["close"]).diff()
    for w in (24, 168, 720):
        out[f"rv_{w}"] = log_ret.rolling(w, min_periods=w).std()
    out["vol_ratio_24_168"] = out["rv_24"] / out["rv_168"]

    prev_close = df["close"].shift(1)
    true_range = pd.concat([df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1).max(axis=1)
    out["tr_mean_14_rel"] = true_range.rolling(14, min_periods=14).mean() / df["close"]

    mid = df["close"].rolling(20, min_periods=20).mean()
    sd = df["close"].rolling(20, min_periods=20).std()
    out["bb_width_20"] = (4 * sd) / mid

    hl = np.log(df["high"] / df["low"]) ** 2
    out["parkinson_24"] = np.sqrt(hl.rolling(24, min_periods=24).mean() / (4 * np.log(2)))

    out["vol_pct_720"] = _rolling_rank_pct(out["rv_24"], 720)
    return out


def regime_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for w in (168, 720, 2160):
        out[f"trail_ret_{w}h"] = df["close"] / df["close"].shift(w) - 1
    for w in (1200, 4800):
        out[f"dist_sma_{w}"] = df["close"] / df["close"].rolling(w, min_periods=w).mean() - 1
    return out


def calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    hour = df.index.hour.to_numpy(dtype=float)
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["is_weekend"] = (df.index.dayofweek >= 5).astype(float)
    # The clock is always known, but an hour with no candle is not a usable reference hour:
    # keep the invariant "no candle -> no feature row" so gaps stay visibly blank everywhere.
    return out.where(df["close"].notna())


def all_features(bars: list[PriceBar]) -> pd.DataFrame:
    df = bars_to_frame(bars)
    return pd.concat([volatility_features(df), regime_features(df), calendar_features(df)], axis=1)
