"""
Candidate feature group "shape": candle geometry, position within the recent range, trade size
and liquidity. Free, already-collected data (spot candles + the trades/taker-buy fields), so
nothing here is new *data* -- it is information the 47 features tested in E003-E008 did not
extract. Each one carries a reason to exist, because a feature without a reason is a lottery
ticket:

  body_ratio_1h     |close-open| / (high-low). How much of the hour's range the market actually
                    committed to. A wide range with a tiny body is indecision, not direction.
  wick_asym_1h      (upper wick - lower wick) / (high-low). Which side got rejected: sellers
                    defending a high leave a long upper wick, buyers defending a low the reverse.
  close_loc_24      where the close sits inside the last 24h high-low range (0 = at the low).
  donchian_pos_168  the same over a week: breakout literature's oldest idea, and the natural
                    counterpart to the distance-to-average features that E004 found useless.
  trade_size_rel_24 mean trade size (volume/trades) against its own trailing 24h mean. E008
                    tested how MANY trades and how many were buys, never how BIG they were --
                    the classic proxy for informed rather than retail flow.
  amihud_rel_168    Amihud illiquidity |return|/volume over 24h against its 168h mean: how much
                    price a unit of volume moves. High illiquidity is where moves overshoot.
  autocorr_lag1_168 lag-1 autocorrelation of hourly returns over the past week. E002-E008 kept
                    finding a weak REVERSAL at 1-6h; this measures directly, at each hour,
                    whether the market is currently in a reverting or a trending state.
  up_streak_6       signed run length of same-direction closes, capped at +/-6.

Point-in-time by construction: every value at hour t uses candles with as_of <= t only, all
rolling windows use min_periods = window, and a rolling baseline excludes the hour itself where
the hour would otherwise be compared with a mean containing it. Gaps blank the window rather
than being bridged (tests/test_features_point_in_time.py garbles the future and checks the past).
"""

import numpy as np
import pandas as pd

SHAPE_FEATURES = [
    "body_ratio_1h",
    "wick_asym_1h",
    "close_loc_24",
    "donchian_pos_168",
    "trade_size_rel_24",
    "amihud_rel_168",
    "autocorr_lag1_168",  # not "ret_..." -- that prefix is reserved for target columns (E004's lesson)
    "up_streak_6",
]


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    with np.errstate(invalid="ignore", divide="ignore"):
        return pd.Series(np.where(b > 0, a / b, np.nan), index=a.index)


def shape_features(df: pd.DataFrame, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """`df`: the complete hourly candle grid (bars_to_frame). `extra`: volume/trades/taker columns."""
    out = pd.DataFrame(index=df.index)
    rng = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()
    upper = df["high"] - df[["open", "close"]].max(axis=1)
    lower = df[["open", "close"]].min(axis=1) - df["low"]
    out["body_ratio_1h"] = _safe_div(body, rng)
    out["wick_asym_1h"] = _safe_div(upper - lower, rng)

    for w, name in ((24, "close_loc_24"), (168, "donchian_pos_168")):
        hi = df["high"].rolling(w, min_periods=w).max()
        lo = df["low"].rolling(w, min_periods=w).min()
        out[name] = _safe_div(df["close"] - lo, hi - lo)

    log_ret = np.log(df["close"]).diff()
    if extra is not None:
        e = extra.reindex(df.index)
        trade_size = _safe_div(e["volume"], e["trades"].astype(float))
        # the hour is compared with a baseline that excludes it, so the ratio cannot be diluted by itself
        out["trade_size_rel_24"] = _safe_div(trade_size, trade_size.shift(1).rolling(24, min_periods=24).mean())
        amihud = _safe_div(log_ret.abs(), e["volume"])
    else:
        out["trade_size_rel_24"] = np.nan
        amihud = _safe_div(log_ret.abs(), df["volume"])
    out["amihud_rel_168"] = _safe_div(
        amihud.rolling(24, min_periods=24).mean(), amihud.shift(1).rolling(168, min_periods=168).mean()
    )

    out["autocorr_lag1_168"] = log_ret.rolling(168, min_periods=168).apply(
        lambda x: np.corrcoef(x[:-1], x[1:])[0, 1] if np.all(np.isfinite(x)) and np.std(x[:-1]) > 0 and np.std(x[1:]) > 0 else np.nan,
        raw=True,
    )

    direction = np.sign(df["close"] - df["open"])
    streak, run = [], 0.0
    for d in direction.to_numpy():
        if not np.isfinite(d) or d == 0:
            run = 0.0
            streak.append(np.nan if not np.isfinite(d) else 0.0)
            continue
        run = d if (run == 0 or np.sign(run) != d) else run + d
        streak.append(float(np.clip(run, -6, 6)))
    out["up_streak_6"] = pd.Series(streak, index=df.index)
    # a gap makes the run length unknowable: blank it wherever the candle itself is missing
    return out.where(df["close"].notna())
