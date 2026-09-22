"""
Derivatives data for research (Phase 8.3): Binance USDT-M perpetual funding rates and
the hourly premium index. Downloaded once into date-stamped CSV snapshots under data/,
validated, and turned into point-in-time features on the same hourly grid as the
price features.

Point-in-time rules (the part that matters):
- A funding rate settles at `fundingTime` (00:00 / 08:00 / 16:00 UTC). For reference
  hour t (cutoff t + 1h) only settlements with fundingTime <= t + 1h are visible. The
  exchange's live "predicted next rate" is never used: it cannot be reconstructed.
- A premium-index candle that opened at o is visible from o + 1h. Aligned like spot
  candles: the candle with as_of = t is available at the cutoff.

Open-interest history (30 days only) and liquidations (no free history) are
UNAVAILABLE and deliberately absent.
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

FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndexKlines"
SYMBOL = "BTCUSDT"
FUNDING_START_MS = 1_567_296_000_000  # 2019-09-01
PREMIUM_START_MS = 1_576_800_000_000  # 2019-12-20
HOUR_MS = 3_600_000
DERIVATIVES_FEATURES = ["funding_last", "funding_mean_3", "funding_sum_21", "premium_close", "premium_mean_24", "premium_mean_168"]


def _get(url: str, params: dict) -> list:
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def download_funding(end_ms: int | None = None) -> Path:
    end_ms = end_ms or int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    rows, cursor = [], FUNDING_START_MS
    while cursor < end_ms:
        page = _get(FUNDING_URL, {"symbol": SYMBOL, "startTime": cursor, "endTime": end_ms, "limit": 1000})
        if not page:
            break
        rows.extend((int(r["fundingTime"]), float(r["fundingRate"])) for r in page)
        cursor = int(page[-1]["fundingTime"]) + 1
        time.sleep(0.1)
    path = DATA_DIR / f"funding_{SYMBOL.lower()}_{datetime.now(tz=timezone.utc):%Y-%m-%d}.csv"
    DATA_DIR.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["funding_time", "funding_rate"])
        for ts, rate in rows:
            w.writerow([datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(), rate])
    logger.info("Funding: %d settlements written to %s", len(rows), path)
    return path


def download_premium(end_ms: int | None = None) -> Path:
    end_ms = end_ms or int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    rows, cursor = [], PREMIUM_START_MS
    while cursor < end_ms:
        page = _get(PREMIUM_URL, {"symbol": SYMBOL, "interval": "1h", "startTime": cursor, "endTime": end_ms, "limit": 1500})
        if not page:
            break
        for k in page:
            if int(k[6]) <= end_ms:  # closed candles only
                rows.append((int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4])))
        cursor = int(page[-1][0]) + HOUR_MS
        time.sleep(0.1)
    path = DATA_DIR / f"premium_{SYMBOL.lower()}_1h_{datetime.now(tz=timezone.utc):%Y-%m-%d}.csv"
    DATA_DIR.mkdir(exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["as_of", "open", "high", "low", "close"])
        for ts, o, h, l, c in rows:
            w.writerow([datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(), o, h, l, c])
    logger.info("Premium index: %d hourly candles written to %s", len(rows), path)
    return path


def _latest(prefix: str) -> Path | None:
    files = sorted(DATA_DIR.glob(f"{prefix}_*.csv"))
    return files[-1] if files else None


def load_funding(path: Path | None = None) -> pd.Series:
    """Settled funding rates indexed by settlement time (UTC). Validated: increasing, finite, ~8h spacing."""
    path = path or _latest(f"funding_{SYMBOL.lower()}") or download_funding()
    df = pd.read_csv(path, float_precision="round_trip")
    s = pd.Series(df["funding_rate"].to_numpy(dtype=float), index=pd.to_datetime(df["funding_time"], utc=True, format="ISO8601"), name="funding_rate")
    if not s.index.is_monotonic_increasing or s.index.has_duplicates:
        raise ValueError("funding history must be strictly increasing in time")
    if not np.isfinite(s.to_numpy()).all():
        raise ValueError("funding history contains non-finite values")
    spacing = s.index.to_series().diff().dropna().dt.total_seconds() / 3600
    irregular = int(((spacing - 8).abs() > 0.01).sum())
    if irregular:
        logger.warning("Funding: %d settlement gaps not equal to 8h (exchange irregularities); left as-is", irregular)
    return s


def load_premium(path: Path | None = None) -> pd.DataFrame:
    path = path or _latest(f"premium_{SYMBOL.lower()}_1h") or download_premium()
    df = pd.read_csv(path, float_precision="round_trip")
    df.index = pd.to_datetime(df["as_of"], utc=True, format="ISO8601")
    df = df.drop(columns=["as_of"])
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("premium history must be strictly increasing in time")
    if not np.isfinite(df.to_numpy()).all():
        raise ValueError("premium history contains non-finite values")
    return df


def derivatives_features(grid: pd.DatetimeIndex, funding: pd.Series, premium: pd.DataFrame) -> pd.DataFrame:
    """
    Features on the hourly grid (index = reference hour t; visible information = up to t + 1h).

    funding_last     most recent settlement with fundingTime <= t + 1h
    funding_mean_3   mean of the last 3 settlements (24h) visible at the cutoff
    funding_sum_21   sum of the last 21 settlements (7 days) visible at the cutoff
    premium_close    premium-index candle with as_of = t (closed at the cutoff)
    premium_mean_24  mean of the last 24 premium closes (as_of <= t)
    premium_mean_168 mean of the last 168 premium closes
    """
    out = pd.DataFrame(index=grid)
    cutoff = grid + timedelta(hours=1)

    # Funding: for each cutoff, the position of the last settlement at or before it.
    f_times = funding.index.to_numpy()
    f_vals = funding.to_numpy(dtype=float)
    pos = np.searchsorted(f_times, cutoff.to_numpy(), side="right") - 1  # index of last settlement <= cutoff
    valid = pos >= 0
    last = np.where(valid, f_vals[np.clip(pos, 0, len(f_vals) - 1)], np.nan)
    out["funding_last"] = last
    csum = np.concatenate([[0.0], np.cumsum(f_vals)])
    for name, k in (("funding_mean_3", 3), ("funding_sum_21", 21)):
        if len(f_vals) < k:
            out[name] = np.nan  # not enough settlements exist at all
            continue
        ok = pos >= k - 1  # at least k settlements visible at this cutoff
        p = np.where(ok, pos, k - 1)  # placeholder index where not ok; masked out below
        window_sum = csum[p + 1] - csum[p + 1 - k]
        out[name] = np.where(ok, window_sum / k if name.startswith("funding_mean") else window_sum, np.nan)

    prem = premium["close"].reindex(grid)  # candle with as_of = t; NaN where missing
    out["premium_close"] = prem.to_numpy()
    out["premium_mean_24"] = prem.rolling(24, min_periods=24).mean().to_numpy()
    out["premium_mean_168"] = prem.rolling(168, min_periods=168).mean().to_numpy()
    return out
