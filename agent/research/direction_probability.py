"""
E032 (RESEARCH-ONLY, pre-registered in d8a3d5f before this code): does E011's faint 1h probability of UP carry
measurable, calibrated, stable skill? One model, one horizon, fixed in advance
(research/experiments/E032_direction_probability.json).

    python -m agent.research.direction_probability --experiment E032

E011's eight pre-defined inputs, an L2 logistic (C = 0.1), E011's expanding walk-forward with no calibration slice,
against a leak-free base rate (each fold's training share of UP hours) and a one-feature reversal logistic
(taker_buy_share_1h), all on identical rows. Development data only: build_frame -> load_bars(end=HOLDOUT.start).
Directional track only: nothing here touches the move-size model, the live signal or any checkpoint.
Measurable skill is not usefulness: the economics are reported, never judged.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.block_calibration import calibration_line
from agent.research.checkpoint_power import e013_passes
from agent.research.diagnose import spearman
from agent.research.metrics import block_bootstrap, brier_score, log_loss
from agent.research.simple_baselines import paired_difference
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

HORIZON = 1
C = 0.1
INPUTS = ["trend_score", "momentum_score", "volume_score", "chart_pattern_score", "tr_mean_14_rel", "trades_rel_168h",
          "taker_buy_share_1h", "taker_buy_share_6h"]  # E011's "A_minus_volpct", unchanged
ONE_FEATURE = ["taker_buy_share_1h"]
PRACTICAL_RATIO = 1.10       # H_b (E020's practical bar)
MIN_POSITIVE_YEARS = 6       # H_d: of the 8 calendar years 2018-2025
ROUND_TRIP_COST = 0.001      # 0.10%, for the descriptive economics only
EDGE_BLOCK, EDGE_BOOT, EDGE_SEED = 48, 500, 32


def edge(p: np.ndarray, ret: np.ndarray) -> float:
    """Mean forward return when p > 0.5 minus when p < 0.5 (NaN if one side is empty)."""
    up, down = ret[p > 0.5], ret[p < 0.5]
    return float(up.mean() - down.mean()) if len(up) and len(down) else float("nan")


def scores(p: np.ndarray, y: np.ndarray, ret: np.ndarray, p_base: np.ndarray, index: pd.DatetimeIndex) -> dict:
    b, b_base = brier_score(p, y), brier_score(p_base, y)
    oracle = float(y.mean())
    b_oracle = brier_score(np.full(len(y), oracle), y)
    ece_ok, buckets_ok, ece = e013_passes(p, y)
    point, lo, hi = block_bootstrap(np.column_stack([p, ret]), lambda a: edge(a[:, 0], a[:, 1]), block=EDGE_BLOCK,
                                    n_boot=EDGE_BOOT, seed=EDGE_SEED)
    signed = np.sign(p - 0.5) * ret
    years = {}
    for yr in sorted(set(index.year)):
        m = index.year == yr
        years[str(yr)] = {"rows": int(m.sum()), "skill_vs_base_rate": 1 - brier_score(p[m], y[m]) / brier_score(p_base[m], y[m])}
    return {"rows": int(len(y)), "brier": b, "skill_vs_base_rate": 1 - b / b_base, "skill_vs_oracle_base": 1 - b / b_oracle,
            "log_loss": log_loss(p, y), "ece": ece, "e013_ece_ok": bool(ece_ok), "e013_buckets_ok": bool(buckets_ok),
            "calibration_line": calibration_line(p, y), "mean_stated": float(p.mean()), "observed_up_share": oracle,
            "rho_p_vs_return": spearman(p, ret), "accuracy_at_0_5": float(np.mean((p > 0.5) == (y > 0.5))),
            "naive_accuracy": max(oracle, 1 - oracle), "share_called_up": float(np.mean(p > 0.5)),
            "return_edge": {"point": point, "ci95": [lo, hi]},
            "gross_signed_return_per_hour": float(signed.mean()), "round_trip_cost": ROUND_TRIP_COST,
            "by_year": years}


def judge(r: dict) -> dict:
    """The four pre-registered hypotheses, exactly as written. Pure."""
    bp = r["by_period"]
    h_a = all(bp[p]["base_minus_model_brier"]["diff"] > 0 and bp[p]["base_minus_model_brier"]["ci_low"] > 0 for p in bp)
    v = bp["validation"]
    h_b = (v["model"]["skill_vs_base_rate"] >= PRACTICAL_RATIO * v["one_feature"]["skill_vs_base_rate"]
           and v["one_feature_minus_model_brier"]["ci_low"] > 0)
    h_c = all(bp[p]["model"]["ece"] <= 0.03 for p in bp) and v["model"]["e013_buckets_ok"]
    years = {**bp["exploration"]["model"]["by_year"], **bp["validation"]["model"]["by_year"]}
    positive = sum(1 for yr in map(str, range(2018, 2026)) if yr in years and years[yr]["skill_vs_base_rate"] > 0)
    return {"H_a_skill_beyond_the_base_rate": bool(h_a), "H_b_more_than_one_reversal_feature": bool(h_b),
            "H_c_calibrated": bool(h_c), "H_d_stable": bool(positive >= MIN_POSITIVE_YEARS), "positive_years": positive}


def run(experiment: str) -> Path:
    from agent.research.model_test import BaseRateModel, LogisticModel, build_frame
    from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward

    df, _ = build_frame(HORIZON, [], INPUTS, "direction")  # load_bars(end=HOLDOUT.start) inside
    common = df[INPUTS + ["y"]].dropna().index  # restricted ONCE: every candidate is scored on the same hours
    df = df.loc[common]
    spec = WalkForwardSpec(horizon_hours=HORIZON, scheme="expanding", min_train_days=365, test_block_days=90,
                           embargo_hours=24, calib_days=0)
    folds = make_folds(common, spec)
    model, _ = run_walk_forward(df, INPUTS, "y", lambda: LogisticModel(C=C), spec, folds=folds)
    one, _ = run_walk_forward(df, ONE_FEATURE, "y", lambda: LogisticModel(C=C), spec, folds=folds)
    base, _ = run_walk_forward(df, INPUTS, "y", BaseRateModel, spec, folds=folds)
    assert model.index.equals(one.index) and model.index.equals(base.index), "the candidates must be scored on identical rows"
    joined = model.join(df[["period", "fwd_%dh" % HORIZON]], how="left").sort_index()
    pm, pf, pb = (joined["p"].to_numpy(float), one["p"].reindex(joined.index).to_numpy(float),
                  base["p"].reindex(joined.index).to_numpy(float))
    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "rows": int(len(joined)), "folds": len(folds), "inputs": INPUTS, "one_feature": ONE_FEATURE, "by_period": {}}
    for period in ("exploration", "validation"):
        m = (joined["period"] == period).to_numpy()
        idx, y, ret = joined.index[m], joined["y"].to_numpy(float)[m], joined["fwd_%dh" % HORIZON].to_numpy(float)[m]
        res["by_period"][period] = {
            "model": scores(pm[m], y, ret, pb[m], idx), "one_feature": scores(pf[m], y, ret, pb[m], idx),
            "base_rate": {"brier": brier_score(pb[m], y), "mean_stated": float(pb[m].mean())},
            "base_minus_model_brier": paired_difference(pb[m], pm[m], y),
            "one_feature_minus_model_brier": paired_difference(pf[m], pm[m], y)}
    res["verdict"] = judge(res)
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "direction_probability.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "direction_probability.md").write_text(render(res), encoding="utf-8")
    return out_dir / "direction_probability.md"


def render(r: dict) -> str:
    L = ["# E032 — does the faint 1h probability of UP carry measurable, calibrated, stable skill? (research-only)", "",
         f"Generated {r['generated_at'][:16]} UTC · {r['rows']:,} development hours, identical rows for every candidate · "
         f"{r['folds']} folds · directional track only · hypothesis-generating (validation wear) · measurable skill is not usefulness", ""]
    for period, d in r["by_period"].items():
        mo, of = d["model"], d["one_feature"]
        bm, fm = d["base_minus_model_brier"], d["one_feature_minus_model_brier"]
        L += [f"## {period} ({mo['rows']:,} hours; UP share {mo['observed_up_share']:.3f})", "",
              "| measure | model (8 inputs) | one-feature (taker-buy share 1h) |", "|---|---|---|",
              f"| Brier (base rate {d['base_rate']['brier']:.5f}) | {mo['brier']:.5f} | {of['brier']:.5f} |",
              f"| Brier skill vs the leak-free base rate | {mo['skill_vs_base_rate']:+.5f} | {of['skill_vs_base_rate']:+.5f} |",
              f"| log loss | {mo['log_loss']:.5f} | {of['log_loss']:.5f} |",
              f"| ECE · E013 buckets | {mo['ece']:.3f} · {'yes' if mo['e013_buckets_ok'] else 'no'} | {of['ece']:.3f} · {'yes' if of['e013_buckets_ok'] else 'no'} |",
              f"| calibration intercept / slope | {mo['calibration_line']['intercept']:+.3f} / {mo['calibration_line']['slope']:.2f} | "
              f"{of['calibration_line']['intercept']:+.3f} / {of['calibration_line']['slope']:.2f} |",
              f"| Spearman ρ(p, 1h return) | {mo['rho_p_vs_return']:+.4f} | {of['rho_p_vs_return']:+.4f} |",
              f"| accuracy at 0.5 (naive {mo['naive_accuracy']:.3f}) | {mo['accuracy_at_0_5']:.3f} | {of['accuracy_at_0_5']:.3f} |",
              f"| return edge, p>0.5 minus p<0.5 (descriptive) | {100 * mo['return_edge']['point']:+.4f}% [{100 * mo['return_edge']['ci95'][0]:+.4f}, {100 * mo['return_edge']['ci95'][1]:+.4f}] | "
              f"{100 * of['return_edge']['point']:+.4f}% [{100 * of['return_edge']['ci95'][0]:+.4f}, {100 * of['return_edge']['ci95'][1]:+.4f}] |",
              f"| gross signed return per hour vs a 0.10% round trip (descriptive) | {100 * mo['gross_signed_return_per_hour']:+.4f}% | "
              f"{100 * of['gross_signed_return_per_hour']:+.4f}% |", "",
              f"Brier(base rate) − Brier(model): {bm['diff']:+.6f} [{bm['ci_low']:+.6f}, {bm['ci_high']:+.6f}] · "
              f"Brier(one-feature) − Brier(model): {fm['diff']:+.6f} [{fm['ci_low']:+.6f}, {fm['ci_high']:+.6f}] (positive = model better)", "",
              "Per year, model skill vs the base rate: " + "; ".join(f"{yr} {v['skill_vs_base_rate']:+.4f}" for yr, v in mo["by_year"].items()), ""]
    v = r["verdict"]
    L += ["## Pre-registered hypotheses", ""] + [f"- {k}: **{'HOLDS' if ok else 'FAILS'}**" for k, ok in v.items() if k != "positive_years"]
    L += [f"- (years with positive skill: {v['positive_years']} of 8)", "",
          "*Research-only and hypothesis-generating: about ten directional experiments, E011 above all, have seen these rows. "
          "Whatever the verdict, the live BUY/HOLD/SELL signal, scoring 0.2.0, move_size_1h_v1 and the checkpoints are unchanged, "
          "and nothing is combined with the move-size track.*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E032")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
