"""
Macro / cross-market data for research (Phase 8.4): daily closes of US stocks, the
dollar index, gold, oil and the 10-year yield, from Yahoo Finance's free chart API.

Point-in-time rule: a daily bar for trading date D becomes visible at D 22:00 UTC --
after the NYSE close (20:00 or 21:00 UTC depending on daylight time) and after CME
daily settlements. That is conservative by one to three hours and never early. On
weekends and holidays the last known close simply stays the latest known value, and
the number of hours since it was known is itself a feature (staleness).

Features per series (name in SERIES): <name>_ret_1d = last known close vs the close
before it; <name>_ret_5d = vs five closes before. For the yield (tnx) the difference
in percentage points is used instead of a ratio. Plus macro_staleness_h.
"""

import csv
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from agent.research.history import DATA_DIR

logger = logging.getLogger(__name__)

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SERIES = {"spx": "^GSPC", "ndq": "^IXIC", "dxy": "DX-Y.NYB", "gold": "GC=F", "oil": "CL=F", "tnx": "^TNX"}
AVAILABLE_AT_UTC_HOUR = 22
MACRO_FEATURES = [f"{n}_{'chg' if n == 'tnx' else 'ret'}_{k}d" for n in SERIES for k in (1, 5)] + ["macro_staleness_h"]


def _fetch_daily(symbol: str) -> pd.Series:
    resp = requests.get(CHART_URL.format(symbol=symbol), params={"range": "max", "interval": "1d"},
                        headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    ts = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    tz = result["meta"]["exchangeTimezoneName"]
    # The bar's trading DATE in the exchange's own timezone (the timestamp is the session start).
    dates = pd.to_datetime(ts, unit="s", utc=True).tz_convert(tz).normalize().tz_localize(None)
    s = pd.Series(closes, index=dates, dtype=float).dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s


def download_macro() -> Path:
    frames = {}
    for name, symbol in SERIES.items():
        frames[name] = _fetch_daily(symbol)
        logger.info("Macro %s (%s): %d daily closes, %s -> %s", name, symbol, len(frames[name]), frames[name].index[0].date(), frames[name].index[-1].date())
        time.sleep(0.5)
    df = pd.DataFrame(frames)
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"macro_{datetime.now(tz=timezone.utc):%Y-%m-%d}.csv"
    df.to_csv(path, index_label="trading_date")
    return path


def _latest() -> Path | None:
    files = sorted(DATA_DIR.glob("macro_*.csv"))
    return files[-1] if files else None


def load_macro(path: Path | None = None) -> pd.DataFrame:
    """Daily closes, index = trading date (naive), one column per series; NaN on days a market was closed."""
    path = path or _latest() or download_macro()
    df = pd.read_csv(path, index_col="trading_date", parse_dates=True, float_precision="round_trip")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("macro history must be strictly increasing by trading date")
    return df


def availability_times(trading_dates: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(trading_dates, tz=None).tz_localize("UTC") + pd.Timedelta(hours=AVAILABLE_AT_UTC_HOUR)


def macro_features(grid: pd.DatetimeIndex, daily: pd.DataFrame) -> pd.DataFrame:
    """Features on the hourly grid: for reference hour t, only bars available at t + 1h."""
    out = pd.DataFrame(index=grid)
    cutoff = (grid + timedelta(hours=1)).to_numpy()
    staleness = None
    for name in SERIES:
        s = daily[name].dropna()
        avail = availability_times(s.index).to_numpy()
        values = s.to_numpy(dtype=float)
        pos = np.searchsorted(avail, cutoff, side="right") - 1  # last bar visible at the cutoff
        ok1, ok5 = pos >= 1, pos >= 5
        p = np.clip(pos, 0, len(values) - 1)
        last = np.where(pos >= 0, values[p], np.nan)
        prev1 = np.where(ok1, values[np.clip(p - 1, 0, None)], np.nan)
        prev5 = np.where(ok5, values[np.clip(p - 5, 0, None)], np.nan)
        if name == "tnx":
            out[f"{name}_chg_1d"] = last - prev1
            out[f"{name}_chg_5d"] = last - prev5
        else:
            out[f"{name}_ret_1d"] = last / prev1 - 1
            out[f"{name}_ret_5d"] = last / prev5 - 1
        if name == "spx":
            known_at = np.where(pos >= 0, avail[p], np.datetime64("NaT", "ns"))
            staleness = (cutoff - known_at) / np.timedelta64(1, "h")
    out["macro_staleness_h"] = staleness
    return out
