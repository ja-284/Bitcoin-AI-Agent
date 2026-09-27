"""
Pure, deterministic views over the records: no database, no clock, no randomness beyond the
registered fixed seeds. Every function takes the moment `at` it describes and, through `known_at`,
sees only what had been recorded by then.

Definitions are reused, never re-invented:
- the registered horizons are the outcome tracker's (`HORIZONS_HOURS`);
- a direction outcome is the registered binary label: UP if the return is > 0, else DOWN
  (agent/research/labels.py);
- which shadow hours count, and how they are scored, is the registered checkpoint's own code
  (`prospective`, `prospective_graded`, `core`, `_slice`, `regime_of`, `HOUR_BLOCKS`), so a running
  figure here cannot drift from the checkpoint -- while never being one;
- expected hours and "missing" use the weekly report's rule (`expected_hours`);
- staleness is agent/healthcheck's definition.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np

from agent.api.state import CONFIDENCE_MEANING, LIMITATIONS, MOVE_SIZE_MEANING, MOVE_SIZE_STATUS, SIGNAL_EVIDENCE, Quantity
from agent.healthcheck import check as staleness_check
from agent.outcome_tracker import HORIZONS_HOURS
from agent.reporting import NEVER_USE_FOR, REPORTING_CONTRACT_VERSION
from agent.reporting.source import Records
from agent.research.labels import DOWN, UP
from agent.research.live_checkpoint import BLOCK_HOURS, CHECKPOINTS, HOUR_BLOCKS, _slice, core, prospective, prospective_graded, regime_of
from agent.research.metrics import brier_score, wilson_interval
from agent.research.weekly_report import INTERVALS_NOMINAL_FROM_HOURS, expected_hours
from agent.version import PIPELINE_VERSION

HOUR = timedelta(hours=1)
# live_checkpoint.core computes block-bootstrap intervals only from 4 blocks of 48 hours (rule 3's 192 hours).
MIN_HOURS_FOR_INTERVALS = 4 * BLOCK_HOURS
BUCKET_MIN_ROWS = 100            # research/LIVE_EVALUATION.md rule 4: a calibration bucket counts from 100 rows
STALE_AFTER_HOURS = 2.0          # the same allowance the published state and the self-check use
PRIMARY_PRICE_SOURCE = "binance"
RECENT_GRADED_HOURS = 168        # "recent" = the last week of graded hours: a display window, not a regime
# The keys of `core()` that are safe to publish as descriptions. Its E013 pass flags are left out on
# purpose: at any running sample they would read as a verdict, and verdicts come only from the
# registered checkpoint readings.
CORE_DESCRIPTIVE_KEYS = ("n", "large_move_share", "mean_stated_p", "brier_rel_gain", "brier_rel_gain_ci95",
                         "accuracy", "accuracy_ci95", "naive_rate", "rho", "rho_ci95", "ece", "ece_ci95")


# ------------------------------------------------------------------ the leakage boundary
def known_at(records: Records, at: datetime) -> Records:
    """
    The records exactly as they stood at `at`: no row saved later, and no outcome checked later.

    Every view goes through this. A run saved at 10:12 whose 24-hour outcome was checked the next
    day at 10:12 shows that outcome only in views at or after that moment; before it, the outcome
    is pending. That is what "no leakage from future outcomes into an earlier run" means here.
    """
    preds = [p for p in records.predictions if p["created_at"] <= at]
    ids = {p["id"] for p in preds}
    outcomes = [o for o in records.outcomes if o["prediction_id"] in ids and o["checked_at"] <= at]
    shadow = []
    for s in records.shadow:
        if s["created_at"] > at:
            continue
        checked = s.get("outcome_checked_at")
        if checked is None or checked > at:
            s = {**s, "outcome_status": None, "outcome_return": None, "outcome_large": None, "outcome_checked_at": None}
        shadow.append(s)
    errors = [e for e in records.shadow_errors if e["occurred_at"] <= at]
    state = records.backend_state if records.backend_state and records.backend_state["generated_at"] <= at else None
    detail = records.run_detail if records.run_detail and records.run_detail["created_at"] <= at else None
    return Records(preds, outcomes, shadow, errors, state, records.schema_version, detail)


# ------------------------------------------------------------------ small helpers
def iso(t: datetime | None) -> str | None:
    return None if t is None else t.astimezone(timezone.utc).isoformat()


def _seconds(later: datetime, earlier: datetime) -> float:
    return round((later - earlier).total_seconds(), 1)


def _num(x) -> float | None:
    """A float, or None for anything that is not a finite number (JSON has no NaN)."""
    if x is None:
        return None
    x = float(x)
    return x if np.isfinite(x) else None


def sample_evidence(n: int) -> dict:
    """
    What a figure computed on `n` hours can and cannot say. Attached to every statistic, so that a
    small sample can never look like strong evidence, and no running figure can look like a verdict.
    """
    if n < MIN_HOURS_FOR_INTERVALS:
        level, intervals = "too_few_to_conclude", "not_computed"
        headline = (f"{n} hours: far too few to conclude anything. A description of what happened, "
                    f"not evidence of how the system behaves.")
    elif n < INTERVALS_NOMINAL_FROM_HOURS:
        level, intervals = "early_intervals_optimistic", "shown_but_too_narrow"
        headline = (f"{n} hours: intervals are shown, but below {INTERVALS_NOMINAL_FROM_HOURS:,} hours they are "
                    f"known to be too narrow (E025). Still descriptive, still not a verdict.")
    else:
        level, intervals = "enough_for_nominal_intervals", "nominal"
        headline = (f"{n} hours: intervals are at their nominal rate. A running figure is still not a verdict; "
                    f"only the registered checkpoint readings are.")
    return {"n": int(n), "level": level, "intervals": intervals, "is_verdict": False, "headline": headline}


def _outcome_state(as_of: datetime, horizon: int, row: dict | None, at: datetime, ret_key: str) -> dict:
    """graded / unavailable / pending (not due yet) / overdue (due, not recorded). Pure."""
    matures_at = as_of + timedelta(hours=horizon) + HOUR  # the target candle's close
    if row is not None and row["status"] == "ok":
        ret = float(row[ret_key])
        return {"state": "graded", "matured_at": iso(matures_at), "checked_at": iso(row["checked_at"]),
                "return": ret, "direction": UP if ret > 0 else DOWN}
    if row is not None:
        return {"state": "unavailable", "matured_at": iso(matures_at), "checked_at": iso(row["checked_at"]),
                "reason": "the target candle is missing from the exchange's history"}
    # due = one hour after the target candle closed (the tracker runs hourly); weekly_report.health's rule
    return {"state": "pending" if at < matures_at + HOUR else "overdue", "matures_at": iso(matures_at)}


# ------------------------------------------------------------------ runs
def _shadow_view(s: dict | None, at: datetime) -> dict:
    if s is None:
        return {"available": False, "reason": "no shadow row for this hour"}
    if s["status"] != "ok" or s["p_calibrated"] is None:
        return {"available": False, "reason": s.get("status_reason") or "no probability for this hour"}
    row = None
    if s["outcome_status"] is not None:
        row = {"status": s["outcome_status"], "checked_at": s["outcome_checked_at"], "ret": s["outcome_return"]}
    outcome = _outcome_state(s["as_of"], int(s["horizon_hours"]), row, at, "ret")
    if outcome["state"] == "graded":
        outcome["large_move"] = bool(s["outcome_large"])
    return {
        "available": True,
        "separate_from_signal": "research shadow model; it has never influenced the BUY/HOLD/SELL signal",
        "status": MOVE_SIZE_STATUS["status"],
        "model_version": s["model_version"],
        "horizon_hours": int(s["horizon_hours"]),
        "threshold_pct": round(float(s["threshold"]) * 100, 4),
        "probability": Quantity(_num(s["p_calibrated"]), "calibrated_probability", True, MOVE_SIZE_MEANING).as_dict(),
        "prospective": bool(prospective(s)),
        "outcome": outcome,
    }


def run_view(pred: dict, outcomes: dict[int, dict], shadow: dict | None, at: datetime, detail: dict | None = None) -> dict:
    """One hourly run: what was predicted, when, by which versions, how the run went, and what happened."""
    meta = pred.get("run_meta") or {}
    news_meta = meta.get("news") or {}
    news_error = bool(meta.get("news_error"))
    fallback = pred["price_source"] != PRIMARY_PRICE_SOURCE or bool(pred["price_is_synthetic"])
    problems = []
    if fallback:
        problems.append("price data came from the fallback source")
    if news_error:
        problems.append("the news step failed, so news was left out (weight 0), not counted as neutral")
    elif news_meta.get("sources_failed"):
        problems.append("%d news source(s) failed; the rest were used" % len(news_meta["sources_failed"]))
    if not pred["has_explanation"]:
        problems.append("no explanation was written")
    if pred["completeness_score"] < 1.0 and not news_error:
        problems.append("some analysis categories were unavailable")
    view = {
        "hour": iso(pred["as_of"]),
        "information_cutoff": iso(pred["cutoff_at"]),
        "data_fetched_at": iso(pred["fetched_at"]),
        "saved_at": iso(pred["created_at"]),
        "timing": {
            "start_lag_seconds": _seconds(pred["fetched_at"], pred["cutoff_at"]),
            "analysis_seconds": _seconds(pred["created_at"], pred["fetched_at"]),
            "job_wall_time_seconds": None,
            "note": ("start lag = candle close -> data fetched; analysis = data fetched -> row saved. The whole "
                     "GitHub job's duration is not stored in the database (see the Actions run)."),
        },
        "signal": {"value": pred["signal"], "evidence_status": SIGNAL_EVIDENCE["status"],
                   "evidence": SIGNAL_EVIDENCE["headline"]},
        "overall_score": Quantity(_num(pred["overall_score"]), "score", False,
                                  "The weighted combination of the category scores, from -1 to +1. A score, "
                                  "not a probability and not an expected return.").as_dict(),
        "confidence": Quantity(_num(pred["overall_confidence"]), "heuristic", False, CONFIDENCE_MEANING).as_dict()
        | {"components": {"agreement": _num(pred["agreement_score"]), "completeness": _num(pred["completeness_score"])}},
        "price": Quantity(_num(pred["close_price"]), "price", False,
                          "Bitcoin's closing price at the information cutoff, in US dollars.").as_dict(),
        "versions": {"pipeline": pred["pipeline_version"], "scoring": pred["scoring_version"],
                     "ai_news": pred["ai_model_news"], "ai_explanation": pred["ai_model_explanation"],
                     "code_commit": meta.get("code_commit")},
        "run": {
            "status": "ok" if not problems else "degraded",
            "problems": problems,
            "price_source": pred["price_source"],
            "fallback_used": fallback,
            "price_is_estimated": bool(pred["price_is_synthetic"]),
            "completeness": _num(pred["completeness_score"]),
            "news": {"available": pred["news_items_n"] > 0 and not news_error, "items_used": int(pred["news_items_n"]),
                     "error_type": meta.get("news_error_type") if news_error else None,
                     "sources_failed": list(news_meta.get("sources_failed") or [])},
            "explanation_available": bool(pred["has_explanation"]),
            "database_role": meta.get("db_role"),
        },
        "outcomes": {f"{h}h": _outcome_state(pred["as_of"], h, outcomes.get(h), at, "pct_change_from_prediction")
                     for h in HORIZONS_HOURS},
        "outcomes_note": ("Raw price change after the reference close, as a fraction (0.0044 = +0.44%), and its "
                          "direction by the registered binary rule (UP if > 0). Bitcoin drifts on its own: a rise "
                          "after a BUY is not evidence the signal worked."),
        "move_size": _shadow_view(shadow, at),
    }
    if detail is not None:
        view["explanation"] = detail.get("explanation")
        view["categories"] = [{"name": c.get("name"), "score": _num(c.get("score")), "weight": _num(c.get("weight")),
                               "is_independent": c.get("is_independent"), "available": bool(c.get("weight"))}
                              for c in (detail.get("category_scores") or [])]
    return view


def _indexes(known: Records) -> tuple[dict, dict]:
    by_pred: dict[int, dict[int, dict]] = {}
    for o in known.outcomes:
        by_pred.setdefault(o["prediction_id"], {})[o["horizon_hours"]] = o
    shadow = {s["as_of"]: s for s in known.shadow}
    return by_pred, shadow


def latest_run(records: Records, at: datetime) -> dict | None:
    known = known_at(records, at)
    if not known.predictions:
        return None
    pred = max(known.predictions, key=lambda p: p["as_of"])
    by_pred, shadow = _indexes(known)
    return run_view(pred, by_pred.get(pred["id"], {}), shadow.get(pred["as_of"]), at)


def recent_runs(records: Records, at: datetime, limit: int = 24, before: datetime | None = None) -> dict:
    """Newest first. `before` pages backwards: pass the oldest `hour` of the previous page."""
    known = known_at(records, at)
    by_pred, shadow = _indexes(known)
    preds = sorted((p for p in known.predictions if before is None or p["as_of"] < before),
                   key=lambda p: p["as_of"], reverse=True)
    page = preds[:max(0, int(limit))]
    return {"runs": [run_view(p, by_pred.get(p["id"], {}), shadow.get(p["as_of"]), at) for p in page],
            "returned": len(page), "total_runs": len(known.predictions),
            "next_before": iso(page[-1]["as_of"]) if len(preds) > len(page) else None}


def run_at(records: Records, at: datetime, hour: datetime) -> dict | None:
    known = known_at(records, at)
    pred = next((p for p in known.predictions if p["as_of"] == hour), None)
    if pred is None:
        return None
    by_pred, shadow = _indexes(known)
    return run_view(pred, by_pred.get(pred["id"], {}), shadow.get(hour), at, detail=known.run_detail)


# ------------------------------------------------------------------ direction signal statistics
def _return_summary(returns: list[float]) -> dict:
    n = len(returns)
    if n == 0:
        return {"sample": sample_evidence(0), "share_followed_by_a_rise": None}
    r = np.asarray(returns, float)
    ups = int((r > 0).sum())
    lo, hi = wilson_interval(ups, n)
    return {"sample": sample_evidence(n), "share_followed_by_a_rise": ups / n, "share_ci95": [_num(lo), _num(hi)],
            "mean_return": float(r.mean()), "median_return": float(np.median(r))}


def signal_statistics(records: Records, at: datetime) -> dict:
    """
    Descriptive statistics of the BUY/HOLD/SELL record. Not trading performance, not evidence of skill:
    the signal has no demonstrated predictive value, and this does not test it.
    """
    known = known_at(records, at)
    rows = sorted((p for p in known.predictions if p["pipeline_version"] == PIPELINE_VERSION), key=lambda p: p["as_of"])
    by_pred, _ = _indexes(known)
    out = {
        "evidence": SIGNAL_EVIDENCE,
        "what_this_is": ("How often each signal was followed by a rise, next to how often ALL hours were. A signal "
                         "that looks different from 'all hours' on a small sample is still no evidence; the signal was "
                         "tested on 68,619 historical hours and showed none (E001, E017)."),
        "population": {"runs": len(rows), "pipeline_version": PIPELINE_VERSION,
                       "excluded_older_pipeline_runs": sum(1 for p in known.predictions if p["pipeline_version"] != PIPELINE_VERSION),
                       "scoring_versions": dict(Counter(p["scoring_version"] for p in rows))},
        "signal_counts": {s: sum(1 for p in rows if p["signal"] == s) for s in ("BUY", "HOLD", "SELL")},
        "confidence": {"kind": "heuristic", "is_probability": False, "meaning": CONFIDENCE_MEANING,
                       "mean": _num(np.mean([p["overall_confidence"] for p in rows])) if rows else None,
                       "note": "Not a probability, so no calibration or Brier score is computed for it."},
        "by_horizon": {},
    }
    for h in HORIZONS_HOURS:
        groups = {g: {"graded": [], "pending": 0, "overdue": 0, "unavailable": 0} for g in ("BUY", "HOLD", "SELL", "ALL")}
        for p in rows:
            st = _outcome_state(p["as_of"], h, by_pred.get(p["id"], {}).get(h), at, "pct_change_from_prediction")
            for g in (p["signal"], "ALL"):
                if st["state"] == "graded":
                    groups[g]["graded"].append(st["return"])
                else:
                    groups[g][st["state"]] += 1
        out["by_horizon"][f"{h}h"] = {
            g: {"graded": len(v["graded"]), "pending": v["pending"], "overdue": v["overdue"], "unavailable": v["unavailable"]}
            | _return_summary(v["graded"]) for g, v in groups.items()}
    return out


# ------------------------------------------------------------------ the shadow move-size model
def _descriptive_core(p: np.ndarray, y: np.ndarray, size: np.ndarray) -> dict:
    s = core(p, y, size)
    d = {k: s[k] for k in CORE_DESCRIPTIVE_KEYS if k in s}
    d["brier"] = brier_score(p, y)
    d["brier_of_the_observed_rate"] = brier_score(np.full(len(y), y.mean()), y)
    d["calibration_bins"] = [{"from": b["from"], "to": b["to"], "n": b["n"], "stated": b["stated"],
                              "observed": b["observed"], "observed_ci95": b["ci95"],
                              "enough_rows": b["n"] >= BUCKET_MIN_ROWS} for b in s["buckets"]]
    return d


def checkpoint_progress(n_graded: int, at: datetime, computed: dict[int, str] | None = None) -> dict:
    """Where the prospective record stands against the registered checkpoints. Counts; never evaluates."""
    nxt = next((c for c in CHECKPOINTS if n_graded < c), None)
    remaining = (nxt - n_graded) if nxt else None
    return {
        "prospective_graded_hours": int(n_graded),
        "selection_rule": ("the registered checkpoint's own selection (agent/research/live_checkpoint.prospective_graded): "
                           "status ok, outcome ok, probability stored before the outcome candle closed"),
        "next_checkpoint_hours": nxt,
        "hours_remaining": remaining,
        "expected_around": iso(at + timedelta(hours=remaining)) if remaining else None,
        "eta_assumption": "one graded hour per hour from now, none lost; the newest hour is graded about an hour after it closes",
        "reached": [c for c in CHECKPOINTS if n_graded >= c],
        "computed_readings": {str(k): v for k, v in sorted((computed or {}).items())},
        "what_each_gives": {"500": "first look, no verdict", "2000": "E012 verdict", "5000": "E013 verdict"},
        "rule": ("A checkpoint reads exactly the first N prospective graded hours (research/LIVE_EVALUATION.md rule 8). "
                 "The running figures in this report cover every graded hour known at the time and are never a checkpoint."),
    }


def move_size_statistics(records: Records, at: datetime, computed: dict[int, str] | None = None) -> dict:
    known = known_at(records, at)
    rows = sorted(known.shadow, key=lambda s: s["as_of"])
    graded = prospective_graded(rows)
    states = Counter()
    for s in rows:
        if s["status"] != "ok":
            states["no_probability"] += 1
        elif s["outcome_status"] == "ok":
            states["graded"] += 1
        elif s["outcome_status"] == "unavailable":
            states["outcome_unavailable"] += 1
        else:
            states[_outcome_state(s["as_of"], int(s["horizon_hours"]), None, at, "ret")["state"]] += 1
    out = {
        "what_this_is": ("The research shadow model's stated chance of a move larger than the threshold in the next "
                         "hour, against what happened. Separate from the BUY/HOLD/SELL signal, which it never influences."),
        "status": MOVE_SIZE_STATUS,
        "probability_meaning": MOVE_SIZE_MEANING,
        "rows": len(rows),
        "row_states": {k: states.get(k, 0) for k in ("graded", "pending", "overdue", "outcome_unavailable", "no_probability")},
        "not_prospective": sum(1 for s in rows if not prospective(s)),
        "model_versions": dict(Counter(s["model_version"] for s in rows)),
        "sample": sample_evidence(len(graded)),
        "checkpoint_progress": checkpoint_progress(len(graded), at, computed),
    }
    if graded:
        p = np.array([s["p_calibrated"] for s in graded], float)
        y = np.array([1.0 if s["outcome_large"] else 0.0 for s in graded])
        size = np.abs(np.array([s["outcome_return"] for s in graded], float))
        out["running_figures"] = _descriptive_core(p, y, size)
        out["running_figures"]["note"] = ("Every prospective graded hour known at this moment. Descriptive; the registered "
                                          "readings are the checkpoint files, and the only verdicts are at 2,000 (E012) "
                                          "and 5,000 (E013) hours.")
    return out


def move_size_breakdowns(records: Records, at: datetime, terciles: tuple[float, float] | None) -> dict:
    """Descriptive slices, with the definitions the registered checkpoints use. Never an input to anything."""
    graded = prospective_graded(known_at(records, at).shadow)
    if not graded:
        return {"sample": sample_evidence(0)}
    p = np.array([s["p_calibrated"] for s in graded], float)
    y = np.array([1.0 if s["outcome_large"] else 0.0 for s in graded])
    size = np.abs(np.array([s["outcome_return"] for s in graded], float))
    recent_from = graded[-RECENT_GRADED_HOURS]["as_of"] if len(graded) > RECENT_GRADED_HOURS else graded[0]["as_of"]
    slices = {
        "hour_block_utc": _slice(graded, p, y, size, lambda r: next(f"{a:02d}-{b:02d}" for a, b in HOUR_BLOCKS if a <= r["as_of"].hour < b)),
        "weekday_weekend": _slice(graded, p, y, size, lambda r: "weekend" if r["as_of"].weekday() >= 5 else "weekday"),
        "recent_vs_earlier": _slice(graded, p, y, size,
                                    lambda r: f"last_{RECENT_GRADED_HOURS}_graded_hours" if r["as_of"] >= recent_from else "earlier"),
    }
    if terciles is not None:
        slices["volatility_regime_168h"] = _slice(graded, p, y, size, lambda r: regime_of(r, terciles))
    for groups in slices.values():
        for g in groups.values():
            g["sample"] = sample_evidence(g["n"])
            for k in ("brier_rel_gain", "ece", "large_move_share", "mean_stated_p"):
                g[k] = _num(g.get(k))
    return {
        "slices": slices,
        "definitions": {
            "hour_block_utc": "the reference hour's six-hour UTC block (the registered 2,000-hour slice)",
            "weekday_weekend": "Saturday/Sunday UTC vs other days (the registered 2,000-hour slice)",
            "volatility_regime_168h": ("realised volatility of the previous 168 h against terciles frozen on development "
                                       "data (research/monitoring/regime_terciles_v1.json; the registered 5,000-hour slice)"),
            "recent_vs_earlier": f"the last {RECENT_GRADED_HOURS} graded hours against all earlier ones (a display window, not a regime)",
        },
        "reading_note": ("Descriptive only; never an input to any model or rule. Hour blocks are read against the model "
                         "family's known development offsets (E027: nights over-stated, the US session under-stated), not "
                         "against zero, and a few weeks of calibration drift is ordinary for this family (E029)."),
    }


# ------------------------------------------------------------------ system health
def _window_counts(preds: list[dict], missing: list[datetime], since: datetime | None) -> dict:
    rows = [p for p in preds if since is None or p["as_of"] >= since]
    miss = [m for m in missing if since is None or m >= since]
    metas = [p.get("run_meta") or {} for p in rows]
    lags = [(p["fetched_at"] - p["cutoff_at"]).total_seconds() for p in rows]
    analysis = [(p["created_at"] - p["fetched_at"]).total_seconds() for p in rows]
    return {
        "runs": len(rows), "missing_hours": len(miss),
        "fallback_price_runs": sum(1 for p in rows if p["price_source"] != PRIMARY_PRICE_SOURCE or p["price_is_synthetic"]),
        "news_unavailable_runs": sum(1 for m in metas if m.get("news_error")),
        "news_partial_runs": sum(1 for m in metas if not m.get("news_error") and (m.get("news") or {}).get("sources_failed")),
        "explanation_unavailable_runs": sum(1 for p in rows if not p["has_explanation"]),
        "start_lag_seconds": {"median": _num(np.median(lags)) if lags else None, "max": _num(max(lags)) if lags else None},
        "analysis_seconds": {"median": _num(np.median(analysis)) if analysis else None, "max": _num(max(analysis)) if analysis else None},
    }


def health(records: Records, at: datetime, computed: dict[int, str] | None = None) -> dict:
    known = known_at(records, at)
    preds = sorted(known.predictions, key=lambda p: p["as_of"])
    external = {
        "heartbeat": {"observable_here": False, "where": "the healthchecks.io dashboard (it emails when pings stop)"},
        "watchdog": {"observable_here": False, "where": "GitHub -> Actions -> Watchdog (a failed run emails the owner)"},
        "job_wall_time": {"observable_here": False, "where": "GitHub -> Actions -> the hourly run"},
    }
    if not preds:
        return {"status": "no_data", "problems": ["no prediction has been stored"], "external": external}
    latest = preds[-1]
    fresh, staleness = staleness_check(STALE_AFTER_HOURS, now=at, latest=latest["as_of"])
    missing = [t for t in expected_hours(preds[0]["as_of"], at) if t not in {p["as_of"] for p in preds}]
    by_pred, shadow_by_hour = _indexes(known)
    overdue, anomalies, unregistered = Counter(), 0, 0
    for p in preds:
        for h, o in by_pred.get(p["id"], {}).items():
            if h not in HORIZONS_HOURS:
                unregistered += 1
            elif o["checked_at"] < p["as_of"] + timedelta(hours=h) + HOUR:
                anomalies += 1  # graded before its target candle closed: must never happen
        for h in HORIZONS_HOURS:
            if h not in by_pred.get(p["id"], {}) and _outcome_state(p["as_of"], h, None, at, "")["state"] == "overdue":
                overdue[f"{h}h"] += 1
    first_shadow = min(shadow_by_hour) if shadow_by_hour else None
    shadow_missing = [p["as_of"] for p in preds if first_shadow and p["as_of"] >= first_shadow and p["as_of"] not in shadow_by_hour]
    errors = known.shadow_errors
    windows = {"last_24h": _window_counts(preds, missing, at - timedelta(hours=24)),
               "last_7d": _window_counts(preds, missing, at - timedelta(days=7)),
               "all_time": _window_counts(preds, missing, None)}
    problems = []
    if not fresh:
        problems.append(staleness)
    for key, text in (("missing_hours", "hour(s) missing"), ("fallback_price_runs", "run(s) on fallback price data"),
                      ("news_unavailable_runs", "run(s) without news"), ("explanation_unavailable_runs", "run(s) without an explanation")):
        if windows["last_24h"][key]:
            problems.append(f"{windows['last_24h'][key]} {text} in the last 24 hours")
    recent_errors = [e for e in errors if e["occurred_at"] > at - timedelta(hours=24)]
    if recent_errors:
        problems.append(f"{len(recent_errors)} research shadow error(s) in the last 24 hours (the live record is unaffected)")
    if sum(overdue.values()):
        problems.append(f"{sum(overdue.values())} outcome(s) overdue")
    if anomalies or unregistered:
        problems.append("outcome records that break the grading rules (see outcomes)")
    n_graded = len(prospective_graded(known.shadow))
    state = known.backend_state
    return {
        "status": "stale" if not fresh else ("ok" if not problems else "degraded"),
        "problems": problems,
        "last_run": {"hour": iso(latest["as_of"]), "saved_at": iso(latest["created_at"]), "freshness": staleness,
                     "database_role": (latest.get("run_meta") or {}).get("db_role"),
                     "code_commit": (latest.get("run_meta") or {}).get("code_commit")},
        "windows": windows,
        "missing_hours_all_time": [iso(t) for t in missing],
        "missing_note": "Missing hours are never backfilled; the ones on go-live weekend (2026-09-19/20) are documented and permanent.",
        "outcomes": {"overdue_by_horizon": dict(overdue), "graded_before_their_candle_closed": anomalies,
                     "rows_for_unregistered_horizons": unregistered, "registered_horizons_hours": list(HORIZONS_HOURS)},
        "shadow": {"rows": len(known.shadow), "hours_without_a_shadow_row": len(shadow_missing),
                   "errors_total": len(errors), "errors_last_24h": len(recent_errors),
                   "latest_error": ({"occurred_at": iso(errors[-1]["occurred_at"]), "step": errors[-1]["step"],
                                     "error_type": errors[-1]["error_type"]} if errors else None),
                   "note": "Error messages are kept in the database for diagnosis and deliberately not published here."},
        "published_state": ({"contract_version": state["contract_version"], "generated_at": iso(state["generated_at"]),
                             "age_hours": round((at - state["generated_at"]).total_seconds() / 3600, 2)}
                            if state else {"available": False, "reason": "no published snapshot known at this time"}),
        "schema_version": known.schema_version,
        "external": external,
        "checkpoint_progress": checkpoint_progress(n_graded, at, computed),
    }


# ------------------------------------------------------------------ the document
def clean(x):
    """JSON-safe and deterministic: numpy scalars to Python, datetimes to ISO strings, NaN/inf to None."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, datetime):
        return iso(x)
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return _num(x)
    return x


def document(kind: str, body, at: datetime, generated_at: datetime) -> dict:
    """The envelope every reporting output travels in."""
    return clean({
        "reporting_contract_version": REPORTING_CONTRACT_VERSION,
        "kind": kind,
        "as_known_at": at,
        "generated_at": generated_at,
        "read_only": True,
        "descriptive_only": True,
        "never_use_for": list(NEVER_USE_FOR),
        "limitations": LIMITATIONS,
        "body": body,
    })


def report(records: Records, at: datetime, terciles: tuple[float, float] | None = None,
           computed: dict[int, str] | None = None) -> dict:
    """Everything except the full run history: latest run, statistics, breakdowns and health."""
    return {"latest_run": latest_run(records, at), "signal_statistics": signal_statistics(records, at),
            "move_size_statistics": move_size_statistics(records, at, computed),
            "move_size_breakdowns": move_size_breakdowns(records, at, terciles), "health": health(records, at, computed)}
