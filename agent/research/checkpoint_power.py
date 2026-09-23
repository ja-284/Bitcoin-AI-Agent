"""
E024 -- how many live hours before the shadow record can say anything? (descriptive planning)

    python -m agent.research.checkpoint_power --experiment E024

The prospective checkpoints (500 / 2,000 / 5,000 shadow hours, research/LIVE_EVALUATION.md) were
set without a power analysis. This asks, for a live record of N consecutive hours: how often does
it show the move-size model ahead of the free E019 reference, how widely does that comparison
swing, how often does the model pass E012's skill bar, and how noisy is its measured calibration?

Method. A live record is a CONTIGUOUS stretch of hours, not a random sample of them, so the honest
sampling distribution is not an i.i.d. bootstrap: it is every contiguous N-hour window of an
out-of-sample record. Each window carries its own market regime, which is exactly the variation a
real prospective record will face. The out-of-sample record used is the walk-forward output that
reproduces E013 exactly (27 folds), on the validation period -- the most recent, most live-like
stretch. Windows are laid every 24 hours (overlapping), and every statistic is computed inside the
window alone, as the weekly report would compute it.

What this is NOT. It fits nothing, selects nothing and tests no hypothesis; it cannot change any
model or threshold. It estimates variability for planning. It does use the (worn) validation
period, which is acceptable for variance estimation and would not be for choosing anything. And it
assumes the live advantage is the size seen on validation; if the true live advantage is smaller,
every "hours needed" figure here is an UNDER-estimate, and that is said wherever it is printed.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.research.feature_count import FULL, evaluate, prepare
from agent.research.history import load_bars
from agent.research.diagnose import spearman
from agent.research.metrics import block_bootstrap, brier_score, reliability_table
from agent.research.periods import HOLDOUT
from agent.research.simple_baselines import simple_rules
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

WINDOW_HOURS = [18, 48, 100, 200, 500, 1000, 2000, 5000]
STEP_HOURS = 24
E012_SKILL_BAR = 0.05       # E012 / E014: Brier at least 5% below the window's own base rate
E013_ECE_BAR = 0.03
SIM_SEED = 7                # outcomes of the perfectly calibrated control
RHO_INTERVAL_AT = (500, 2000)
RHO_INTERVAL_STRIDE = 7     # every 7th window (weekly spacing) for the per-window bootstrap
RHO_BOOT = 300


def e013_passes(p: np.ndarray, y: np.ndarray) -> tuple[bool, bool, float]:
    """E013 exactly as written: ECE <= 0.03 AND every bucket with >= 100 rows within 0.05."""
    buckets, ece, _ = reliability_table(p, y)
    buckets_ok = all(abs(b.observed - b.mean_predicted) <= 0.05 for b in buckets if b.n >= 100)
    return ece <= E013_ECE_BAR, buckets_ok, ece


def window_stats(p: np.ndarray, ref: np.ndarray, y: np.ndarray, size: np.ndarray, y_calibrated: np.ndarray) -> dict:
    """
    y_calibrated: outcomes simulated from the model's own probabilities -- a forecaster that is
    perfectly calibrated BY CONSTRUCTION. Whatever share of windows it fails a calibration rule
    in is that rule's false-failure rate from sampling noise alone.
    """
    base = float(y.mean())
    b_base = brier_score(np.full(len(y), base), y)
    b_model, b_ref = brier_score(p, y), brier_score(ref, y)
    skill = 1 - b_model / b_base if b_base > 0 else float("nan")
    acc = float(np.mean((p > 0.5) == (y > 0.5)))
    naive = max(base, 1 - base)
    rho = spearman(p, size)
    ece_ok, buckets_ok, ece = e013_passes(p, y)
    sim_ece_ok, sim_buckets_ok, sim_ece = e013_passes(p, y_calibrated)
    return {
        "model_ahead": b_model < b_ref,
        "brier_diff": b_ref - b_model,  # positive = the model is ahead
        "model_skill": skill,
        "ece": ece,
        "large_move_share": base,
        # E012 as written (the interval on rho is added separately, where it is affordable)
        "e012_brier": skill >= E012_SKILL_BAR, "e012_accuracy": acc >= naive + 0.05, "e012_rho_point": rho >= 0.10,
        "rho": rho,
        # E013 as written, on the real outcomes and on perfectly calibrated simulated ones
        "e013_ece": ece_ok, "e013_buckets": buckets_ok,
        "perfect_e013_ece": sim_ece_ok, "perfect_e013_buckets": sim_buckets_ok, "perfect_ece": sim_ece,
    }


def run(experiment: str) -> Path:
    df, spec, folds = prepare()
    oos = evaluate(df, spec, folds, FULL, {})["predictions"]
    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(oos.index)
    val = oos[(oos["period"] == "validation")].copy()
    val["ref"] = ewma.reindex(val.index)
    val = val.dropna(subset=["ref"])
    p, ref, y = val["p"].to_numpy(float), val["ref"].to_numpy(float), val["y"].to_numpy(float)
    size = np.abs(val["fwd_1h"].to_numpy(float))
    y_cal = (np.random.default_rng(SIM_SEED).uniform(size=len(p)) < p).astype(float)
    n_total = len(y)
    full = window_stats(p, ref, y, size, y_cal)
    logger.info("validation rows %d; whole-period model ahead by %.5f Brier", n_total, full["brier_diff"])

    def share(rows, key):
        return float(np.mean([bool(r[key]) for r in rows]))

    table = {}
    for n in WINDOW_HOURS:
        if n > n_total:
            continue
        starts = range(0, n_total - n + 1, STEP_HOURS)
        rows = [window_stats(p[s:s + n], ref[s:s + n], y[s:s + n], size[s:s + n], y_cal[s:s + n]) for s in starts]
        diffs = np.array([r["brier_diff"] for r in rows])
        skills = np.array([r["model_skill"] for r in rows])
        eces = np.array([r["ece"] for r in rows])
        shares = np.array([r["large_move_share"] for r in rows])
        entry = {
            "windows": len(rows),
            "share_model_ahead": float(np.mean(diffs > 0)),
            "brier_diff_p05_median_p95": [float(np.percentile(diffs, q)) for q in (5, 50, 95)],
            "share_passing_E012_skill_bar": float(np.mean(skills >= E012_SKILL_BAR)),
            "model_skill_p05_median_p95": [float(np.percentile(skills, q)) for q in (5, 50, 95)],
            "share_ece_within_E013_bar": float(np.mean(eces <= E013_ECE_BAR)),
            "ece_median_p95": [float(np.percentile(eces, 50)), float(np.percentile(eces, 95))],
            "large_move_share_p05_p95": [float(np.percentile(shares, 5)), float(np.percentile(shares, 95))],
            "e012_parts": {k: share(rows, k) for k in ("e012_brier", "e012_accuracy", "e012_rho_point")},
            "e012_all_point_parts": float(np.mean([r["e012_brier"] and r["e012_accuracy"] and r["e012_rho_point"] for r in rows])),
            "e013_real": {"ece": share(rows, "e013_ece"), "buckets": share(rows, "e013_buckets"),
                          "both": float(np.mean([r["e013_ece"] and r["e013_buckets"] for r in rows]))},
            "e013_perfectly_calibrated": {"ece": share(rows, "perfect_e013_ece"), "buckets": share(rows, "perfect_e013_buckets"),
                                          "both": float(np.mean([r["perfect_e013_ece"] and r["perfect_e013_buckets"] for r in rows])),
                                          "ece_median_p95": [float(np.percentile([r["perfect_ece"] for r in rows], q)) for q in (50, 95)]},
        }
        if n in RHO_INTERVAL_AT:  # the rho interval is a bootstrap per window: affordable at the verdict sizes only
            sub = list(starts)[::RHO_INTERVAL_STRIDE]
            excl = []
            for s in sub:
                pairs = np.column_stack([p[s:s + n], size[s:s + n]])
                _, lo, _ = block_bootstrap(pairs, lambda a: spearman(a[:, 0], a[:, 1]), block=48, n_boot=RHO_BOOT, seed=31)
                excl.append(lo > 0)
            entry["e012_rho_interval_excludes_zero"] = {"windows": len(sub), "share": float(np.mean(excl))}
        table[n] = entry
    res = {
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION, "snapshot": snapshot.name,
        "validation_rows": n_total, "step_hours": STEP_HOURS, "whole_period": full,
        "by_window_hours": table,
    }
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "checkpoint_power.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "checkpoint_power.md").write_text(render(res), encoding="utf-8")
    return out_dir / "checkpoint_power.md"


def render(r: dict) -> str:
    L = ["# E024 -- how many live hours before the shadow record can say anything?", "",
         "Generated %s  |  pipeline %s  |  %d validation hours, windows laid every %dh" % (
             r["generated_at"], r["pipeline_version"], r["validation_rows"], r["step_hours"]),
         "", "**Descriptive planning. Fits nothing, selects nothing, changes nothing.** Assumes the live advantage is",
         "the size seen on validation; if it is smaller, every figure below is an UNDER-estimate of the hours needed.", "",
         "Whole validation period: model ahead of the free EWMA reference by %.5f Brier." % r["whole_period"]["brier_diff"], "",
         "| live hours | windows | model ahead of free rule | Brier lead: 5th / median / 95th pct | passes E012 skill bar | ECE within 0.03 | large-move share range |",
         "|---|---|---|---|---|---|---|"]
    for n, t in r["by_window_hours"].items():
        d = t["brier_diff_p05_median_p95"]
        L.append("| %s | %d | %.0f%% | %+.4f / %+.4f / %+.4f | %.0f%% | %.0f%% | %.0f%%-%.0f%% |" % (
            n, t["windows"], 100 * t["share_model_ahead"], d[0], d[1], d[2],
            100 * t["share_passing_E012_skill_bar"], 100 * t["share_ece_within_E013_bar"],
            100 * t["large_move_share_p05_p95"][0], 100 * t["large_move_share_p05_p95"][1]))

    L += ["", "## The verdict rules as written (research/LIVE_EVALUATION.md), window by window", "",
          "E012 (verdict at 2,000 hours): Brier >= 5% below base AND accuracy >= naive + 5 points AND rho >= 0.10",
          "with its interval excluding zero. E013 (verdict at 5,000 hours): ECE <= 0.03 AND every bucket with",
          ">= 100 rows within 0.05. The **perfectly calibrated** columns use outcomes simulated from the model's own",
          "probabilities: whatever share of windows fails there is the rule's failure rate from **noise alone**.", "",
          "| live hours | E012 Brier | E012 accuracy | E012 rho point | E012 rho interval | E013 ECE | E013 buckets | E013 both | perfect: ECE | perfect: buckets | perfect: both |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, t in r["by_window_hours"].items():
        e12, e13, pc = t["e012_parts"], t["e013_real"], t["e013_perfectly_calibrated"]
        ri = t.get("e012_rho_interval_excludes_zero")
        L.append("| %s | %.0f%% | %.0f%% | %.0f%% | %s | %.0f%% | %.0f%% | %.0f%% | %.0f%% | %.0f%% | %.0f%% |" % (
            n, 100 * e12["e012_brier"], 100 * e12["e012_accuracy"], 100 * e12["e012_rho_point"],
            ("%.0f%% (%d windows)" % (100 * ri["share"], ri["windows"])) if ri else "--",
            100 * e13["ece"], 100 * e13["buckets"], 100 * e13["both"],
            100 * pc["ece"], 100 * pc["buckets"], 100 * pc["both"]))
    L += ["", "Percentages are the share of N-hour windows in which the rule PASSES."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E024")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
