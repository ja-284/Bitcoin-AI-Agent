"""
Replays the analysis recipe over past hours, one simulated hour at a time, to see
how it would have behaved -- the "test every meaningful change against historical
data" rule (CLAUDE.md rule 7) in practice.

Two deliberate limitations:

1. Technical-only. RSS feeds have no archive, so there is no honest way to know what
   news the system would have seen at a past hour. Backtests therefore run with the
   news category absent (weight 0), exactly as a live run does when news is
   unavailable -- and results are labeled as such. They are not directly comparable
   to live runs, which do include news.

2. Point-in-time, enforced by construction. Each simulated hour is analysed from a
   slice `bars[:i + 1]` and nothing else -- the code path can't reach later bars
   because it is never handed them. tests/test_point_in_time.py checks this holds.
   Forward returns are looked up only afterwards, for grading, never for deciding.

Results go to a CSV under backtests/ (git-ignored), not to the predictions table,
so live data stays pure.

    python -m agent.backtest.runner --days 30
"""

import argparse
import csv
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.data_providers.binance import BinanceProvider
from agent.decision.decision import compute_confidence, decide_signal
from agent.indicators.engine import compute_indicators
from agent.patterns.rules import detect_patterns
from agent.scoring.scorer import SCORING_VERSION, score_all
from agent.shared.types import PriceBar

logger = logging.getLogger(__name__)

WARMUP_HOURS = 250  # longest indicator warm-up (200h SMA) plus margin
HORIZONS_HOURS = [1, 24, 168]
OUTPUT_DIR = Path("backtests")


@dataclass
class HourResult:
    as_of: datetime
    close: float
    signal: str
    overall_score: float
    confidence: float
    agreement: float
    completeness: float


def analyze_window(window: list[PriceBar]) -> HourResult:
    """Analyse one simulated hour. `window` is ALL the data this function may see."""
    indicators = compute_indicators(window)
    patterns = detect_patterns(window, indicators)
    result = score_all(window, indicators, patterns, news_score=None)
    confidence = compute_confidence(result)
    return HourResult(
        as_of=window[-1].as_of,
        close=window[-1].close,
        signal=decide_signal(result.overall_score),
        overall_score=result.overall_score,
        confidence=confidence.overall_confidence,
        agreement=confidence.agreement_score,
        completeness=confidence.completeness_score,
    )


def replay(bars: list[PriceBar], warmup: int = WARMUP_HOURS) -> list[HourResult]:
    return [analyze_window(bars[: i + 1]) for i in range(warmup, len(bars))]


def forward_returns(bars: list[PriceBar], results: list[HourResult], warmup: int = WARMUP_HOURS) -> list[dict]:
    """Grading only -- runs after every decision has already been made."""
    rows = []
    for offset, r in enumerate(results):
        i = warmup + offset
        row = {"as_of": r.as_of.isoformat(), "close": r.close, "signal": r.signal,
               "overall_score": round(r.overall_score, 4), "confidence": round(r.confidence, 4),
               "agreement": round(r.agreement, 4), "completeness": round(r.completeness, 4)}
        for h in HORIZONS_HOURS:
            row[f"return_{h}h"] = round((bars[i + h].close - r.close) / r.close, 6) if i + h < len(bars) else None
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> str:
    lines = [
        f"Scoring version: {SCORING_VERSION}   (technical-only: news absent, not comparable to live runs)",
        f"Hours analysed: {len(rows)}   from {rows[0]['as_of']} to {rows[-1]['as_of']}",
        "",
        f"{'signal':8s} {'count':>6s}" + "".join(f"{'avg ' + str(h) + 'h':>12s}" for h in HORIZONS_HOURS),
    ]
    for signal in ["BUY", "HOLD", "SELL", "ALL"]:
        group = rows if signal == "ALL" else [r for r in rows if r["signal"] == signal]
        cells = []
        for h in HORIZONS_HOURS:
            vals = [r[f"return_{h}h"] for r in group if r[f"return_{h}h"] is not None]
            cells.append(f"{statistics.mean(vals) * 100:+11.2f}%" if vals else f"{'n/a':>12s}")
        lines.append(f"{signal:8s} {len(group):6d}" + "".join(cells))
    lines.append("")
    lines.append("Read 'ALL' as the plain buy-and-hold baseline: a signal only shows skill if its")
    lines.append("average return differs from ALL in the direction it predicted, consistently, over")
    lines.append("many hours -- and one window proves nothing (CLAUDE.md rule 4).")
    return "\n".join(lines)


def run_backtest(days: int, end: datetime | None = None) -> tuple[list[dict], Path]:
    end = end or (datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1))
    hours = days * 24
    logger.info("Fetching %d hours of history (+%d warm-up) ending %s", hours, WARMUP_HOURS, end.isoformat())
    bars = BinanceProvider().get_history(end=end, hours=hours + WARMUP_HOURS)
    if len(bars) <= WARMUP_HOURS:
        raise RuntimeError(f"only {len(bars)} bars fetched; need more than {WARMUP_HOURS}")

    results = replay(bars)
    rows = forward_returns(bars, results)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"backtest_{rows[0]['as_of'][:10]}_{rows[-1]['as_of'][:10]}_v{SCORING_VERSION}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows, out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="how many days of history to replay (default 30)")
    parser.add_argument("--end", type=str, default=None, help="last hour to include, UTC, e.g. 2026-08-31T23:00")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    end_dt = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else None
    rows, path = run_backtest(args.days, end_dt)
    print()
    print(summarize(rows))
    print(f"\nPer-hour results written to {path}")
