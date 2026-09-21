"""
Phase 13: the weekly live-monitoring report.

Reads the live database (predictions + outcomes) and writes one Markdown + JSON report to
research/monitoring/. It never writes to the live tables and never changes the live system.

Sections
  1. Health      did every hour run, how late, on which data source, with which errors,
                 and is outcome tracking keeping up
  2. Signal      the live record of scoring 0.1.0 (the thing under test): signal mix, acted
                 accuracy vs the naive rate, return edge with a block-bootstrap interval once
                 there are enough hours, and whether the stated confidence means anything yet
  3. Shadow      the LIVE shadow record (agent/shadow): probabilities stored before their
                 outcomes existed, plus coverage, honest blanks and the close cross-check
  3b. Paper      the same model scored AFTER THE FACT on all live hours from point-in-time
                 candle features -- covers hours before the shadow existed; labelled as such
  4. Watch list  how far the live record is from the thresholds that re-open deferred tests

Everything that computes is a pure function of rows, so it is unit-tested on synthetic rows
(tests/test_weekly_report.py); only fetch_* touch the database or the exchange.
"""

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.metrics import block_bootstrap, brier_score, reliability_table, signal_edge, wilson_interval
from agent.research.periods import LIVE
from agent.scoring.scorer import SCORING_VERSION
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

HORIZONS = [1, 6, 24, 72, 168]
HOUR = timedelta(hours=1)
OUT_DIR = Path("research") / "monitoring"
N_BOOT = 500
NEWS_HOURS_FOR_8_6 = 500  # roadmap 8.6 re-opens at this many live hours with news
MONTHS_FOR_WATCHLIST = 6  # funding / dollar-yield confirmatory re-tests


# ---------------------------------------------------------------- 1. health
def expected_hours(start: datetime, now: datetime, run_minute: int = 12, allowance_min: int = 10) -> list[datetime]:
    """Reference hours that should have a prediction by `now`: a run at :12 writes as_of = previous hour."""
    last_closed = now.replace(minute=0, second=0, microsecond=0) - HOUR
    if now.minute < run_minute + allowance_min:
        last_closed -= HOUR  # this hour's run may legitimately still be in progress
    hours, t = [], start
    while t <= last_closed:
        hours.append(t)
        t += HOUR
    return hours


def health(pred_rows: list[dict], outcome_rows: list[dict], now: datetime, since: datetime) -> dict:
    """pred_rows: dicts with as_of, fetched_at, cutoff_at, pipeline_version, price_source, price_is_synthetic,
    run_meta, news_items_n, has_explanation. outcome_rows: dicts with prediction_as_of, horizon_hours, status."""
    rows = [r for r in pred_rows if r["as_of"] >= since]
    got = {r["as_of"] for r in rows}
    expected = expected_hours(since, now)
    missing = [t for t in expected if t not in got]
    delays = [(r["fetched_at"] - r["as_of"] - HOUR).total_seconds() / 60 for r in rows]
    invariant_violations = [r["as_of"] for r in rows if r["cutoff_at"] != r["as_of"] + HOUR or r["fetched_at"] < r["cutoff_at"]]
    errors = Counter()
    for r in rows:
        meta = r.get("run_meta") or {}
        for key in ("news_error", "explanation_error"):
            if meta.get(key):
                errors[key] += 1
    outcome_cov = {}
    for h in HORIZONS:
        due = [r for r in rows if r["as_of"] + timedelta(hours=h) + 2 * HOUR < now]  # target candle closed + 1h grace
        graded = {o["prediction_as_of"]: o["status"] for o in outcome_rows if o["horizon_hours"] == h}
        ok = sum(1 for r in due if graded.get(r["as_of"]) == "ok")
        unavailable = sum(1 for r in due if graded.get(r["as_of"]) == "unavailable")
        outcome_cov[f"{h}h"] = {"due": len(due), "ok": ok, "unavailable": unavailable, "overdue": len(due) - ok - unavailable}
    return {
        "since": since.isoformat(), "now": now.isoformat(),
        "expected_hours": len(expected), "predictions": len(rows), "missing_hours": [t.isoformat() for t in missing],
        "fetch_delay_min": {"min": min(delays) if delays else None, "median": float(np.median(delays)) if delays else None, "max": max(delays) if delays else None},
        "price_sources": dict(Counter(r["price_source"] for r in rows)), "synthetic_rows": sum(1 for r in rows if r["price_is_synthetic"]),
        "pipeline_versions": dict(Counter(r["pipeline_version"] for r in rows)),
        "rows_without_explanation": sum(1 for r in rows if not r["has_explanation"]),
        "rows_with_zero_news": sum(1 for r in rows if r["news_items_n"] == 0),
        "mean_news_items": float(np.mean([r["news_items_n"] for r in rows])) if rows else None,
        "run_errors": dict(errors), "timestamp_rule_violations": [t.isoformat() for t in invariant_violations],
        "outcome_coverage": outcome_cov,
    }


