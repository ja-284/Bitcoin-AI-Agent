"""
Backend Phase A: live / research parity, checked on the real live record.

Question: if the research replay is run today on the exchange's candles for the hours the
live job already analysed, does it reproduce what the live job stored at the time?
Every stored live hour (pipeline 0.2.0, real Binance data) is re-analysed with the research
replay function on a window of exactly HISTORY_HOURS candles ending at that hour, and the
two are compared field by field:

  reference close and volume      the candle itself (exchange revisions would show here)
  raw indicators                  RSI, MACD, SMAs, Bollinger, volume average
  the four technical categories   trend, momentum, volume, chart_pattern -- score and weight
  overall score WITHOUT news      recombined from the stored categories with news at weight 0,
                                  because the replay has no news and live does

Anything outside tolerance is a parity break and is reported, never averaged away. The
comparison itself is a pure function (tested); only fetch() touches the exchange/database.
"""

import logging
import math
from datetime import datetime, timedelta, timezone

from agent.data_providers.binance import BinanceProvider
from agent.indicators.engine import HISTORY_HOURS
from agent.research.replay import analyze_window_detailed
from agent.scoring.scorer import combine_scores
from agent.shared.types import CategoryScore, PriceBar
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)
HOUR = timedelta(hours=1)
TECHNICAL = ("trend", "momentum", "volume", "chart_pattern")
INDICATORS = ("rsi", "macd", "macd_signal", "macd_histogram", "sma_short", "sma_long", "bb_upper", "bb_lower", "volume_avg")
REL_TOL = 1e-9


def _close(a, b, rel=REL_TOL, abs_=1e-9) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_)


def overall_without_news(category_scores: list[dict]) -> float:
    """The live overall score recombined with the news category at weight 0 -- what the replay computes."""
    cats = [CategoryScore(name=c["name"], score=float(c["score"]), weight=0.0 if c["name"] == "news" else float(c["weight"]),
                          is_independent=bool(c.get("is_independent", True)), detail=c.get("detail") or {}) for c in category_scores]
    return combine_scores(cats).overall_score


def compare_hour(live: dict, replay: dict) -> dict:
    """
    live: a stored prediction row (as_of, close_price, category_scores, raw_indicators, price_is_synthetic).
    replay: analyze_window_detailed() output for the same hour. Returns the list of mismatches.
    """
    mismatches = []
    if not _close(live["close_price"], replay["close"]):
        mismatches.append(("close_price", live["close_price"], replay["close"]))
    ind = live["raw_indicators"] or {}
    if not _close(ind.get("volume"), replay.get("ind_volume")):
        mismatches.append(("volume", ind.get("volume"), replay.get("ind_volume")))
    for f in INDICATORS:
        if not _close(ind.get(f), replay.get(f"ind_{f}"), rel=1e-7, abs_=1e-6):
            mismatches.append((f"indicator.{f}", ind.get(f), replay.get(f"ind_{f}")))
    by_name = {c["name"]: c for c in live["category_scores"]}
    for name in TECHNICAL:
        c = by_name.get(name)
        if c is None:
            mismatches.append((f"category.{name}", "missing", replay.get(f"{name}_score")))
            continue
        if not _close(c["score"], replay.get(f"{name}_score"), rel=1e-7, abs_=1e-9):
            mismatches.append((f"category.{name}.score", c["score"], replay.get(f"{name}_score")))
        if not _close(c["weight"], replay.get(f"{name}_weight")):
            mismatches.append((f"category.{name}.weight", c["weight"], replay.get(f"{name}_weight")))
    try:
        recombined = overall_without_news(live["category_scores"])
        if not _close(recombined, replay["overall_score"], rel=1e-7, abs_=1e-9):
            mismatches.append(("overall_score_without_news", recombined, replay["overall_score"]))
    except Exception as exc:  # noqa: BLE001
        mismatches.append(("overall_score_without_news", f"error: {exc}", replay.get("overall_score")))
    return {"as_of": live["as_of"].isoformat(), "ok": not mismatches, "mismatches": mismatches, "synthetic": bool(live.get("price_is_synthetic"))}


def check(live_rows: list[dict], bars: list[PriceBar]) -> dict:
    """Pure: re-analyse every live hour from `bars` (must cover HISTORY_HOURS before the first live hour) and compare."""
    by_time = {b.as_of: i for i, b in enumerate(bars)}
    results, skipped = [], []
    for row in live_rows:
        if row["pipeline_version"] != PIPELINE_VERSION:
            skipped.append((row["as_of"].isoformat(), "pipeline version differs"))
            continue
        if row.get("price_is_synthetic"):
            skipped.append((row["as_of"].isoformat(), "live row used fallback (synthetic) data"))
            continue
        i = by_time.get(row["as_of"])
        if i is None or i + 1 < HISTORY_HOURS:
            skipped.append((row["as_of"].isoformat(), "no full candle window available"))
            continue
        window = bars[i + 1 - HISTORY_HOURS : i + 1]
        results.append(compare_hour(row, analyze_window_detailed(window)))
    breaks = [r for r in results if not r["ok"]]
    return {"compared": len(results), "parity_breaks": len(breaks), "breaks": breaks[:20], "skipped": skipped,
            "verdict": "PARITY" if results and not breaks else ("NO ROWS" if not results else "BREAK")}


def fetch_live_rows(since: datetime) -> list[dict]:
    from agent.database.db import get_connection

    with get_connection() as c, c.cursor() as cur:
        cur.execute("""SELECT as_of, close_price, category_scores, raw_indicators, price_is_synthetic, pipeline_version
                       FROM predictions WHERE as_of >= %s ORDER BY as_of""", (since,))
        return [dict(zip(["as_of", "close_price", "category_scores", "raw_indicators", "price_is_synthetic", "pipeline_version"], r)) for r in cur.fetchall()]


def run(since: datetime, now: datetime | None = None) -> dict:
    now = now or datetime.now(tz=timezone.utc)
    rows = fetch_live_rows(since)
    if not rows:
        return {"compared": 0, "parity_breaks": 0, "breaks": [], "skipped": [], "verdict": "NO ROWS"}
    end = now.replace(minute=0, second=0, microsecond=0) - HOUR
    hours = int((end - rows[0]["as_of"]).total_seconds() // 3600) + HISTORY_HOURS + 1
    bars = BinanceProvider().get_history(end=end, hours=hours)
    out = check(rows, bars)
    out["candles_fetched"] = len(bars)
    return out


if __name__ == "__main__":
    import json
    import sys

    from agent.research.periods import LIVE

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(run(LIVE.start), indent=2, default=str))
