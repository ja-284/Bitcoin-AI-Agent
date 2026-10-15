"""
Grade direction rows once their target candle exists: the candle opening at as_of + 1h, found by timestamp (the live
outcome tracker's own helpers, so the two cannot disagree). A target candle that never appears becomes 'unavailable'
after the same grace period. Grading never changes a probability or an input; it only fills the outcome, once.

    python -m agent.direction_shadow.outcomes

A failure is recorded in shadow_direction_errors (step 'outcomes') and the step exits 0; the next run retries.
"""

import logging
import sys
from datetime import datetime, timezone

from agent.data_providers.binance import BinanceProvider
from agent.outcome_tracker import HOUR, UNAVAILABLE_GRACE, target_candle_open

logger = logging.getLogger(__name__)


def grade(reference_close: float, target_close: float) -> tuple[float, bool]:
    """(return as a FRACTION, UP?). A tie is not UP (research/DIRECTION_TRACK.md, section 1)."""
    ret = (target_close - reference_close) / reference_close
    return ret, ret > 0


def track(now: datetime | None = None, provider: BinanceProvider | None = None) -> dict:
    from agent.direction_shadow.db import rows_awaiting_outcome, save_outcome

    now = now or datetime.now(tz=timezone.utc)
    provider = provider or BinanceProvider()
    counts = {"graded": 0, "unavailable": 0, "deferred": 0, "errors": 0}
    for row_id, as_of, ref_close, horizon in rows_awaiting_outcome(now):
        target_open = target_candle_open(as_of, horizon)
        try:
            bar = provider.get_bar_at(target_open)
        except Exception as exc:  # noqa: BLE001 -- leave it; the next run retries
            logger.warning("Direction outcome lookup failed for %s: %s", as_of, exc)
            counts["errors"] += 1
            continue
        if bar is None:
            if now >= target_open + HOUR + UNAVAILABLE_GRACE:
                save_outcome(row_id, None, None, None, "unavailable", now)
                counts["unavailable"] += 1
            else:
                counts["deferred"] += 1
            continue
        if bar.as_of != target_open:
            raise RuntimeError(f"provider returned candle {bar.as_of} for requested {target_open}")
        ret, up = grade(ref_close, bar.close)
        save_outcome(row_id, bar.close, ret, up, "ok", now)
        counts["graded"] += 1
    logger.info("Direction outcomes: %s", counts)
    return counts


def track_and_record() -> int:
    try:
        track()
        return 0
    except Exception as exc:  # noqa: BLE001
        from agent.direction_shadow.model import DEFAULT_VERSION
        from agent.direction_shadow.run import DirectionRunError, record_failure

        return record_failure(DirectionRunError("outcomes", exc), DEFAULT_VERSION)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(track_and_record())
