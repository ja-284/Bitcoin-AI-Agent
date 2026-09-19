"""
Explicit target definitions. Nothing here is "Bitcoin went up"; every label is a
documented, configurable rule:

  reference price   close of the reference candle (the price at the information cutoff)
  outcome price     close of the candle that OPENED at as_of + H, i.e. the price H hours
                    after the cutoff; found by timestamp, missing candle -> no label
  return            outcome / reference - 1
  binary            UP if return > 0 else DOWN
  three-class       UP if return > +threshold, DOWN if return < -threshold, else NEUTRAL
  threshold         fixed: a constant return (e.g. 0.005 = 0.5%)
                    vol_scaled: k x median |return| over the last L hours of COMPLETED
                    returns -- only returns whose outcome candle had closed by this
                    hour's cutoff, so the threshold itself can't see the future

Labels are used only for evaluation. The prediction pipeline never sees them.
"""

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from agent.shared.types import PriceBar

HOUR = timedelta(hours=1)
UP, DOWN, NEUTRAL = "UP", "DOWN", "NEUTRAL"


@dataclass(frozen=True)
class LabelSpec:
    horizon_hours: int
    kind: str = "binary"  # "binary" | "three_class"
    threshold_kind: str = "fixed"  # "fixed" | "vol_scaled"; ignored for binary
    threshold: float = 0.0  # fixed: absolute return; vol_scaled: multiplier k of the median absolute return
    vol_lookback_hours: int = 720  # 30 days of completed returns
    min_vol_samples: int = 240  # below this many completed returns, the threshold (and label) is unavailable

    def __post_init__(self):
        if self.kind not in ("binary", "three_class"):
            raise ValueError(f"unknown label kind {self.kind!r}")
        if self.threshold_kind not in ("fixed", "vol_scaled"):
            raise ValueError(f"unknown threshold kind {self.threshold_kind!r}")
        if self.horizon_hours < 1:
            raise ValueError("horizon must be >= 1 hour")

    @property
    def name(self) -> str:
        if self.kind == "binary":
            return f"binary_{self.horizon_hours}h"
        return f"three_class_{self.horizon_hours}h_{self.threshold_kind}_{self.threshold:g}"


def forward_returns(bars: list[PriceBar], horizon_hours: int) -> pd.Series:
    """Return per reference hour (index = as_of), NaN where the outcome candle is missing."""
    closes = pd.Series({b.as_of: b.close for b in bars})
    target_index = closes.index + timedelta(hours=horizon_hours)
    outcome = closes.reindex(target_index).to_numpy()
    return pd.Series(outcome / closes.to_numpy() - 1.0, index=closes.index, name=f"ret_{horizon_hours}h")


def point_in_time_thresholds(returns: pd.Series, spec: LabelSpec) -> pd.Series:
    """
    Volatility-scaled threshold per hour, using only returns that were COMPLETE at that
    hour's cutoff. A return for reference hour s completes when its outcome candle closes,
    at s + H + 1h; it is usable by decision hour t (cutoff t + 1h) when s + H <= t.
    So each return is shifted forward by H hours before the rolling window is applied.
    """
    known_at = returns.dropna().abs()
    known_at.index = known_at.index + timedelta(hours=spec.horizon_hours)
    rolling = known_at.rolling(f"{spec.vol_lookback_hours}h", min_periods=spec.min_vol_samples).median()
    aligned = rolling.reindex(returns.index, method="ffill")
    # ffill carries the last value forward; if that last completed return is older than the
    # lookback window (a long data gap), the threshold is stale and must not be used.
    last_known = pd.Series(known_at.index, index=known_at.index).reindex(returns.index, method="ffill")
    age = (returns.index.to_series() - last_known).dt.total_seconds()
    aligned[age.isna() | (age > spec.vol_lookback_hours * 3600)] = float("nan")
    return spec.threshold * aligned


def make_labels(bars: list[PriceBar], spec: LabelSpec) -> pd.DataFrame:
    """One row per reference hour: return, threshold used, label (None if unavailable)."""
    ret = forward_returns(bars, spec.horizon_hours)
    df = pd.DataFrame({"as_of": ret.index, "ret": ret.to_numpy()})
    df["cutoff_at"] = df["as_of"] + HOUR

    if spec.kind == "binary":
        df["threshold"] = 0.0
        df["label"] = pd.Series([None if pd.isna(r) else (UP if r > 0 else DOWN) for r in df["ret"]], dtype=object)
        return df

    if spec.threshold_kind == "fixed":
        df["threshold"] = spec.threshold
    else:
        df["threshold"] = point_in_time_thresholds(ret, spec).to_numpy()

    labels = []
    for r, th in zip(df["ret"], df["threshold"]):
        if pd.isna(r) or pd.isna(th):
            labels.append(None)
        elif r > th:
            labels.append(UP)
        elif r < -th:
            labels.append(DOWN)
        else:
            labels.append(NEUTRAL)
    df["label"] = pd.Series(labels, dtype=object)  # object dtype keeps None as "no label" (pandas 3 would turn it into NaN)
    return df


SIGNAL_TO_LABEL = {"BUY": UP, "SELL": DOWN, "HOLD": NEUTRAL}
