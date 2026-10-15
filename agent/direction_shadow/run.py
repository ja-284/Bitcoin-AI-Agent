"""
Compute and store this hour's direction probabilities (E034, research/DIRECTION_TRACK.md).

    python -m agent.direction_shadow.run            # store (exits early if this hour already has a row)
    python -m agent.direction_shadow.run --no-save  # compute and print only

Sequence: ONE Binance request for the 250 most recent closed candles with their trade and taker-buy fields, plus the
still-open target candle -> reference hour = the last closed candle, cutoff = its close -> the eight inputs with the
research code -> the frozen artefact's three probabilities -> a row with everything needed to recompute them. If any
input is missing, the row is stored 'unavailable' with the reason and no probability: an honest blank beats a
filled-in number.

The still-open candle's last price is stored as price_at_prediction for the descriptive economics. It is NEVER an
input: the inputs are computed from the closed candles alone, before it is even looked at.

The live decision is read for two cross-checks only (the reference close and the four category scores). Nothing here
can change it.
"""

import argparse
import logging
import math
import os
import sys
from datetime import datetime, timedelta, timezone

from agent.data_providers import binance
from agent.data_providers.quality import validate_bars
from agent.direction_shadow.features import CATEGORY_INPUTS, WINDOW_HOURS, input_row
from agent.direction_shadow.model import DEFAULT_VERSION, DirectionModel, load_model
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)
HOUR = timedelta(hours=1)


def fetch(count: int = WINDOW_HOURS):
    """
    (closed candles, their extras, the still-open candles as [(open time, last price)], fetched_at). One request, one
    consistent view. The closed candles and extras are built exactly as BinanceProvider.get_hourly_klines_with_extras
    builds them (a test feeds both the same payload); the open candles are set aside, never mixed in.
    """
    params = {"symbol": binance.SYMBOL, "interval": "1h", "limit": count + 1}
    fetched_at = datetime.now(tz=timezone.utc)
    now_ms = fetched_at.timestamp() * 1000
    payload = binance._get_klines(params)
    raw = [k for k in payload if k[6] <= now_ms][-count:]
    bars = binance._to_bars(raw, now_ms)
    extras = [(datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc), float(k[5]), int(k[8]), float(k[9])) for k in raw]
    still_open = [(datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc), float(k[4])) for k in payload if k[6] > now_ms]
    return bars, extras, still_open, fetched_at


def compute(model: DirectionModel, bars, extras_rows, open_candles, fetched_at: datetime, scoring_version: str) -> dict:
    """Pure: candles + extras (+ the open candle's price, set aside) -> the row to store. No network, no database."""
    if not bars:
        raise ValueError("no candles")
    reference = bars[-1]
    cutoff = reference.as_of + HOUR
    if fetched_at < cutoff:
        raise RuntimeError(f"fetched at {fetched_at} before the reference candle closed at {cutoff}")
    values, rv_168, reason = input_row(bars, extras_rows)  # the closed candles only
    quality = validate_bars(bars)
    if quality.gaps:
        reason = (reason + "; " if reason else "") + f"{len(quality.gaps)} gap(s) inside the window"
    if scoring_version != model.scoring_version:
        reason = (reason + "; " if reason else "") + f"scoring {scoring_version} is running; {model.version} needs {model.scoring_version}"
    # the target candle itself (it opened at the cutoff), nothing else; looked at only after the inputs are computed
    price_at_prediction = next((price for opened, price in open_candles if opened == cutoff), None)
    row = {
        "as_of": reference.as_of, "cutoff_at": cutoff, "fetched_at": fetched_at,
        "model_version": model.version, "artefact_sha256": model.sha256, "pipeline_version": PIPELINE_VERSION,
        "scoring_version": scoring_version, "code_commit": os.environ.get("GITHUB_SHA"), "price_source": reference.source,
        "reference_close": reference.close, "price_at_prediction": price_at_prediction,
        "live_close_match": None, "live_scores_match": None, "status": "ok", "status_reason": None,
        "features": values or None, "regime_rv_168": rv_168, "p_model": None, "p_one_feature": None, "p_base": None,
        "horizon_hours": model.horizon_hours,
    }
    if reason is None:
        pred = model.predict(values)
        if pred is None:
            reason = "model refused an input"
    if reason is not None:
        row["status"], row["status_reason"] = "unavailable", reason
        return row
    row["p_model"], row["p_one_feature"], row["p_base"] = pred
    return row


