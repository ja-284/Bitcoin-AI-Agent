"""
Replays the live analysis over history, keeping every intermediate number per hour --
category scores with their weights, indicator values, pattern states -- not just the
final signal. That lets later steps (ablation, feature diagnosis, alternative scoring)
recombine the stored pieces instead of recomputing, and it lets a reader see exactly
why any historical hour got the signal it did.

Each hour is computed from exactly HISTORY_HOURS bars (identical to live; verified by
tests/test_backtest_matches_live.py), using the same functions the live run uses. Work
is spread over processes; results are cached under data/replays/ keyed by snapshot,
range and version stamps, so a full replay costs a couple of minutes once.
"""

import csv
import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from multiprocessing import Pool
from pathlib import Path

from agent.decision.decision import compute_confidence, decide_signal
from agent.indicators.engine import HISTORY_HOURS, compute_indicators
from agent.patterns.rules import detect_patterns
from agent.scoring.scorer import SCORING_VERSION, score_all
from agent.shared.types import PriceBar
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

REPLAY_DIR = Path("data") / "replays"
HOUR = timedelta(hours=1)
CATEGORIES = ["trend", "momentum", "volume", "chart_pattern", "news"]
INDICATOR_FIELDS = ["sma_short", "sma_long", "rsi", "macd", "macd_signal", "macd_histogram", "bb_upper", "bb_lower", "volume", "volume_avg"]

_BARS: list[PriceBar] = []


def analyze_window_detailed(window: list[PriceBar]) -> dict:
    """Everything the live run computes for one hour, flattened. `window` is all it may see."""
    indicators = compute_indicators(window)
    patterns = detect_patterns(window, indicators)
    result = score_all(window, indicators, patterns, news_score=None)
    confidence = compute_confidence(result)

    row = {
        "as_of": window[-1].as_of.isoformat(),
        "cutoff_at": (window[-1].as_of + HOUR).isoformat(),
        "close": window[-1].close,
        "window_missing_hours": int((window[-1].as_of - window[0].as_of) / HOUR) - (len(window) - 1),
        "overall_score": result.overall_score,
        "signal": decide_signal(result.overall_score),
        "confidence": confidence.overall_confidence,
        "agreement": confidence.agreement_score,
        "completeness": confidence.completeness_score,
    }
    by_name = {c.name: c for c in result.category_scores}
    for name in CATEGORIES:
        c = by_name[name]
        row[f"{name}_score"] = c.score
        row[f"{name}_weight"] = c.weight
        row[f"{name}_independent"] = c.is_independent
    ind = asdict(indicators)
    for f in INDICATOR_FIELDS:
        row[f"ind_{f}"] = ind[f]
    row["pat_ma_cross"] = patterns.ma_cross
    row["pat_trend_structure"] = patterns.trend_structure
    row["pat_bb_position"] = patterns.bb_position
    return row


def _init_worker(bars: list[PriceBar]) -> None:
    global _BARS
    _BARS = bars


def _analyze_index(i: int) -> dict:
    return analyze_window_detailed(_BARS[i - HISTORY_HOURS + 1 : i + 1])


def replay_detailed(bars: list[PriceBar], processes: int | None = None, window: int = HISTORY_HOURS) -> list[dict]:
    indices = range(window - 1, len(bars))
    if processes == 1:
        _init_worker(bars)
        return [_analyze_index(i) for i in indices]
    with Pool(processes=processes, initializer=_init_worker, initargs=(bars,)) as pool:
        return list(pool.imap(_analyze_index, indices, chunksize=256))


def replay_cache_path(snapshot: Path, start: datetime, end: datetime) -> Path:
    tag = f"{snapshot.stem}_{start.strftime('%Y%m%d%H')}_{end.strftime('%Y%m%d%H')}_p{PIPELINE_VERSION}_s{SCORING_VERSION}"
    return REPLAY_DIR / f"replay_{tag}.csv"


def write_replay(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_replay(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    numeric = {k for k in rows[0] if k not in ("as_of", "cutoff_at", "signal", "pat_ma_cross", "pat_trend_structure", "pat_bb_position")
               and not k.endswith("_independent")}
    for r in rows:
        for k in numeric:
            r[k] = None if r[k] in ("", "None") else float(r[k])
        for k in [k for k in r if k.endswith("_independent")]:
            r[k] = r[k] == "True"
    return rows


def replay_cached(bars: list[PriceBar], snapshot: Path, processes: int | None = None) -> list[dict]:
    path = replay_cache_path(snapshot, bars[HISTORY_HOURS - 1].as_of, bars[-1].as_of)
    if path.exists():
        logger.info("Using cached replay %s", path)
        return read_replay(path)
    logger.info("Replaying %d hours over %s processes...", len(bars) - HISTORY_HOURS + 1, processes or "all")
    rows = replay_detailed(bars, processes=processes)
    write_replay(rows, path)
    logger.info("Replay written to %s", path)
    return rows
