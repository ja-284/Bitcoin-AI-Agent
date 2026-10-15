"""
The direction model's inputs for the reference hour, computed by the SAME research code that built E032's rows, so
live and research cannot drift apart silently (research/DIRECTION_TRACK.md, section 3):
- the four category scores by agent.research.replay.analyze_window_detailed on exactly the fetched window. That is
  the historical replay's own function, and it calls the live scoring code;
- the four candle inputs (and rv_168, for the descriptive regime split only) by the move-size shadow's feature code,
  agent/shadow/features.feature_row, which is the research feature code.

Point-in-time: the window is the 250 closed candles ending at the reference hour, nothing later. A missing input is
reported, never filled.
"""

import math

import pandas as pd

from agent.indicators.engine import HISTORY_HOURS
from agent.research.replay import analyze_window_detailed
from agent.shadow.features import FEATURE_CHECK_ROWS, extras_frame, feature_row, reference_series
from agent.shared.types import PriceBar

CATEGORY_INPUTS = ("trend_score", "momentum_score", "volume_score", "chart_pattern_score")
CANDLE_INPUTS = ("tr_mean_14_rel", "trades_rel_168h", "taker_buy_share_1h", "taker_buy_share_6h")
INPUTS = CATEGORY_INPUTS + CANDLE_INPUTS  # E032's eight in E032's order (a test pins it to direction_probability.INPUTS)
ONE_FEATURE = "taker_buy_share_1h"
REGIME_FEATURE = "rv_168"                         # descriptive only, never an input
WINDOW_HOURS = HISTORY_HOURS                      # 250: the replay's and the live run's window


def _clean(v) -> float | None:
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else v


def input_row(bars: list[PriceBar], extras_rows: list) -> tuple[dict, float | None, str | None]:
    """
    (the eight raw inputs, rv_168, reason). `reason` is None when every input exists, else says what is missing.
    `bars` must be exactly the WINDOW_HOURS closed candles ending at the reference hour.
    """
    if len(bars) != WINDOW_HOURS:
        return {}, None, f"{len(bars)} candles, expected exactly {WINDOW_HOURS}"
    detail = analyze_window_detailed(bars)
    values = {k: _clean(detail.get(k)) for k in CATEGORY_INPUTS}
    candle, _ = feature_row(bars, extras_frame(extras_rows), CANDLE_INPUTS + (REGIME_FEATURE,))
    values.update({k: _clean(candle.get(k)) for k in CANDLE_INPUTS})
    values = {k: values[k] for k in INPUTS}
    missing = [k for k, v in values.items() if v is None]
    reason = None if not missing else f"missing inputs at {bars[-1].as_of.isoformat()}: {', '.join(missing)}"
    return values, _clean(candle.get(REGIME_FEATURE)), reason


def reference_values() -> dict[str, list[float]]:
    """
    Every input's value over the last FEATURE_CHECK_ROWS hours of the move-size shadow's fixed synthetic series.
    Stored in the artefact and re-checked at load time, so coefficients fitted on one definition of an input are
    never evaluated on another. The category scores are included: a change to the scoring code changes them.
    """
    bars, extras = reference_series()
    rows = [(t.to_pydatetime(), float(r.volume), int(r.trades), float(r.taker_buy_volume)) for t, r in extras.iterrows()]
    out: dict[str, list[float]] = {k: [] for k in INPUTS}
    n = len(bars)
    for end in range(n - FEATURE_CHECK_ROWS, n):
        window = bars[end - WINDOW_HOURS + 1:end + 1]
        values, _, _ = input_row(window, rows[end - WINDOW_HOURS + 1:end + 1])
        for k in INPUTS:
            v = values.get(k)
            out[k].append(float("nan") if v is None else float(v))
    return out


def extras_rows_from_frame(df: pd.DataFrame) -> list:
    """Helper for tests and tools: an extras frame back to (as_of, volume, trades, taker_buy_volume) rows."""
    return [(t.to_pydatetime(), float(r.volume), int(r.trades), float(r.taker_buy_volume)) for t, r in df.iterrows()]
