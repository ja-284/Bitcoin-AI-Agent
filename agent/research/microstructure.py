"""
Microstructure proxies for research (Phase 8.7), from fields the spot candles already
carry but the live PriceBar drops: taker-buy base volume (aggressive buying) and the
number of trades per hour. Downloaded once into a snapshot under data/ (same endpoint
and pagination as the price history), validated, then turned into trailing-window
features on the complete hourly grid. Point-in-time is inherited from the candle: the
candle with as_of = t is complete at the cutoff t + 1h.

Order-book depth and spread history are not available free and are not fabricated.
"""

import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from agent.data_providers.binance import BASE_URLS, HOUR_MS, MAX_PER_REQUEST, SYMBOL
from agent.research.history import DATA_DIR
from agent.research.periods import DATA_START

logger = logging.getLogger(__name__)

MICROSTRUCTURE_FEATURES = ["taker_buy_share_1h", "taker_buy_share_6h", "taker_buy_share_24h", "trades_rel_24h", "trades_rel_168h"]


def download_klines_extra(end: datetime | None = None) -> Path:
    """Hourly candles with taker-buy volume and trade count, closed candles only."""
    end = end or datetime.now(tz=timezone.utc)
    end_ms = int(end.timestamp() * 1000)
    cursor = int(DATA_START.timestamp() * 1000)
    rows = []
    while cursor < end_ms:
        page = None
        for url in BASE_URLS:
            try:
                resp = requests.get(url, params={"symbol": SYMBOL, "interval": "1h", "startTime": cursor, "limit": MAX_PER_REQUEST}, timeout=30)
                resp.raise_for_status()
                page = resp.json()
                break
            except requests.RequestException as exc:
                logger.warning("%s failed: %s", url, exc)
        if not page:
            break
        for k in page:
            if int(k[6]) <= end_ms:
                rows.append((int(k[0]), float(k[5]), int(k[8]), float(k[9])))  # open time, volume, trades, taker buy base volume
        cursor = int(page[-1][0]) + HOUR_MS
        time.sleep(0.05)
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"klines_extra_{SYMBOL.lower()}_1h_{datetime.now(tz=timezone.utc):%Y-%m-%d}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["as_of", "volume", "trades", "taker_buy_volume"])
        for ts, vol, n, tb in rows:
            w.writerow([datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(), vol, n, tb])
    logger.info("Klines extra: %d candles written to %s", len(rows), path)
    return path


def _latest() -> Path | None:
    files = sorted(DATA_DIR.glob(f"klines_extra_{SYMBOL.lower()}_1h_*.csv"))
    return files[-1] if files else None


def load_klines_extra(path: Path | None = None) -> pd.DataFrame:
    path = path or _latest() or download_klines_extra()
    df = pd.read_csv(path, float_precision="round_trip")
    df.index = pd.to_datetime(df["as_of"], utc=True, format="ISO8601")
    df = df.drop(columns=["as_of"])
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("klines history must be strictly increasing in time")
    if (df["taker_buy_volume"] > df["volume"] * 1.000001).any() or (df[["volume", "trades", "taker_buy_volume"]] < 0).any().any():
        raise ValueError("impossible values: taker-buy volume above total volume, or negatives")
    return df


def microstructure_features(grid: pd.DatetimeIndex, extra: pd.DataFrame) -> pd.DataFrame:
    """Trailing-window features on the complete hourly grid (gaps blank the window)."""
    e = extra.reindex(grid)
    out = pd.DataFrame(index=grid)
    for w in (1, 6, 24):
        buy = e["taker_buy_volume"].rolling(w, min_periods=w).sum()
        total = e["volume"].rolling(w, min_periods=w).sum()
        with np.errstate(invalid="ignore", divide="ignore"):
            out[f"taker_buy_share_{w}h"] = np.where(total > 0, buy / total, np.nan)
    trades = e["trades"].astype(float)
    for w in (24, 168):
        prior_mean = trades.shift(1).rolling(w, min_periods=w).mean()  # the hour itself is excluded from its own baseline
        with np.errstate(invalid="ignore", divide="ignore"):
            out[f"trades_rel_{w}h"] = np.where(prior_mean > 0, trades / prior_mean, np.nan)
    return out