def cross_check(row: dict, live: tuple[float, dict] | None) -> None:
    """Fill live_close_match / live_scores_match from the live prediction for the same hour (read-only parity)."""
    if live is None:
        return
    close, scores = live
    row["live_close_match"] = bool(math.isclose(close, row["reference_close"], rel_tol=0, abs_tol=1e-9))
    mine = row.get("features") or {}
    if all(mine.get(k) is not None and k in scores for k in CATEGORY_INPUTS):
        row["live_scores_match"] = all(math.isclose(scores[k], mine[k], rel_tol=1e-9, abs_tol=1e-12) for k in CATEGORY_INPUTS)


class DirectionRunError(RuntimeError):
    """An operational failure, carrying the stage it happened in so it can be recorded usefully."""

    def __init__(self, step: str, cause: BaseException):
        super().__init__(f"{step}: {type(cause).__name__}: {cause}")
        self.step, self.cause = step, cause


def run_once(save: bool = True, version: str = DEFAULT_VERSION) -> dict | None:
    from agent.scoring.scorer import SCORING_VERSION

    step = "load_model"
    try:
        model = load_model(version)
        step = "fetch"
        bars, extras, open_candles, fetched_at = fetch()
        step = "compute"
        row = compute(model, bars, extras, open_candles, fetched_at, SCORING_VERSION)
    except Exception as exc:  # noqa: BLE001 -- re-raised with the stage attached
        raise DirectionRunError(step, exc) from exc
    if save:
        from agent.direction_shadow.db import live_reference_for, row_exists, save_row

        try:
            if row_exists(row["as_of"]):
                logger.info("Direction row for %s already exists -- nothing to do", row["as_of"].isoformat())
                return None
            cross_check(row, live_reference_for(row["as_of"]))
            for k in ("live_close_match", "live_scores_match"):
                if row[k] is False:
                    logger.warning("Direction %s: %s is False at %s", row["as_of"].isoformat(), k, row["as_of"])
            new_id = save_row(row)
        except Exception as exc:  # noqa: BLE001
            raise DirectionRunError("save", exc) from exc
        if new_id is None:
            logger.info("Direction row for %s was written by a concurrent run -- nothing to do", row["as_of"].isoformat())
            return None
        row["id"] = new_id
    logger.info("Direction %s @ %s: status=%s p_model=%s p_one=%s p_base=%s", row["as_of"].isoformat(), fetched_at.strftime("%H:%M:%S"),
                row["status"], *(None if row[k] is None else round(row[k], 4) for k in ("p_model", "p_one_feature", "p_base")))
    return row


def record_failure(exc: BaseException, version: str) -> int:
    """Record a failure in shadow_direction_errors and return 0; return 1 only if even that fails (then it is invisible)."""
    from agent.data_providers.market_data import expected_last_closed
    from agent.direction_shadow.db import save_run_error

    step = getattr(exc, "step", "run")
    cause = getattr(exc, "cause", exc)
    logger.error("Direction step failed at %s: %s: %s", step, type(cause).__name__, cause)
    try:
        save_run_error({
            "expected_as_of": expected_last_closed(datetime.now(tz=timezone.utc)),
            "step": step, "error_type": type(cause).__name__, "error_message": str(cause)[:4000],
            "model_version": version, "pipeline_version": PIPELINE_VERSION, "code_commit": os.environ.get("GITHUB_SHA"),
        })
        logger.error("Recorded in shadow_direction_errors; the live record is unaffected.")
        return 0
    except Exception as record_exc:  # noqa: BLE001
        logger.error("Could not even record the failure (%s) -- failing the step so it is visible", record_exc)
        return 1


def run_and_record(version: str = DEFAULT_VERSION) -> int:
    """
    The entry point the hourly job uses. A failure of this research track is RECORDED, not crashed on: the live
    prediction was already saved, self-checked and published by earlier steps (incident 2026-09-21/22: an add-on must
    never be able to drag the job red every hour). If even the recording fails, it exits 1, so it is still seen.
    """
    try:
        run_once(save=True, version=version)
        return 0
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: the point is to record anything
        return record_failure(exc, version)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--raise-errors", action="store_true", help="do not record failures; let them propagate (local debugging)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.no_save and not args.raise_errors:
        sys.exit(run_and_record(version=args.version))
    out = run_once(save=not args.no_save, version=args.version)
    if out is None:
        print("Direction row for this hour already exists -- nothing to do.")
    else:
        print(f"as_of {out['as_of'].isoformat()} status {out['status']} p_model {out['p_model']} p_one {out['p_one_feature']} "
              f"p_base {out['p_base']} price_at_prediction {out['price_at_prediction']} reason {out['status_reason']}")
