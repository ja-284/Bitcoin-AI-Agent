"""
Grade shadow rows once their target candle exists: the candle opening at as_of + horizon,
by timestamp (the same rule as the live outcome tracker; its helpers are reused so the two
cannot disagree). Rows whose target candle never appears become 'unavailable' after the
same grace period. Grading never changes p or the features -- it only fills the outcome.

    python -m agent.shadow.outcomes
"""

import logging
from datetime import datetime, timezone

from agent.data_providers.binance import BinanceProvider
from agent.outcome_tracker import HOUR, UNAVAILABLE_GRACE, target_candle_open
from agent.shadow.db import save_shadow_outcome, shadow_rows_awaiting_outcome

logger = logging.getLogger(__name__)


def grade(reference_close: float, target_close: float, threshold: float) -> tuple[float, bool]:
    ret = (target_close - reference_close) / reference_close
    return ret, abs(ret) > threshold


def track(now: datetime | None = None, provider: BinanceProvider | None = None) -> dict:
    now = now or datetime.now(tz=timezone.utc)
    provider = provider or BinanceProvider()
    counts = {"graded": 0, "unavailable": 0, "deferred": 0, "errors": 0}
    for row_id, as_of, ref_close, threshold, horizon in shadow_rows_awaiting_outcome(now):
        target_open = target_candle_open(as_of, horizon)
        try:
            bar = provider.get_bar_at(target_open)
        except Exception as exc:  # noqa: BLE001 -- leave it; the next run retries
            logger.warning("Shadow outcome lookup failed for %s: %s", as_of, exc)
            counts["errors"] += 1
            continue
        if bar is None:
            if now >= target_open + HOUR + UNAVAILABLE_GRACE:
                save_shadow_outcome(row_id, None, None, None, "unavailable", now)
                counts["unavailable"] += 1
            else:
                counts["deferred"] += 1
            continue
        if bar.as_of != target_open:
            raise RuntimeError(f"provider returned candle {bar.as_of} for requested {target_open}")
        ret, large = grade(ref_close, bar.close, threshold)
        save_shadow_outcome(row_id, bar.close, ret, large, "ok", now)
        counts["graded"] += 1
    logger.info("Shadow outcomes: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(track())