# ---------------------------------------------------------------- 2. signal record (scoring 0.1.0)
def signal_record(pred_rows: list[dict], outcome_rows: list[dict]) -> dict:
    """Live scoring 0.1.0 vs naive per horizon. Only pipeline 0.2.0 rows (the corrected pipeline)."""
    rows = sorted([r for r in pred_rows if r["pipeline_version"] == PIPELINE_VERSION], key=lambda r: r["as_of"])
    by_key = {(o["prediction_as_of"], o["horizon_hours"]): o for o in outcome_rows if o["status"] == "ok"}
    out: dict = {"rows_pipeline_0_2_0": len(rows), "signal_mix": dict(Counter(r["signal"] for r in rows)), "by_horizon": {}}
    for h in HORIZONS:
        graded = [(r, by_key[(r["as_of"], h)]) for r in rows if (r["as_of"], h) in by_key]
        if not graded:
            out["by_horizon"][f"{h}h"] = {"n": 0}
            continue
        sig = np.array([r["signal"] for r, _ in graded])
        # pct_change_from_prediction is stored as a FRACTION (0.0044 = +0.44%), despite its name -- see outcome_tracker
        ret = np.array([o["pct_change_from_prediction"] for _, o in graded], dtype=float)
        up = ret > 0
        base = float(up.mean())
        acted = sig != "HOLD"
        acc = float(np.mean((sig[acted] == "BUY") == up[acted])) if acted.any() else float("nan")
        block = max(48, 2 * h)
        stacked = np.column_stack([sig, ret]).astype(object)
        if len(ret) >= 2 * block:
            pt, lo, hi = block_bootstrap(stacked, lambda a: signal_edge(a[:, 0], a[:, 1].astype(float)), block=block, n_boot=N_BOOT, seed=13)
        else:
            pt, lo, hi = signal_edge(sig, ret), float("nan"), float("nan")
        d = {
            "n": int(len(graded)), "base_rate_up": base, "naive_rate": max(base, 1 - base), "acted_share": float(acted.mean()),
            "acted_accuracy": acc, "acted_n": int(acted.sum()),
            "edge": {"point": pt, "ci_low": lo, "ci_high": hi, "interval_available": bool(len(ret) >= 2 * block), "hours_needed_for_interval": 2 * block},
            "buy_and_hold_mean_return": float(ret.mean()),
            "mean_return_by_signal": {s: {"n": int((sig == s).sum()), "mean": float(ret[sig == s].mean()) if (sig == s).any() else None} for s in ("BUY", "HOLD", "SELL")},
        }
        if acted.sum() >= 20:  # stated confidence vs hit rate, as in E001
            hit = ((sig[acted] == "BUY") == up[acted]).astype(float)
            conf = np.array([r["overall_confidence"] for r, _ in graded])[acted]
            buckets, ece, _ = reliability_table(conf, hit, edges=[0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0 + 1e-9])
            d["confidence_reliability"] = {"ece": ece, "buckets": [b.__dict__ | {"enough_rows": b.reliable} for b in buckets]}
        out["by_horizon"][f"{h}h"] = d
    return out


