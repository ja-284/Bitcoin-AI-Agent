"""
Backend Phase I: drift and regime monitoring -- does the live environment look like the
development data the model was fitted on?

Compared against frozen reference distributions (research/monitoring/reference_distributions_v1.json,
built once from the development period; never updated from live data):

  features       each of the model's nine raw inputs: median shift in units of the development
                 inter-quartile range, and the share of live values outside the development
                 1st-99th percentile band
  probabilities  the calibrated probability's distribution vs E013's out-of-sample validation
  outcomes       the live share of large moves vs development / validation
  missing data   the share of hours the shadow could not score
  behaviour      fetch delay after the candle close (the job's timing), by week

Flags are DESCRIPTIVE. A flag means "look", never "retrain": the model is frozen, and any
change is a new experiment on development data. Everything here is a pure function of rows.
"""

import json
from pathlib import Path

import numpy as np

REFERENCE_PATH = Path("research") / "monitoring" / "reference_distributions_v1.json"
MEDIAN_SHIFT_FLAG_IQR = 1.0  # live median more than one development IQR away from the development median
OUTSIDE_BAND_FLAG = 0.10  # more than 10% of live values outside the development 1-99% band (2% expected)
MIN_ROWS = 100  # below this, nothing is flagged: the numbers are shown as "too few"


def load_reference(path: Path = REFERENCE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _q(ref_q: list[float], quantiles: list[float], which: float) -> float:
    return ref_q[quantiles.index(which)]


def feature_drift(live_values: dict[str, list[float]], ref: dict) -> dict:
    """live_values: feature name -> live raw values (NaN/None removed by the caller)."""
    Q = ref["quantiles"]
    out = {}
    for name, spec in ref["features"].items():
        x = np.asarray([v for v in live_values.get(name, []) if v is not None and not np.isnan(v)], float)
        q1, q25, q50, q75, q99 = (_q(spec["q"], Q, w) for w in (0.01, 0.25, 0.5, 0.75, 0.99))
        iqr = q75 - q25
        d = {"n": int(len(x)), "dev_median": q50, "dev_iqr": iqr}
        if len(x) == 0:
            d["status"] = "no data"
            out[name] = d
            continue
        d["live_median"] = float(np.median(x))
        d["median_shift_iqr"] = float((d["live_median"] - q50) / iqr) if iqr > 0 else float("nan")
        d["share_outside_dev_1_99"] = float(np.mean((x < q1) | (x > q99)))
        if len(x) < MIN_ROWS:
            d["status"] = "too few rows to flag"
        elif abs(d["median_shift_iqr"]) > MEDIAN_SHIFT_FLAG_IQR or d["share_outside_dev_1_99"] > OUTSIDE_BAND_FLAG:
            d["status"] = "FLAG"
        else:
            d["status"] = "ok"
        out[name] = d
    return out


def probability_drift(p_live: list[float], ref: dict) -> dict:
    Q = ref["quantiles"]
    x = np.asarray([v for v in p_live if v is not None], float)
    spec = ref["p_calibrated"]
    d = {"n": int(len(x)), "dev_median": _q(spec["q"], Q, 0.5), "dev_q05_q95": [_q(spec["q"], Q, 0.05), _q(spec["q"], Q, 0.95)]}
    if len(x):
        d["live_median"] = float(np.median(x))
        d["live_q05_q95"] = [float(np.quantile(x, 0.05)), float(np.quantile(x, 0.95))]
        d["share_above_dev_q95"] = float(np.mean(x > d["dev_q05_q95"][1]))
        d["share_below_dev_q05"] = float(np.mean(x < d["dev_q05_q95"][0]))
        d["status"] = "too few rows to flag" if len(x) < MIN_ROWS else ("FLAG" if max(d["share_above_dev_q95"], d["share_below_dev_q05"]) > 0.20 else "ok")
    else:
        d["status"] = "no data"
    return d


def outcome_drift(large: list[bool], ref: dict) -> dict:
    y = np.asarray([1.0 if v else 0.0 for v in large if v is not None], float)
    d = {"n": int(len(y)), "dev_share": ref["large_move_share"]["dev"], "validation_share": ref["large_move_share"]["validation_2024_2025H1"]}
    if len(y):
        d["live_share"] = float(y.mean())
        se = float(np.sqrt(d["live_share"] * (1 - d["live_share"]) / len(y))) if len(y) else float("nan")
        d["live_share_ci95"] = [max(0.0, d["live_share"] - 1.96 * se), min(1.0, d["live_share"] + 1.96 * se)]
        d["status"] = "too few rows to flag" if len(y) < MIN_ROWS else ("FLAG" if not (d["live_share_ci95"][0] <= d["validation_share"] <= d["live_share_ci95"][1] or d["live_share_ci95"][0] <= d["dev_share"] <= d["live_share_ci95"][1]) else "ok")
    else:
        d["status"] = "no data"
    return d


def missing_and_timing(shadow_rows: list[dict], pred_rows: list[dict]) -> dict:
    n = len(shadow_rows)
    unavailable = sum(1 for r in shadow_rows if r.get("status") == "unavailable")
    delays = [(r["fetched_at"] - r["as_of"]).total_seconds() / 60 - 60 for r in pred_rows if r.get("fetched_at") and r.get("as_of")]
    by_week: dict[str, list[float]] = {}
    for r, dmin in zip(pred_rows, delays):
        wk = r["as_of"].strftime("%G-W%V")
        by_week.setdefault(wk, []).append(dmin)
    return {
        "shadow_unavailable_share": (unavailable / n) if n else None, "shadow_rows": n,
        "fetch_delay_by_week_median_min": {wk: float(np.median(v)) for wk, v in sorted(by_week.items())},
        "status": "too few rows to flag" if n < MIN_ROWS else ("FLAG" if unavailable / n > 0.05 else "ok"),
    }


def report(shadow_rows: list[dict], pred_rows: list[dict], ref: dict | None = None) -> dict:
    """shadow_rows need: status, features (dict), p_calibrated, outcome_status, outcome_large, as_of, fetched_at."""
    ref = ref or load_reference()
    ok_rows = [r for r in shadow_rows if r.get("status") == "ok" and r.get("features")]
    live_values = {name: [r["features"].get(name) for r in ok_rows] for name in ref["features"]}
    graded = [r for r in shadow_rows if r.get("outcome_status") == "ok"]
    out = {
        "reference": ref.get("built_from"),
        "features": feature_drift(live_values, ref),
        "probability": probability_drift([r.get("p_calibrated") for r in ok_rows], ref),
        "outcomes": outcome_drift([r.get("outcome_large") for r in graded], ref),
        "missing_and_timing": missing_and_timing(shadow_rows, pred_rows),
    }
    flags = [f"feature {k}" for k, v in out["features"].items() if v.get("status") == "FLAG"]
    flags += [k for k in ("probability", "outcomes", "missing_and_timing") if out[k].get("status") == "FLAG"]
    out["flags"] = flags
    out["note"] = "Flags are descriptive: investigate and document; never retrain or retune from them. Reference distributions are frozen."
    return out
