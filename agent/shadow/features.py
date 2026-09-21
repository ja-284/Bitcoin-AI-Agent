"""
The model's inputs for the reference hour, computed from a window of closed candles with
the SAME research code that produced E012/E013 (agent/research/features.py and
agent/research/microstructure.py), so live and research cannot drift apart silently.

Point-in-time: every value uses candles with as_of <= reference hour only. A gap inside a
window blanks that window (min_periods = window) and the hour is reported unavailable --
never filled.
"""

import math
from datetime import datetime, timezone

import pandas as pd

from agent.research.features import all_features, bars_to_frame
from agent.research.microstructure import microstructure_features
from agent.shared.types import PriceBar

WINDOW_HOURS = 250  # same window the live indicators use; the longest input needs 169 closed hours


def extras_frame(rows: list[tuple[datetime, float, int, float]]) -> pd.DataFrame:
    """(as_of, volume, trades, taker_buy_volume) rows -> the frame microstructure_features expects."""
    df = pd.DataFrame(rows, columns=["as_of", "volume", "trades", "taker_buy_volume"])
    df["as_of"] = pd.to_datetime(df["as_of"], utc=True)
    df = df.set_index("as_of").sort_index()
    if df.index.has_duplicates:
        raise ValueError("duplicate hours in trade data")
    return df


def feature_row(bars: list[PriceBar], extras: pd.DataFrame, names: tuple[str, ...]) -> tuple[dict, str | None]:
    """
    Raw feature values at the last bar (the reference hour). Returns (values, reason) where
    reason is None when every requested input exists, else says what is missing.
    """
    if not bars:
        return {}, "no candles"
    grid = bars_to_frame(bars).index
    feats = pd.concat([all_features(bars), microstructure_features(grid, extras)], axis=1)
    ref = pd.Timestamp(bars[-1].as_of)
    if ref.tzinfo is None:
        ref = ref.tz_localize(timezone.utc)
    last = feats.loc[ref]
    values, missing = {}, []
    for n in names:
        v = last.get(n)
        v = None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)
        values[n] = v
        if v is None:
            missing.append(n)
    reason = None if not missing else f"missing inputs at {ref.isoformat()}: {', '.join(missing)}"
    return values, reason