# ---------------------------------------------------------------- 3. paper record (E012 + Platt, 1h move size)
def paper_record(p: np.ndarray, y: np.ndarray, abs_ret: np.ndarray) -> dict:
    """Score stated large-move probabilities against what happened. Pure."""
    n = len(p)
    if n == 0:
        return {"n": 0}
    base = float(y.mean())
    d = {"n": int(n), "base_rate_large": base, "mean_stated_p": float(p.mean()),
         "brier": brier_score(p, y), "brier_base_rate": brier_score(np.full(n, base), y),
         "accuracy": float(np.mean((p > 0.5) == (y > 0.5))), "naive_rate": max(base, 1 - base)}
    d["brier_rel_gain"] = 1 - d["brier"] / d["brier_base_rate"] if d["brier_base_rate"] > 0 else float("nan")
    d["rank_corr_p_vs_abs_return"] = float(pd.Series(p).rank().corr(pd.Series(abs_ret).rank())) if n >= 10 else float("nan")
    buckets, ece, _ = reliability_table(p, y)
    d["ece"] = ece
    d["reliability"] = [b.__dict__ | {"enough_rows": b.reliable} for b in buckets]
    d["note"] = "Paper record computed after the fact from point-in-time candle features; the model is fitted on data before the sealed holdout only. Not a live shadow run. Read intervals, not points, until n is in the thousands."
    return d


def fit_move_size_model():
    """The E012 + Platt 1h model as of the holdout start: fit rows | purge | 90-day calibration slice | purge | holdout."""
    from agent.research.model_test import LogisticModel, PlattCalibrator, build_frame
    from agent.research.periods import HOLDOUT
    from agent.research.walkforward import WalkForwardSpec

    from agent.research.holdout_eval import E012_FEATURES, E012_LOG, E012_THRESHOLD_1H

    df, cols = build_frame(1, [], E012_FEATURES, "large_move", E012_THRESHOLD_1H)
    for c in E012_LOG:
        df[c] = np.log(df[c].where(df[c] > 0))
    spec = WalkForwardSpec(horizon_hours=1, calib_days=90, embargo_hours=24)
    usable = df[cols + ["y"]].dropna()
    calib_end = pd.Timestamp(HOLDOUT.start) - spec.purge
    calib_start = calib_end - pd.Timedelta(days=90)
    fit_end = calib_start - spec.purge
    train = usable[usable.index < fit_end]
    calib = usable[(usable.index >= calib_start) & (usable.index < calib_end)]
    model = LogisticModel(C=0.1)
    model.fit(train[cols], train["y"].to_numpy(dtype=float))
    cal = PlattCalibrator()
    cal.fit(model.predict_proba(calib[cols]), calib["y"].to_numpy(dtype=float))
    return model, cal, cols, {"fit_rows": len(train), "fit_end": str(fit_end), "calib_rows": len(calib), "calib_range": [str(calib_start), str(calib_end)], "platt": cal.params()}


