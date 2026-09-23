"""
Phase 12: the ONE-TIME evaluation on the sealed holdout (2025-07-01 -> 2026-08-19).

What it judges is fixed in research/experiments/E014_holdout_evaluation.json before this
runs, and nothing about the objects under test may change afterwards:

  A  scoring 0.1.0 (the live signal) -- direction, E001's criterion
  B  E011 set-A direction model (1h) -- the null result, E011's criterion
  C  E012 raw 1h move-size model -- E012's criterion
  D  E012 + Platt (E013's choice) 1h move-size model -- E012's and E013's criteria

plus, AFTER E014's verdict is fixed, the five secondary hypotheses registered in E023
(agent/research/holdout_secondary.py) -- evaluated on the same candles and folds, unable to
change E014's verdict.

Models B-D keep walking forward: every holdout quarter is scored by a model fitted only on
data before it (with the usual purge/embargo and, for D, the purged calibration slice), so the
holdout sees exactly what a live deployment would have produced.

`--dry-run` proves the script end-to-end WITHOUT opening the holdout: it loads candles only
up to the holdout's start and evaluates the (already seen) validation period instead.
The real run needs `--unseal`, which loads holdout candles through load_bars(allow_holdout=True)
-- the only route -- and is written to research/HOLDOUT_ACCESS.log.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research import evaluate as e001
from agent.research.history import load_bars
from agent.research.model_test import CALIBRATORS, LogisticModel, build_frame, evaluate_predictions
from agent.research.periods import HOLDOUT, VALIDATION, Period
from agent.research.replay import replay_cached
from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward
from agent.scoring.scorer import SCORING_VERSION
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

# The objects under test, exactly as recorded in E011 / E012 / E013.
E011_SET_A = ["trend_score", "momentum_score", "volume_score", "chart_pattern_score", "tr_mean_14_rel", "trades_rel_168h",
              "taker_buy_share_1h", "taker_buy_share_6h", "vol_pct_720"]
E012_FEATURES = ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168", "trades_rel_24h", "trades_rel_168h", "hour_sin", "hour_cos", "is_weekend"]
E012_LOG = ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168", "trades_rel_24h", "trades_rel_168h"]
E012_THRESHOLD_1H = 0.0025
C = 0.1
# The scoring version E014 tests as object A (amended 2026-09-23 from 0.1.0, while sealed). The run
# refuses to start if the code's scoring version differs: a scoring change must never silently change
# what the one-time evaluation tests -- it needs a dated amendment to E014 first.
REGISTERED_SCORING_VERSION = "0.2.0"


def assert_registered_versions() -> None:
    if SCORING_VERSION != REGISTERED_SCORING_VERSION:
        raise RuntimeError(
            f"scoring is {SCORING_VERSION} but E014 registers {REGISTERED_SCORING_VERSION} as object A. "
            "Amend research/experiments/E014_holdout_evaluation.json (dated, while sealed) before running.")


def _window(df: pd.DataFrame, window: Period) -> pd.DataFrame:
    return df[(df.index >= pd.Timestamp(window.start)) & (df.index < pd.Timestamp(window.end))]


def _fit_and_score(df: pd.DataFrame, cols: list[str], horizon: int, window: Period, calib_days: int, calibrator: str) -> tuple[pd.DataFrame, list[dict]]:
    """Walk forward with test blocks starting exactly at the window start; keep only window rows."""
    spec = WalkForwardSpec(horizon_hours=horizon, scheme="expanding", min_train_days=365, test_block_days=90, embargo_hours=24, calib_days=calib_days)
    usable_index = df[cols + ["y"]].dropna().index
    folds = make_folds(usable_index, spec, eval_start=pd.Timestamp(window.start))
    folds = [f for f in folds if f.test_start < pd.Timestamp(window.end)]
    make_cal = None
    if calibrator != "none":
        make_cal = CALIBRATORS[calibrator]
    preds, diag = run_walk_forward(df, cols, "y", lambda: LogisticModel(C=C), spec, folds=folds, make_calibrator=make_cal)
    return _window(preds, window), diag


def _model_block(df: pd.DataFrame, cols: list[str], horizon: int, window: Period, calib_days: int, calibrator: str) -> dict:
    preds, diag = _fit_and_score(df, cols, horizon, window, calib_days, calibrator)
    ev = evaluate_predictions(preds, df, horizon)
    win = ev["overall"]  # preds already restricted to the window
    return {"n": int(len(preds)), "folds": diag, "window": win, "by_year": ev["by_year"], "baseline_0_1_0_same_rows": ev["baseline_0_1_0_same_rows"]}


def _scoring_block(bars, rows, window: Period) -> dict:
    """Scoring 0.1.0 and the simple baselines on the window, E001-style (binary + fixed-band three-class)."""
    df = e001.build_frame(bars, rows)
    signals = e001.baseline_signals(df, rows)
    mask = ((df["as_of"] >= pd.Timestamp(window.start)) & (df["as_of"] < pd.Timestamp(window.end))).to_numpy()
    out = {}
    for spec in e001.label_specs():
        if spec.kind == "three_class" and spec.threshold_kind != "fixed":
            continue  # binary (edge, accuracy) and the fixed-band three-class (balanced accuracy), as in E001's criterion
        out[spec.name] = e001.evaluate_slice(df, mask, signals, spec, with_ci=spec.kind == "binary")
    out["signal_mix"] = {s: int(((df["signal"] == s) & mask).sum()) for s in ("BUY", "HOLD", "SELL")}
    return out


def run(experiment: str, unseal: bool, dry_run: bool) -> Path:
    if unseal == dry_run:
        raise ValueError("choose exactly one of --unseal (the real, one-time run) or --dry-run")
    assert_registered_versions()  # before a single candle is loaded
    if dry_run:
        window = VALIDATION
        bars, quality, snapshot = load_bars(end=HOLDOUT.start)
        out_dir = Path("research") / "results" / f"{experiment}_dryrun"
    else:
        window = HOLDOUT
        bars, quality, snapshot = load_bars(end=HOLDOUT.end, allow_holdout=True,
                                            reason=f"{experiment}: Phase 12 one-time holdout evaluation of scoring 0.1.0, E011 set A, E012 1h raw, E012 1h + Platt")
        out_dir = Path("research") / "results" / experiment
    logger.info("Loaded %d candles from %s (window %s -> %s)", quality.count, snapshot.name, window.start, window.end)
    rows = replay_cached(bars, snapshot)
    data = (bars, snapshot)

    results: dict = {
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "dry_run": dry_run,
        "pipeline_version": PIPELINE_VERSION, "scoring_version": SCORING_VERSION, "snapshot": snapshot.name,
        "window": {"name": window.name, "start": str(window.start), "end": str(window.end)},
        "candles_in_window": int(sum(1 for b in bars if window.start <= b.as_of < window.end)),
    }
    logger.info("A: scoring 0.1.0")
    results["A_scoring_0_1_0"] = _scoring_block(bars, rows, window)

    logger.info("B: E011 set A direction 1h")
    df_dir, cols = build_frame(1, [], E011_SET_A, "direction", None, data=data)
    results["B_E011_direction_1h"] = _model_block(df_dir, cols, 1, window, 0, "none")

    logger.info("C/D: E012 move size 1h, raw and Platt")
    df_sz, cols = build_frame(1, [], E012_FEATURES, "large_move", E012_THRESHOLD_1H, data=data)
    for c in E012_LOG:
        df_sz[c] = np.log(df_sz[c].where(df_sz[c] > 0))
    results["C_E012_size_1h_raw"] = _model_block(df_sz, cols, 1, window, 90, "none")
    results["D_E012_size_1h_platt"] = _model_block(df_sz, cols, 1, window, 90, "platt")

    results["verdicts"] = verdicts(results)  # E014's verdict, fixed BEFORE the secondary hypotheses run

    logger.info("E023: secondary hypotheses (cannot change E014's verdict)")
    from agent.research import holdout_secondary

    # Same candles, same frame, same walk-forward as object D -- no new route to the data.
    results["E023_secondary"] = holdout_secondary.evaluate(df_sz, cols, bars, window, _fit_and_score)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(render(results), encoding="utf-8")
    return out_dir


def verdicts(res: dict) -> dict:
    """The pre-registered pass rules of E001 / E011 / E012 / E013, applied to the window only."""
    v: dict = {}
    a = res["A_scoring_0_1_0"]
    for name, blk in a.items():
        if name == "signal_mix" or "system" not in blk or "classification" in blk["system"]:
            continue
        sysm = blk["system"]
        naive = max(blk["label_distribution"].values())
        # E001 (b): the fixed-band three-class balanced accuracy must beat every trivial baseline
        three = a.get(name.replace("binary_", "three_class_") + "_fixed_0.005", {})
        ba_sys = three.get("system", {}).get("classification", {}).get("balanced_accuracy", float("nan"))
        ba_base = {k: blk2["classification"]["balanced_accuracy"] for k, blk2 in three.items() if isinstance(blk2, dict) and "classification" in blk2 and k != "system"}
        beats_all = bool(ba_base) and all(ba_sys > x for x in ba_base.values())
        v[f"A_{name}"] = {"acted_accuracy": sysm.get("acted_accuracy"), "naive": naive, "edge": sysm["edge"],
                          "balanced_accuracy_3class": ba_sys, "baselines_balanced_accuracy": ba_base,
                          "pass": bool(sysm["edge"]["ci_low"] > 0 and beats_all)}
    b = res["B_E011_direction_1h"]["window"]
    v["B_E011_1h"] = {"acted_accuracy": b["acted_accuracy"], "naive": b["naive_rate"], "edge": b["edge"], "brier": b["brier"], "brier_base": b["brier_base_rate"],
                      "pass": bool(b["acted_accuracy"] > b["naive_rate"] and (b["edge"]["ci_low"] > 0 or b["edge"]["ci_high"] < 0) and b["brier"] < b["brier_base_rate"])}
    for key in ("C_E012_size_1h_raw", "D_E012_size_1h_platt"):
        w = res[key]["window"]
        r = w["rank_corr_p_vs_abs_return"]
        big = [bk for bk in w["reliability"] if bk["n"] >= 100]
        max_gap = max(abs(bk["observed"] - bk["mean_predicted"]) for bk in big) if big else float("nan")
        v[key] = {
            "brier": w["brier"], "brier_base": w["brier_base_rate"], "brier_rel_gain": 1 - w["brier"] / w["brier_base_rate"],
            "acted_accuracy": w["acted_accuracy"], "naive": w["naive_rate"], "rho": r, "ece": w["ece"], "max_bucket_gap": max_gap,
            "E012_pass": bool(w["brier"] <= 0.95 * w["brier_base_rate"] and w["acted_accuracy"] >= w["naive_rate"] + 0.05 and r["point"] >= 0.10 and r["ci_low"] > 0),
            "E013_calibrated": bool(w["ece"] <= 0.03 and max_gap <= 0.05),
        }
    return v


def _pct(x):
    return f"{x * 100:+.2f}%"


def render(res: dict) -> str:
    w = res["window"]
    v = res["verdicts"]
    L = [f"# {res['experiment']} — {'DRY RUN on validation' if res['dry_run'] else 'ONE-TIME HOLDOUT EVALUATION'}: {w['start'][:10]} → {w['end'][:10]}", "",
         f"pipeline {res['pipeline_version']} / scoring {res['scoring_version']} · snapshot {res['snapshot']} · candles in window {res['candles_in_window']}", "",
         "## A — scoring 0.1.0 (the live signal), direction", "",
         "| label | acted accuracy | naive | edge (95% CI) | buy-and-hold mean | 3-class balanced acc. | pass |", "|---|---|---|---|---|---|---|"]
    a = res["A_scoring_0_1_0"]
    for name, blk in a.items():
        if f"A_{name}" not in v:
            continue
        s = blk["system"]
        e = s["edge"]
        vv = v[f"A_{name}"]
        L.append(f"| {name} | {s.get('acted_accuracy', float('nan')):.3f} (n={s.get('acted_n', 0)}) | {vv['naive']:.3f} | {_pct(e['point'])} [{_pct(e['ci_low'])}, {_pct(e['ci_high'])}] | {_pct(blk['buy_and_hold_mean_return'])} | {vv['balanced_accuracy_3class']:.3f} vs best baseline {max(vv['baselines_balanced_accuracy'].values()):.3f} | {'YES' if vv['pass'] else 'no'} |")
    L.append(f"\nSignal mix in window: {a['signal_mix']}")
    b = v["B_E011_1h"]
    L += ["", "## B — E011 direction model (1h, set A): the null result", "",
          f"acted accuracy {b['acted_accuracy']:.3f} vs naive {b['naive']:.3f} · edge {_pct(b['edge']['point'])} [{_pct(b['edge']['ci_low'])}, {_pct(b['edge']['ci_high'])}] · Brier {b['brier']:.4f} vs base {b['brier_base']:.4f} · **pass: {'YES' if b['pass'] else 'no'}**"]
    for key, title in (("C_E012_size_1h_raw", "C — E012 move-size model (1h), raw"), ("D_E012_size_1h_platt", "D — E012 + Platt (the chosen deliverable)")):
        d = v[key]
        r = d["rho"]
        L += ["", f"## {title}", "",
              f"Brier {d['brier']:.4f} vs base {d['brier_base']:.4f} ({d['brier_rel_gain'] * 100:+.1f}%) · accuracy {d['acted_accuracy']:.3f} vs naive {d['naive']:.3f} ({(d['acted_accuracy'] - d['naive']) * 100:+.1f} pts) · ρ(p, |move|) {r['point']:+.3f} [{r['ci_low']:+.3f}, {r['ci_high']:+.3f}] · ECE {d['ece']:.4f} · worst bucket {d['max_bucket_gap']:.3f}",
              f"**E012 criterion: {'PASS' if d['E012_pass'] else 'no'} · E013 calibrated: {'YES' if d['E013_calibrated'] else 'no'}**", "",
              "| stated | observed | 95% interval | n |", "|---|---|---|---|"]
        for bk in res[key]["window"]["reliability"]:
            L.append(f"| {bk['mean_predicted']:.2f} | {bk['observed']:.2f} | [{bk['ci_low']:.2f}, {bk['ci_high']:.2f}] | {bk['n']} |")
        yrs = res[key]["by_year"]
        L.append("\nPer year (accuracy − naive, points / ECE): " + " · ".join(f"{yr}: {(d2['acted_accuracy'] - d2['naive_rate']) * 100:+.1f} / {d2['ece']:.3f}" for yr, d2 in yrs.items() if d2.get("n")))
        L.append("Folds (test start → gap hours): " + ", ".join(f"{f['test_range'][0][:10]} → {int(f['gap_hours_between_last_fit_row_and_test_start'])}" for f in res[key]["folds"]))
    if "E023_secondary" in res:
        from agent.research import holdout_secondary

        L += holdout_secondary.render(res["E023_secondary"], res["dry_run"])
    return "\n".join(L)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E014")
    parser.add_argument("--unseal", action="store_true", help="the real, one-time run on the sealed holdout")
    parser.add_argument("--dry-run", action="store_true", help="prove the script on the validation period; holdout stays sealed")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = run(args.experiment, args.unseal, args.dry_run)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print((out / "summary.md").read_text(encoding="utf-8"))
