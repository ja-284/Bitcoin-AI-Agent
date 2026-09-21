"""
Compute and store this hour's shadow move-size probability.

    python -m agent.shadow.run            # store (exits early if this hour already has a row)
    python -m agent.shadow.run --no-save  # compute and print only

Sequence: fetch 250 closed candles with trade/taker fields from Binance (one request) ->
reference hour = last closed candle, cutoff = its close -> features with the research code
-> frozen model -> row with everything needed to recompute it. If any input is missing
(a gap inside a window, a zero-trade candle) the row is stored as 'unavailable' with the
reason: an honest blank beats a filled-in number.

The live decision is never read for anything except one cross-check: that the live
prediction (if it exists yet) saw the same reference close.
"""

import argparse
import logging
import math
import os
from datetime import datetime, timedelta, timezone

from agent.data_providers.binance import BinanceProvider
from agent.data_providers.quality import validate_bars
from agent.shadow.features import WINDOW_HOURS, extras_frame, feature_row
from agent.shadow.model import DEFAULT_VERSION, MoveSizeModel, load_model
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)
HOUR = timedelta(hours=1)


def compute(model: MoveSizeModel, bars, extras_rows, fetched_at: datetime) -> dict:
    """Pure: candles + extras -> the row to store. No network, no database."""
    if not bars:
        raise ValueError("no candles")
    reference = bars[-1]
    quality = validate_bars(bars)
    values, reason = feature_row(bars, extras_frame(extras_rows), model.features)
    row = {
        "as_of": reference.as_of, "cutoff_at": reference.as_of + HOUR, "fetched_at": fetched_at,
        "model_version": model.version, "pipeline_version": PIPELINE_VERSION, "code_commit": os.environ.get("GITHUB_SHA"),
        "price_source": reference.source, "reference_close": reference.close, "live_close_match": None,
        "status": "ok", "status_reason": None, "features": values, "p_raw": None, "p_calibrated": None,
        "threshold": model.threshold, "horizon_hours": model.horizon_hours,
    }
    if fetched_at < row["cutoff_at"]:
        raise RuntimeError(f"fetched at {fetched_at} before the reference candle closed at {row['cutoff_at']}")
    if quality.gaps:
        reason = (reason + "; " if reason else "") + f"{len(quality.gaps)} gap(s) inside the window"
    if reason is None:
        pred = model.predict(values)
        if pred is None:
            reason = "model refused an input (non-positive value for a log-transformed feature)"
    if reason is not None:
        row["status"], row["status_reason"] = "unavailable", reason
        return row
    row["p_raw"], row["p_calibrated"] = pred
    return row


def run_once(save: bool = True, version: str = DEFAULT_VERSION) -> dict | None:
    model = load_model(version)
    fetched_at = datetime.now(tz=timezone.utc)
    bars, extras = BinanceProvider().get_hourly_klines_with_extras(WINDOW_HOURS)
    row = compute(model, bars, extras, fetched_at)
    if save:
        from agent.shadow.db import ensure_schema, live_close_for, save_shadow, shadow_exists

        ensure_schema()
        if shadow_exists(row["as_of"]):
            logger.info("Shadow row for %s already exists -- nothing to do", row["as_of"].isoformat())
            return None
        live_close = live_close_for(row["as_of"])
        row["live_close_match"] = None if live_close is None else bool(math.isclose(live_close, row["reference_close"], rel_tol=0, abs_tol=1e-9))
        if row["live_close_match"] is False:
            logger.warning("Reference close differs from the live prediction's: shadow %s vs live %s at %s", row["reference_close"], live_close, row["as_of"])
        new_id = save_shadow(row)
        if new_id is None:
            logger.info("Shadow row for %s was written by a concurrent run -- nothing to do", row["as_of"].isoformat())
            return None
        row["id"] = new_id
    logger.info("Shadow %s @ %s: status=%s p_cal=%s (raw %s) model=%s", row["as_of"].isoformat(), fetched_at.strftime("%H:%M:%S"),
                row["status"], None if row["p_calibrated"] is None else round(row["p_calibrated"], 4),
                None if row["p_raw"] is None else round(row["p_raw"], 4), model.version)
    return row


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = run_once(save=not args.no_save, version=args.version)
    if out is None:
        print("Shadow row for this hour already exists -- nothing to do.")
    else:
        print(f"as_of {out['as_of'].isoformat()} status {out['status']} p_calibrated {out['p_calibrated']} p_raw {out['p_raw']} "
              f"reason {out['status_reason']} live_close_match {out['live_close_match']}")