def live_features(now: datetime, lookback_hours: int = 400) -> pd.DataFrame:
    """Point-in-time candle features for the live period from a small, fresh Binance fetch (spot + trades/taker-buy)."""
    from agent.data_providers.binance import HOUR_MS, SYMBOL, BinanceProvider, _get_klines
    from agent.research.features import all_features, bars_to_frame
    from agent.research.microstructure import microstructure_features

    end = now.replace(minute=0, second=0, microsecond=0) - HOUR  # last closed candle
    hours = int((end - LIVE.start).total_seconds() // 3600) + lookback_hours
    bars = BinanceProvider().get_history(end=end, hours=hours)
    grid = bars_to_frame(bars).index
    # trades and taker-buy volume for the same range
    start_ms = int(bars[0].as_of.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    extra_rows, cursor = [], start_ms
    while cursor <= end_ms:
        page = _get_klines({"symbol": SYMBOL, "interval": "1h", "startTime": cursor, "endTime": end_ms + HOUR_MS - 1, "limit": 1000}, timeout=30)
        if not page:
            break
        for k in page:
            if int(k[6]) <= int(now.timestamp() * 1000):
                extra_rows.append((datetime.fromtimestamp(int(k[0]) / 1000, tz=timezone.utc), float(k[5]), int(k[8]), float(k[9])))
        cursor = int(page[-1][0]) + HOUR_MS
    extra = pd.DataFrame(extra_rows, columns=["as_of", "volume", "trades", "taker_buy_volume"]).set_index("as_of")
    feats = pd.concat([all_features(bars), microstructure_features(grid, extra)], axis=1)
    closes = bars_to_frame(bars)["close"]
    feats["fwd_1h"] = closes.shift(-1) / closes - 1  # next candle's close vs this close; NaN where the next hour is a gap or not yet closed
    return feats


def paper_section(now: datetime, outcome_rows: list[dict]) -> dict:
    model, cal, cols, fit_info = fit_move_size_model()
    from agent.research.holdout_eval import E012_LOG, E012_THRESHOLD_1H

    feats = live_features(now)
    live = feats[feats.index >= pd.Timestamp(LIVE.start)].copy()
    for c in E012_LOG:
        live[c] = np.log(live[c].where(live[c] > 0))
    usable = live.dropna(subset=cols + ["fwd_1h"])
    p = cal.transform(model.predict_proba(usable[cols])) if len(usable) else np.array([])
    y = (usable["fwd_1h"].abs() > E012_THRESHOLD_1H).to_numpy(dtype=float)
    rec = paper_record(p, y, usable["fwd_1h"].abs().to_numpy())
    # consistency check: the live outcome tracker's 1h return must equal the research candles' return for the same hour
    tracker = {o["prediction_as_of"]: o["pct_change_from_prediction"] for o in outcome_rows if o["horizon_hours"] == 1 and o["status"] == "ok"}  # fraction
    common = [t for t in usable.index if t.to_pydatetime() in tracker]
    diffs = [abs(tracker[t.to_pydatetime()] - float(usable.loc[t, "fwd_1h"])) for t in common]
    rec["tracker_consistency"] = {"hours_compared": len(common), "max_abs_difference": max(diffs) if diffs else None, "agree_within_1e-9": bool(all(d < 1e-9 for d in diffs)) if diffs else None}
    rec["model"] = fit_info
    rec["latest"] = [{"as_of": str(t), "p_large_move": float(pp)} for t, pp in list(zip(usable.index, p))[-5:]]
    return rec


# ---------------------------------------------------------------- 3b. LIVE shadow record (agent/shadow)
def shadow_record(rows: list[dict], now: datetime) -> dict:
    """rows: dicts with as_of, status, status_reason, live_close_match, p_calibrated, model_version, outcome_status, outcome_return, outcome_large."""
    if not rows:
        return {"n": 0, "note": "no shadow rows yet"}
    rows = sorted(rows, key=lambda r: r["as_of"])
    first = rows[0]["as_of"]
    expected = expected_hours(first, now)
    got = {r["as_of"] for r in rows}
    missing = [t for t in expected if t not in got]
    graded = [r for r in rows if r["outcome_status"] == "ok" and r["status"] == "ok"]
    out = {
        "n": len(rows), "first_hour": first.isoformat(), "expected_hours": len(expected), "missing_hours": [t.isoformat() for t in missing],
        "unavailable": sum(1 for r in rows if r["status"] == "unavailable"), "unavailable_reasons": dict(Counter(r["status_reason"] for r in rows if r["status"] == "unavailable")),
        "live_close_mismatch": sum(1 for r in rows if r["live_close_match"] is False), "live_close_unchecked": sum(1 for r in rows if r["live_close_match"] is None),
        "model_versions": dict(Counter(r["model_version"] for r in rows)),
        "outcomes": {"ok": len(graded), "unavailable": sum(1 for r in rows if r["outcome_status"] == "unavailable"), "pending": sum(1 for r in rows if r["status"] == "ok" and r["outcome_status"] is None)},
    }
    if graded:
        p = np.array([r["p_calibrated"] for r in graded], float)
        y = np.array([1.0 if r["outcome_large"] else 0.0 for r in graded])
        out["evaluation"] = paper_record(p, y, np.abs(np.array([r["outcome_return"] for r in graded], float)))
        out["evaluation"]["note"] = "LIVE shadow record: probabilities were stored before their outcomes existed. Read intervals, not points, until n is in the thousands."
    return out


def fetch_shadow_rows() -> list[dict]:
    from agent.database.db import get_connection

    with get_connection() as c, c.cursor() as cur:
        cur.execute("SELECT to_regclass('shadow_move_size')")
        if cur.fetchone()[0] is None:
            return []
        cur.execute("""SELECT as_of, status, status_reason, live_close_match, p_calibrated, model_version, outcome_status, outcome_return, outcome_large
                       FROM shadow_move_size ORDER BY as_of""")
        return [dict(zip(["as_of", "status", "status_reason", "live_close_match", "p_calibrated", "model_version", "outcome_status", "outcome_return", "outcome_large"], r)) for r in cur.fetchall()]


# ---------------------------------------------------------------- 4. watch list
def watch_list(pred_rows: list[dict], now: datetime) -> dict:
    rows = [r for r in pred_rows if r["pipeline_version"] == PIPELINE_VERSION]
    with_news = sum(1 for r in rows if r["news_items_n"] > 0)
    months = (now - LIVE.start).days / 30.44
    return {
        "news_hours": {"have": with_news, "need": NEWS_HOURS_FOR_8_6, "ready": with_news >= NEWS_HOURS_FOR_8_6},
        "live_months": {"have": round(months, 2), "need": MONTHS_FOR_WATCHLIST, "ready": months >= MONTHS_FOR_WATCHLIST,
                        "tests_waiting": ["funding_last 24h contrarian (E005)", "dxy_ret_5d / tnx_chg_5d 168h negative (E006)"]},
    }


# ---------------------------------------------------------------- database
def fetch_rows() -> tuple[list[dict], list[dict]]:
    from agent.database.db import get_connection

    with get_connection() as c, c.cursor() as cur:
        cur.execute("""SELECT as_of, fetched_at, cutoff_at, pipeline_version, price_source, price_is_synthetic, run_meta,
                              COALESCE(jsonb_array_length(news_items), 0), explanation IS NOT NULL AND explanation <> '',
                              signal, overall_confidence FROM predictions ORDER BY as_of""")
        preds = [dict(zip(["as_of", "fetched_at", "cutoff_at", "pipeline_version", "price_source", "price_is_synthetic", "run_meta",
                           "news_items_n", "has_explanation", "signal", "overall_confidence"], r)) for r in cur.fetchall()]
        cur.execute("""SELECT p.as_of, o.horizon_hours, o.status, o.pct_change_from_prediction
                       FROM prediction_outcomes o JOIN predictions p ON p.id = o.prediction_id""")
        outs = [dict(zip(["prediction_as_of", "horizon_hours", "status", "pct_change_from_prediction"], r)) for r in cur.fetchall()]
    return preds, outs


# ---------------------------------------------------------------- report
def build(now: datetime, with_paper: bool = True) -> dict:
    preds, outs = fetch_rows()
    week_ago = now - timedelta(days=7)
    from agent.database.db import SCHEMA_VERSION, schema_version

    db_schema = schema_version()
    rep = {
        "generated_at": now.isoformat(), "pipeline_version": PIPELINE_VERSION, "scoring_version": SCORING_VERSION,
        "schema_version": {"database": db_schema, "code": SCHEMA_VERSION, "match": db_schema == SCHEMA_VERSION},
        "live_since": LIVE.start.isoformat(), "live_hours": round((now - LIVE.start).total_seconds() / 3600, 1),
        "health_last_7_days": health(preds, outs, now, max(week_ago, LIVE.start)),
        "health_since_go_live": health(preds, outs, now, LIVE.start),
        "signal_record": signal_record(preds, outs),
        "shadow_record": shadow_record(fetch_shadow_rows(), now),
        "watch_list": watch_list(preds, now),
    }
    try:  # Backend Phase A: re-analyse every live hour with the research replay and compare
        from agent.research.parity import run as parity_run

        rep["parity"] = parity_run(LIVE.start, now)
    except Exception as exc:  # noqa: BLE001
        logger.exception("parity check failed")
        rep["parity"] = {"verdict": "ERROR", "error": str(exc)}
    if with_paper:
        try:
            rep["paper_move_size_1h"] = paper_section(now, outs)
        except Exception as exc:  # the report must still come out if the exchange is unreachable
            logger.exception("paper section failed")
            rep["paper_move_size_1h"] = {"error": str(exc)}
    return rep


def _pct(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:+.3f}%"


def render(rep: dict) -> str:
    h7, hall, sr = rep["health_last_7_days"], rep["health_since_go_live"], rep["signal_record"]
    L = [f"# Weekly live report — {rep['generated_at'][:16]} UTC", "",
         f"pipeline {rep['pipeline_version']} · scoring {rep['scoring_version']} (frozen, under test) · schema {rep['schema_version']['database']} (code {rep['schema_version']['code']}{'' if rep['schema_version']['match'] else ' — MISMATCH'}) · live since {rep['live_since'][:16]} · {rep['live_hours']} live hours", "",
         "## 1. Health", "",
         f"- Last 7 days: {h7['predictions']} of {h7['expected_hours']} expected hours; missing: {h7['missing_hours'] or 'none'}",
         f"- Since go-live: {hall['predictions']} of {hall['expected_hours']} expected hours; missing: {len(hall['missing_hours'])} ({', '.join(t[5:16] for t in hall['missing_hours'][:8])}{'…' if len(hall['missing_hours']) > 8 else ''})",
         f"- Fetch delay after candle close (7d): min {h7['fetch_delay_min']['min']:.1f} / median {h7['fetch_delay_min']['median']:.1f} / max {h7['fetch_delay_min']['max']:.1f} min" if h7["predictions"] else "- no rows in the last 7 days",
         f"- Price sources (7d): {h7['price_sources']}; synthetic rows: {h7['synthetic_rows']}; pipeline versions: {h7['pipeline_versions']}",
         f"- Rows without explanation: {h7['rows_without_explanation']}; rows with zero news: {h7['rows_with_zero_news']}; mean news items: {h7['mean_news_items']:.1f}" if h7["predictions"] else "",
         f"- Run errors recorded in run_meta (7d): {h7['run_errors'] or 'none'}; timestamp-rule violations: {h7['timestamp_rule_violations'] or 'none'}",
         "- Outcome coverage (since go-live): " + " · ".join(f"{k}: {v['ok']} ok / {v['unavailable']} unavailable / **{v['overdue']} overdue** of {v['due']} due" for k, v in hall["outcome_coverage"].items()),
         "", "## 2. Live signal record — scoring 0.1.0", "",
         f"Rows (pipeline 0.2.0): {sr['rows_pipeline_0_2_0']} · signal mix {sr['signal_mix']}", "",
         "| horizon | graded n | acted | acted accuracy | naive | edge (BUY − SELL) | 95% interval | buy-and-hold mean |", "|---|---|---|---|---|---|---|---|"]
    for k, d in sr["by_horizon"].items():
        if not d.get("n"):
            L.append(f"| {k} | 0 | | | | | | |")
            continue
        e = d["edge"]
        ci = f"[{_pct(e['ci_low'])}, {_pct(e['ci_high'])}]" if e["interval_available"] else f"needs {e['hours_needed_for_interval']} h"
        L.append(f"| {k} | {d['n']} | {d['acted_share']:.2f} | {d['acted_accuracy']:.3f} (n={d['acted_n']}) | {d['naive_rate']:.3f} | {_pct(e['point'])} | {ci} | {_pct(d['buy_and_hold_mean_return'])} |")
    for k, d in sr["by_horizon"].items():
        cr = d.get("confidence_reliability")
        if cr:
            L += ["", f"Stated confidence vs hit rate at {k} (ECE {cr['ece']:.3f}): " + " · ".join(f"{b['mean_predicted']:.2f} → {b['observed']:.2f} [{b['ci_low']:.2f}, {b['ci_high']:.2f}] n={b['n']}{'' if b['enough_rows'] else ' (few)'}" for b in cr["buckets"])]
    L += ["", "*Read this table as a growing record, not a verdict: intervals appear only once there are enough hours, and one week of hours is far too few to overturn E001.*"]
    sh = rep.get("shadow_record", {})
    L += ["", "## 3. LIVE shadow record — E012 + Platt, P(next-hour move > 0.25%) (agent/shadow, own table, never touches the signal)", ""]
    if not sh.get("n"):
        L.append("No shadow rows yet.")
    else:
        L += [f"- Rows: {sh['n']} since {sh['first_hour'][:16]} · expected {sh['expected_hours']} · missing {len(sh['missing_hours'])} {sh['missing_hours'][:6]}",
              f"- Unavailable (honest blanks): {sh['unavailable']} {sh['unavailable_reasons'] or ''} · reference close ≠ live prediction's: **{sh['live_close_mismatch']}** (unchecked: {sh['live_close_unchecked']}) · model versions: {sh['model_versions']}",
              f"- Outcomes: {sh['outcomes']['ok']} graded · {sh['outcomes']['unavailable']} unavailable · {sh['outcomes']['pending']} pending"]
        ev = sh.get("evaluation")
        if ev:
            L += [f"- Evaluation (n={ev['n']}): Brier {ev['brier']:.4f} vs base-rate {ev['brier_base_rate']:.4f} ({ev['brier_rel_gain'] * 100:+.1f}%) · accuracy {ev['accuracy']:.3f} vs naive {ev['naive_rate']:.3f} · ρ {ev['rank_corr_p_vs_abs_return']:+.3f} · ECE {ev['ece']:.3f}",
                  "", "| stated | observed | 95% interval | n |", "|---|---|---|---|"]
            L += [f"| {b['mean_predicted']:.2f} | {b['observed']:.2f} | [{b['ci_low']:.2f}, {b['ci_high']:.2f}] | {b['n']} |" for b in ev["reliability"]]
            L += ["", f"*{ev['note']}*"]
    pr = rep.get("paper_move_size_1h")
    L += ["", "## 3b. Paper record (after the fact) — same model on all live hours, from candle features", ""]
    if not pr:
        L.append("(not computed this run)")
    elif "error" in pr:
        L.append(f"Could not compute: {pr['error']}")
    elif pr.get("n", 0) == 0:
        L.append("No live hours with usable features yet.")
    else:
        L += [f"n = {pr['n']} live hours · observed large-move share {pr['base_rate_large']:.3f} · mean stated p {pr['mean_stated_p']:.3f}",
              f"Brier {pr['brier']:.4f} vs base-rate {pr['brier_base_rate']:.4f} ({pr['brier_rel_gain'] * 100:+.1f}%) · accuracy {pr['accuracy']:.3f} vs naive {pr['naive_rate']:.3f} · ρ(p, |move|) {pr['rank_corr_p_vs_abs_return']:+.3f} · ECE {pr['ece']:.3f}",
              "", "| stated | observed | 95% interval | n |", "|---|---|---|---|"]
        L += [f"| {b['mean_predicted']:.2f} | {b['observed']:.2f} | [{b['ci_low']:.2f}, {b['ci_high']:.2f}] | {b['n']} |" for b in pr["reliability"]]
        tc = pr["tracker_consistency"]
        L += ["", f"Consistency with the live outcome tracker: {tc['hours_compared']} hours compared, max difference {tc['max_abs_difference']}, agree: {tc['agree_within_1e-9']}",
              f"Model: fitted on {pr['model']['fit_rows']} rows to {pr['model']['fit_end'][:10]}, Platt on {pr['model']['calib_rows']} rows ({pr['model']['calib_range'][0][:10]} → {pr['model']['calib_range'][1][:10]}), a={pr['model']['platt']['a']:.3f} b={pr['model']['platt']['b']:.3f}",
              "Latest: " + ", ".join(f"{x['as_of'][5:16]} → {x['p_large_move']:.2f}" for x in pr["latest"]),
              "", f"*{pr['note']}*"]
    pa = rep.get("parity", {})
    L += ["", "## 4. Live / research parity (Backend Phase A)", ""]
    if pa.get("verdict") == "ERROR":
        L.append(f"Could not run: {pa.get('error')}")
    else:
        L.append(f"**{pa.get('verdict')}** — {pa.get('compared', 0)} live hours re-analysed by the research replay on today's exchange candles; parity breaks: **{pa.get('parity_breaks', 0)}**; skipped: {len(pa.get('skipped', []))} ({dict(Counter(r for _, r in pa.get('skipped', [])))})")
        for b in pa.get("breaks", [])[:5]:
            L.append(f"- {b['as_of']}: " + "; ".join(f"{m[0]} live={m[1]} replay={m[2]}" for m in b["mismatches"][:4]))
    wl = rep["watch_list"]
    L += ["", "## 5. Watch list", "",
          f"- News evaluation (roadmap 8.6): {wl['news_hours']['have']} of {wl['news_hours']['need']} live hours with news — {'READY' if wl['news_hours']['ready'] else 'waiting'}",
          f"- Confirmatory re-tests on live data (funding 24h; dollar/yield 168h): {wl['live_months']['have']} of {wl['live_months']['need']} months — {'READY' if wl['live_months']['ready'] else 'waiting'}",
          "", "Reminders: healthchecks.io heartbeat not set up; GitHub token `supabase-dispatch` expires 2027-09-20; scheduled workflows on a public repo pause after 60 days without a commit."]
    return "\n".join(L)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-paper", action="store_true", help="skip the exchange fetch / model fit for the paper record")
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    now = datetime.now(timezone.utc)
    rep = build(now, with_paper=not args.no_paper)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"weekly_{now:%Y-%m-%d}"
    stem.with_suffix(".json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    stem.with_suffix(".md").write_text(render(rep), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(stem.with_suffix(".md").read_text(encoding="utf-8"))
