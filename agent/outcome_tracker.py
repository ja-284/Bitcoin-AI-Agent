"""
Grades past predictions against what the price actually did afterwards, at a few
fixed time horizons. This is the raw material for checking, later on, whether the
confidence numbers mean anything (CLAUDE.md rule 6) -- so it records prices and
returns only, and deliberately does NOT decide whether a signal was "right". That
judgement (which horizon matters, what counts as a win, how to compare against
plain buy-and-hold) belongs to a later analysis step, not to a nightly job.

Runs after each hourly analysis. It's never urgent: if the price lookup fails, the
prediction simply stays ungraded and gets picked up on a later run.

    python -m agent.outcome_tracker
"""

import logging
from datetime import datetime, timedelta, timezone

from agent.data_providers.binance import BinanceProvider
from agent.database.db import predictions_awaiting_outcome, save_outcome

logger = logging.getLogger(__name__)

HORIZONS_HOURS = [1, 24, 168]  # one hour, one day, one week


def track_outcomes(now: datetime | None = None) -> int:
    """Grades every prediction that's ready. Returns how many outcome rows were written."""
    now = now or datetime.now(tz=timezone.utc)
    provider = BinanceProvider()
    written = 0

    for horizon in HORIZONS_HOURS:
        pending = predictions_awaiting_outcome(horizon, now)
        for prediction_id, as_of, close_price in pending:
            target_hour = as_of + timedelta(hours=horizon)
            try:
                bar = provider.get_bar_at(target_hour)
            except Exception as exc:  # noqa: BLE001 -- leave it ungraded; a later run will retry
                logger.warning("Price lookup failed for prediction %s at %s: %s", prediction_id, target_hour, exc)
                continue
            if bar is None:
                continue
            pct_change = (bar.close - close_price) / close_price
            save_outcome(prediction_id, horizon, bar.close, pct_change)
            written += 1
            logger.info(
                "Prediction %s @ %s: %+.2f%% after %dh", prediction_id, as_of.isoformat(), pct_change * 100, horizon
            )

    return written


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = track_outcomes()
    print(f"Outcome rows written: {count}")
