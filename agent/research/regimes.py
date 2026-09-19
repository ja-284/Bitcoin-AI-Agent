"""
Market-regime labels, defined mathematically and point-in-time: each hour's regime uses
only prices up to that hour's cutoff.

  trend regime      30-day (720h) return up to the reference candle:
                    > +10% "uptrend", < -10% "downtrend", otherwise "sideways"
  volatility regime realised volatility = std of hourly log returns over the last 720h;
                    "high" / "mid" / "low" by terciles of that measure over the
                    EXPLORATION period (fixed constants, so later periods are judged
                    against a threshold that was decided before they were seen)

These are descriptive labels for slicing results, not features -- and like any regime
definition they are a choice, so results by regime are always reported next to results
overall.
"""

from datetime import datetime, timedelta

import numpy as np

from agent.research.periods import EXPLORATION

TREND_LOOKBACK_HOURS = 720
TREND_THRESHOLD = 0.10
VOL_LOOKBACK_HOURS = 720
VOL_MIN_SAMPLES = 480


def _log_returns(rows: list[dict]) -> dict[datetime, float]:
    out = {}
    prev = None
    for r in rows:
        t = datetime.fromisoformat(r["as_of"])
        if prev is not None and prev[0] == t - timedelta(hours=1):
            out[t] = float(np.log(r["close"] / prev[1]))
        prev = (t, r["close"])
    return out


def realised_vol(rows: list[dict]) -> list[float | None]:
    """Per row: std of the hourly log returns in the trailing VOL_LOOKBACK_HOURS (None if too few)."""
    lr = _log_returns(rows)
    times = [datetime.fromisoformat(r["as_of"]) for r in rows]
    values = np.array([lr.get(t, np.nan) for t in times])
    out: list[float | None] = []
    for i in range(len(rows)):
        lo = max(0, i - VOL_LOOKBACK_HOURS + 1)
        window = values[lo : i + 1]
        window = window[~np.isnan(window)]
        out.append(float(window.std()) if len(window) >= VOL_MIN_SAMPLES else None)
    return out


def trend_regime(rows: list[dict]) -> list[str | None]:
    close_at = {datetime.fromisoformat(r["as_of"]): r["close"] for r in rows}
    out = []
    for r in rows:
        earlier = close_at.get(datetime.fromisoformat(r["as_of"]) - timedelta(hours=TREND_LOOKBACK_HOURS))
        if earlier is None:
            out.append(None)
            continue
        change = r["close"] / earlier - 1
        out.append("uptrend" if change > TREND_THRESHOLD else "downtrend" if change < -TREND_THRESHOLD else "sideways")
    return out


def volatility_regime(rows: list[dict]) -> tuple[list[str | None], tuple[float, float]]:
    """Returns (regime per row, (low_cut, high_cut)) with cuts = terciles over EXPLORATION rows."""
    vol = realised_vol(rows)
    exploration_vol = [v for r, v in zip(rows, vol) if v is not None and EXPLORATION.contains(datetime.fromisoformat(r["as_of"]))]
    if not exploration_vol:
        return [None] * len(rows), (float("nan"), float("nan"))
    low_cut, high_cut = np.percentile(exploration_vol, [33.3, 66.7])
    regime = [None if v is None else ("low" if v <= low_cut else "high" if v > high_cut else "mid") for v in vol]
    return regime, (float(low_cut), float(high_cut))
