"""
On-chain data for research (Phase 8.5): daily network statistics from blockchain.info's
free charts API (values derived from immutable block data) and difficulty adjustments
with exact block timestamps from mempool.space.

Point-in-time rules:
- A daily value stamped D 00:00 UTC covers day D. It is complete at D+1 00:00 UTC and is
  treated as known from D+1 06:00 UTC (a publication margin). The last known value
  persists until the next one is known; hours since it was known are recorded.
- A difficulty adjustment is known from the timestamp of the block that triggered it.

Excluded on purpose: estimated-transaction-volume-usd (a methodology-based estimate that
the provider re-computes over time -> UNSAFE for point-in-time work), mempool-size
(minute-level series with ambiguous long-range sampling), and every paid metric.
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

CHART_URL = "https://api.blockchain.info/charts/{name}"
DIFFICULTY_URL = "https://mempool.space/api/v1/mining/difficulty-adjustments"
SERIES = {"hashrate": "hash-rate", "txcount": "n-transactions", "addr": "n-unique-addresses", "fees": "transaction-fees-usd"}
KNOWN_AFTER = timedelta(hours=30)  # day D (00:00) -> known at D+1 06:00 UTC
ONCHAIN_FEATURES = [f"{n}_chg_{k}d" for n in SERIES for k in (7, 30)] + ["difficulty_adj_last_pct", "onchain_staleness_h"]
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_chart(name: str) -> pd.Series:
    resp = requests.get(CHART_URL.format(name=name), params={"timespan": "all", "format": "json", "sampled": "false"}, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    values = resp.json()["values"]
    idx = pd.to_datetime([v["x"] for v in values], unit="s", utc=True)
    s = pd.Series([float(v["y"]) for v in values], index=idx).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if (s.index.hour != 0).any() or (s.index.minute != 0).any():
        raise ValueError(f"{name}: expected daily points stamped at 00:00 UTC")
    return s


def download_onchain() -> Path:
    frames = {}
    for key, name in SERIES.items():
        frames[key] = _fetch_chart(name)
        logger.info("On-chain %s (%s): %d daily points, %s -> %s", key, name, len(frames[key]), frames[key].index[0].date(), frames[key].index[-1].date())
        time.sleep(0.7)
    df = pd.DataFrame(frames)
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"onchain_{datetime.now(tz=timezone.utc):%Y-%m-%d}.csv"
    df.to_csv(path, index_label="day")
    return path


def download_difficulty() -> Path:
    resp = requests.get(DIFFICULTY_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    rows = sorted((int(r[0]), int(r[1]), float(r[2]), float(r[3])) for r in resp.json())  # time, height, difficulty, change factor
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"difficulty_adjustments_{datetime.now(tz=timezone.utc):%Y-%m-%d}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["adjusted_at", "height", "difficulty", "change_factor"])
        for ts, h, d, c in rows:
            w.writerow([datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), h, d, c])
    logger.info("Difficulty: %d adjustments written to %s", len(rows), path)
    return path


def _latest(prefix: str) -> Path | None:
    files = sorted(DATA_DIR.glob(f"{prefix}_*.csv"))
    return files[-1] if files else None


def load_onchain(path: Path | None = None) -> pd.DataFrame:
    path = path or _latest("onchain") or download_onchain()
    df = pd.read_csv(path, index_col="day", parse_dates=True, float_precision="round_trip")
    df.index = pd.DatetimeIndex(df.index, tz="UTC") if df.index.tz is None else df.index.tz_convert("UTC")
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("on-chain history must be strictly increasing by day")
    return df


def load_difficulty(path: Path | None = None) -> pd.DataFrame:
    path = path or _latest("difficulty_adjustments") or download_difficulty()
    df = pd.read_csv(path, float_precision="round_trip")
    df.index = pd.to_datetime(df["adjusted_at"], utc=True, format="ISO8601")
    df = df.drop(columns=["adjusted_at"])
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("difficulty adjustments must be strictly increasing in time")
    return df


def _last_known(cutoff: np.ndarray, known_at: np.ndarray, values: np.ndarray, back: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Value `back` observations before the last one known at each cutoff, plus the position (-1 = none)."""
    pos = np.searchsorted(known_at, cutoff, side="right") - 1 - back
    ok = pos >= 0
    return np.where(ok, values[np.clip(pos, 0, len(values) - 1)], np.nan), pos


def onchain_features(grid: pd.DatetimeIndex, daily: pd.DataFrame, difficulty: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=grid)
    cutoff = (grid + timedelta(hours=1)).to_numpy()
    staleness = None
    for key in SERIES:
        s = daily[key].dropna()
        known_at = (s.index + KNOWN_AFTER).to_numpy()
        values = s.to_numpy(dtype=float)
        last, pos = _last_known(cutoff, known_at, values)
        for k in (7, 30):
            earlier, _ = _last_known(cutoff, known_at, values, back=k)
            with np.errstate(invalid="ignore", divide="ignore"):
                out[f"{key}_chg_{k}d"] = np.where(earlier > 0, last / earlier - 1, np.nan)
        if key == "addr":
            known_time = np.where(pos >= 0, known_at[np.clip(pos, 0, len(known_at) - 1)], np.datetime64("NaT", "ns"))
            staleness = (cutoff - known_time) / np.timedelta64(1, "h")
    out["onchain_staleness_h"] = staleness

    adj_at = difficulty.index.to_numpy()
    adj_pct = (difficulty["change_factor"].to_numpy(dtype=float) - 1.0) * 100
    last_adj, _ = _last_known(cutoff, adj_at, adj_pct)
    out["difficulty_adj_last_pct"] = last_adj
    return out
