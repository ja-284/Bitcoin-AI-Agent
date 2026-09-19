"""
Grades past predictions against what the price actually did afterwards, at a few
fixed time horizons. This is the raw material for checking, later on, whether the
confidence numbers mean anything (CLAUDE.md rule 6) -- so it records prices and
returns only, and deliberately does NOT decide whether a signal was "right". That
judgement (which horizon matters, what counts as a win, how to compare against
plain buy-and-hold) belongs to a later analysis step, not to an hourly job.

Timing rules, stated once:
- A prediction's reference candle opens at `as_of` and closes at `as_of + 1h` (the
  information cutoff; the reference price is that close).
- The outcome for horizon H is the close of the candle that OPENS at `as_of + H`,
  i.e. the price H hours after the cutoff. It can only be graded once that candle has
  closed: `now >= as_of + H + 1h`. The database query enforces this; the same guard
  is repeated here so a change to one can't silently break the other.
- If the target candle does not exist (exchange downtime), the outcome is recorded as
  'unavailable' -- never the nearest candle that happens to exist. To tell "missing"
  from "API hiccup", a candle is only declared unavailable after a grace period.

Runs after each hourly analysis. It's never urgent: if a price lookup fails, the
prediction stays ungraded and is picked up on a later run.

    python -m agent.outcome_tracker
"""

import logging
from datetime import datetime, timedelta, timezone

from agent.data_providers.binance import BinanceProvider
from agent.database.db import predictions_awaiting_outcome, save_outcome, save_outcome_unavailable

logger = logging.getLogger(__name__)

HORIZONS_HOURS = [1, 6, 24, 72, 168]
UNAVAILABLE_GRACE = timedelta(hours=6)  # how long after the target candle should have closed before calling it missing
HOUR = timedelta(hours=1)


def target_candle_open(as_of: datetime, horizon_hours: int) -> datetime:
    return as_of + timedelta(hours=horizon_hours)


def is_gradeable(as_of: datetime, horizon_hours: int, now: datetime) -> bool:
    return now >= target_candle_open(as_of, horizon_hours) + HOUR


def track_outcomes(now: datetime | None = None, provider: BinanceProvider | None = None) -> dict:
    """Grades every prediction that's ready. Returns counts of what happened."""
    now = now or datetime.now(tz=timezone.utc)
    provider = provider or BinanceProvider()
    counts = {"graded": 0, "unavailable": 0, "deferred": 0, "errors": 0}

    for horizon in HORIZONS_HOURS:
        for prediction_id, as_of, close_price in predictions_awaiting_outcome(horizon, now):
            if not is_gradeable(as_of, horizon, now):
                counts["deferred"] += 1  # the query should never hand us this; the guard is belt-and-braces
                continue
            target_open = target_candle_open(as_of, horizon)
            try:
                bar = provider.get_bar_at(target_open)
            except Exception as exc:  # noqa: BLE001 -- leave it ungraded; a later run will retry
                logger.warning("Price lookup failed for prediction %s at %s: %s", prediction_id, target_open, exc)
                counts["errors"] += 1
                continue

            if bar is None:
                if now >= target_open + HOUR + UNAVAILABLE_GRACE:
                    save_outcome_unavailable(prediction_id, horizon)
                    counts["unavailable"] += 1
                    logger.warning("Prediction %s: no candle at %s (%dh) -- recorded as unavailable", prediction_id, target_open, horizon)
                else:
                    counts["deferred"] += 1
                continue

            if bar.as_of != target_open:
                raise RuntimeError(f"provider returned candle {bar.as_of} for requested {target_open}")
            pct_change = (bar.close - close_price) / close_price
            save_outcome(prediction_id, horizon, bar.close, pct_change)
            counts["graded"] += 1
            logger.info("Prediction %s @ %s: %+.2f%% after %dh", prediction_id, as_of.isoformat(), pct_change * 100, horizon)

    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print("Outcome tracker:", track_outcomes())
