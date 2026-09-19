"""
Replays the analysis recipe over past hours, one simulated hour at a time, to see
how it would have behaved -- the "test every meaningful change against historical
data" rule (CLAUDE.md rule 7) in practice.

Deliberate properties:

1. Technical-only. RSS feeds have no archive, so there is no honest way to know what
   news the system would have seen at a past hour. Backtests therefore run with the
   news category absent (weight 0), exactly as a live run does when news is
   unavailable -- and results are labeled as such. They are not directly comparable
   to live runs, which do include news.

2. Point-in-time, enforced by construction. Each simulated hour is analysed from
   exactly the trailing HISTORY_HOURS bars ending at that hour -- the same window a
   live run sees -- and nothing else; the code path can't reach later bars because it
   is never handed them. tests/test_point_in_time.py checks this holds, and
   tests/test_backtest_matches_live.py checks the window matches live behaviour.

3. Outcomes by timestamp, not by row count. "24 hours later" means the candle that
   opened exactly 24 hours after the reference candle. If that candle is missing from
   the data (exchange downtime), the outcome is UNAVAILABLE -- never the next row that
   happens to exist, never an invented value. Windows that contain a gap are flagged.

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
from agent.data_providers.quality import BarQualityReport, validate_bars
from agent.decision.decision import compute_confidence, decide_signal
from agent.indicators.engine import HISTORY_HOURS, compute_indicators
from agent.patterns.rules import detect_patterns
from agent.scoring.scorer import SCORING_VERSION, score_all
from agent.shared.types import PriceBar
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

HORIZONS_HOURS = [1, 6, 24, 72, 168]
OUTPUT_DIR = Path("backtests")
HOUR = timedelta(hours=1)


@dataclass
class HourResult:
    as_of: datetime  # reference candle open
    cutoff_at: datetime  # reference candle close = information cutoff
    close: float
    signal: str
    overall_score: float
    confidence: float
    agreement: float
    completeness: float
    window_missing_hours: int  # hours missing inside the feature window (0 = clean)


def analyze_window(window: list[PriceBar]) -> HourResult:
    """Analyse one simulated hour. `window` is ALL the data this function may see."""
    indicators = compute_indicators(window)
    patterns = detect_patterns(window, indicators)
    result = score_all(window, indicators, patterns, news_score=None)
    confidence = compute_confidence(result)
    expected_span = len(window) - 1
    actual_span = int((window[-1].as_of - window[0].as_of) / HOUR)
    return HourResult(
        as_of=window[-1].as_of,
        cutoff_at=window[-1].as_of + HOUR,
        close=window[-1].close,
        signal=decide_signal(result.overall_score),
        overall_score=result.overall_score,
        confidence=confidence.overall_confidence,
        agreement=confidence.agreement_score,
        completeness=confidence.completeness_score,
        window_missing_hours=actual_span - expected_span,
    )


def replay(bars: list[PriceBar], window: int = HISTORY_HOURS) -> list[HourResult]:
    """One result per hour from index window-1 onward, each computed from exactly `window` bars."""
    return [analyze_window(bars[i - window + 1 : i + 1]) for i in range(window - 1, len(bars))]


def forward_returns(bars: list[PriceBar], results: list[HourResult], horizons: list[int] = HORIZONS_HOURS) -> list[dict]:
    """
    Grading only -- runs after every decision has already been made. The outcome for
    horizon H is the close of the candle that OPENED at as_of + H hours (i.e. the price
    H hours after the cutoff). Missing candle -> None, recorded as unavailable.
    """
    by_time = {b.as_of: b for b in bars}
    rows = []
    for r in results:
        row = {
            "as_of": r.as_of.isoformat(),
            "cutoff_at": r.cutoff_at.isoformat(),
            "close": r.close,
            "signal": r.signal,
            "overall_score": round(r.overall_score, 4),
            "confidence": round(r.confidence, 4),
            "agreement": round(r.agreement, 4),
            "completeness": round(r.completeness, 4),
            "window_missing_hours": r.window_missing_hours,
        }
        for h in horizons:
            target = by_time.get(r.as_of + timedelta(hours=h))
            row[f"return_{h}h"] = round((target.close - r.close) / r.close, 6) if target is not None else None
        rows.append(row)
    return rows


def summarize(rows: list[dict], quality: BarQualityReport | None = None, horizons: list[int] = HORIZONS_HOURS) -> str:
    lines = [
        f"Pipeline {PIPELINE_VERSION} / scoring {SCORING_VERSION}   (technical-only: news absent, not comparable to live runs)",
        f"Hours analysed: {len(rows)}   from {rows[0]['as_of']} to {rows[-1]['as_of']}",
    ]
    if quality is not None:
        lines.append(f"Data: {quality.count} candles, {len(quality.gaps)} gap(s), {quality.missing_hours} missing hour(s)")
    flagged = sum(1 for r in rows if r["window_missing_hours"])
    unavailable = {h: sum(1 for r in rows if r[f"return_{h}h"] is None) for h in horizons}
    lines.append(f"Hours whose feature window contains a gap: {flagged}")
    lines.append("Outcomes unavailable (missing target candle): " + ", ".join(f"{h}h={n}" for h, n in unavailable.items()))
    lines.append("")
    lines.append(f"{'signal':8s} {'count':>6s}" + "".join(f"{'avg ' + str(h) + 'h':>12s}" for h in horizons))
    for signal in ["BUY", "HOLD", "SELL", "ALL"]:
        group = rows if signal == "ALL" else [r for r in rows if r["signal"] == signal]
        cells = []
        for h in horizons:
            vals = [r[f"return_{h}h"] for r in group if r[f"return_{h}h"] is not None]
            cells.append(f"{statistics.mean(vals) * 100:+11.2f}%" if vals else f"{'n/a':>12s}")
        lines.append(f"{signal:8s} {len(group):6d}" + "".join(cells))
    lines.append("")
    lines.append("Read 'ALL' as the plain buy-and-hold baseline. Averages hide everything that matters")
    lines.append("(consistency, uncertainty, regime); the research evaluation adds those. One window proves nothing.")
    return "\n".join(lines)


def run_backtest(days: int, end: datetime | None = None) -> tuple[list[dict], Path, BarQualityReport]:
    end = end or (datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0) - HOUR)
    hours = days * 24
    logger.info("Fetching %d hours of history (+%d warm-up) ending %s", hours, HISTORY_HOURS, end.isoformat())
    bars = BinanceProvider().get_history(end=end, hours=hours + HISTORY_HOURS)
    quality = validate_bars(bars)
    if quality.gaps:
        logger.warning("History has %d gap(s), %d missing hour(s) -- flagged, not filled", len(quality.gaps), quality.missing_hours)
    if len(bars) < HISTORY_HOURS:
        raise RuntimeError(f"only {len(bars)} bars fetched; need at least {HISTORY_HOURS}")

    results = replay(bars)
    rows = forward_returns(bars, results)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out = OUTPUT_DIR / f"backtest_{rows[0]['as_of'][:10]}_{rows[-1]['as_of'][:10]}_p{PIPELINE_VERSION}_s{SCORING_VERSION}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows, out, quality


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="how many days of history to replay (default 30)")
    parser.add_argument("--end", type=str, default=None, help="last hour to include, UTC, e.g. 2026-08-31T23:00")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    end_dt = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc) if args.end else None
    rows, path, quality = run_backtest(args.days, end_dt)
    print()
    print(summarize(rows, quality))
    print(f"\nPer-hour results written to {path}")
