"""
Trivial reference systems. Their job is not to be good; it is to show whether the
five-category system contains information beyond what a coin flip, a constant answer,
or a one-line rule already gives. Each takes the replay rows (time-ordered) and returns
one BUY/HOLD/SELL signal per row, using only information in that row or earlier rows.
"""

from datetime import datetime, timedelta

import numpy as np

SIGNALS = ["BUY", "HOLD", "SELL"]


def always(signal: str, rows: list[dict]) -> list[str]:
    return [signal] * len(rows)


def random_signals(rows: list[dict], probabilities: dict[str, float], seed: int = 0) -> list[str]:
    """Random signals drawn with fixed probabilities (e.g. the system's own signal mix on a prior period)."""
    rng = np.random.default_rng(seed)
    labels = list(probabilities)
    p = np.array([probabilities[s] for s in labels], float)
    p = p / p.sum()
    return list(rng.choice(labels, size=len(rows), p=p))


def momentum_rule(rows: list[dict], lookback_hours: int = 24) -> list[str]:
    """BUY if the close is above the close `lookback_hours` earlier, SELL if below; HOLD if that hour is missing."""
    close_at = {datetime.fromisoformat(r["as_of"]): r["close"] for r in rows}
    out = []
    for r in rows:
        earlier = close_at.get(datetime.fromisoformat(r["as_of"]) - timedelta(hours=lookback_hours))
        if earlier is None or r["close"] == earlier:
            out.append("HOLD")
        else:
            out.append("BUY" if r["close"] > earlier else "SELL")
    return out


def moving_average_rule(rows: list[dict]) -> list[str]:
    """BUY if the close is above its 200-hour average, SELL if below (the classic one-liner)."""
    out = []
    for r in rows:
        sma = r.get("ind_sma_long")
        if sma is None or r["close"] == sma:
            out.append("HOLD")
        else:
            out.append("BUY" if r["close"] > sma else "SELL")
    return out


def signal_mix(signals: list[str]) -> dict[str, float]:
    n = len(signals)
    return {s: signals.count(s) / n for s in SIGNALS} if n else {s: 1 / 3 for s in SIGNALS}
