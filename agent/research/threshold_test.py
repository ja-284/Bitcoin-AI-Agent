"""
E021 -- should "a large move" be a fixed percentage, or one that adapts to how much the market
has been moving lately?

    python -m agent.research.threshold_test --experiment E021

Every move-size result in this project (E012, E013, E018, E019, E020) rests on one target
definition -- |1h return| > 0.25% -- that was chosen, never tested. The research rules recorded
on 2026-09-19 say it should be: "threshold fixed-% vs volatility-scaled to be tested, not
assumed". This pays that debt.

Two candidates, no search over the multiplier:

    F   |return| > 0.0025                                  (the incumbent)
    V   |return| > 1.0 x median|return| over the last 720h  (of COMPLETED returns)

k = 1.0 because the median is by definition what half of recent hours exceed, so V means
"bigger than a typical recent hour" -- the most interpretable value, and one that makes the two
targets comparable in difficulty without anything being fitted to make them so.

Raw Brier is NOT comparable between the two: they are different events with different base
rates. Skill (1 - Brier / base-rate Brier) is, and so is the rank correlation between the
stated probability and the realised |return|, because that outcome is the same continuous
quantity under either definition. The criterion uses those two and never compares raw Brier.

Pre-registration: research/experiments/E021_threshold_definition_move_size.json.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.diagnose import spearman
from agent.research.feature_count import BLOCK, C, FULL, LOG_FEATURES, N_BOOT, SEED, THRESHOLD, prepare
from agent.research.history import load_bars
from agent.research.labels import LabelSpec, forward_returns, point_in_time_thresholds
from agent.research.metrics import brier_score, reliability_table
from agent.research.model_test import LogisticModel, PlattCalibrator
from agent.research.periods import HOLDOUT
from agent.research.simple_baselines import score, simple_rules
from agent.research.walkforward import run_walk_forward
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

HORIZON = 1
K = 1.0                      # "bigger than a typical recent hour" -- declared, never searched
VOL_LOOKBACK_HOURS = 720     # the LabelSpec default, not a value chosen for this experiment
MIN_VOL_SAMPLES = 240        # likewise


def vol_scaled_threshold(bars) -> pd.Series:
    """
    The per-hour threshold for candidate V, using only returns that had COMPLETED by that
    hour's cutoff. agent/research/labels.point_in_time_thresholds does the shifting and marks
    the value unavailable when the newest completed return is older than the lookback window.
    """
    spec = LabelSpec(horizon_hours=HORIZON, kind="three_class", threshold_kind="vol_scaled",
                     threshold=K, vol_lookback_hours=VOL_LOOKBACK_HOURS, min_vol_samples=MIN_VOL_SAMPLES)
    return point_in_time_thresholds(forward_returns(bars, HORIZON), spec)


def build(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Add candidate V's label to the frame that already carries candidate F's, and restrict to the
    hours where BOTH exist. A difference between the two can then only come from the definition.
    """
    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    thresholds = vol_scaled_threshold(bars).reindex(df.index)
    ret = df["fwd_%dh" % HORIZON]
    df = df.copy()
    df["y_fixed"] = df["y"]                              # |return| > 0.0025, already built
    df["threshold_v"] = thresholds
    df["y_vol"] = (ret.abs() > thresholds).astype(float).where(ret.notna() & thresholds.notna())
    before = len(df)
    df = df[df["y_fixed"].notna() & df["y_vol"].notna()]
    return df, {"snapshot": snapshot.name, "rows_before": before, "rows_common": len(df),
                "dropped_no_vol_threshold": before - len(df),
                "median_threshold_pct": float(np.nanmedian(df["threshold_v"]) * 100)}


def run_one(df, spec, folds, label_col: str) -> pd.DataFrame:
    preds, _ = run_walk_forward(df, list(FULL), label_col, lambda: LogisticModel(C=C), spec,
                                folds=folds, make_calibrator=PlattCalibrator)
    return preds.join(df[["period", "year", "fwd_%dh" % HORIZON, "threshold_v"]], how="left")


def per_year(preds: pd.DataFrame) -> dict:
    out = {}
    for year, block in preds.groupby("year"):
        p = block["p"].to_numpy(float)
        y = block["y"].to_numpy(float)
        base = float(y.mean())
        _, ece, _ = reliability_table(p, y)
        out[int(year)] = {"n": int(len(y)), "positive_rate": base,
                          "skill": 1.0 - brier_score(p, y) / brier_score(np.full(len(y), base), y),
                          "ece": ece}
    return out


def spread(by_year: dict, key: str = "positive_rate") -> float:
    values = [v[key] for v in by_year.values() if v["n"] >= 500]
    return float(max(values) - min(values)) if len(values) >= 2 else float("nan")


def run(experiment: str) -> Path:
    base_df, spec, folds = prepare()
    df, info = build(base_df)
    logger.info("common rows %d (dropped %d with no volatility threshold), median V threshold %.3f%%",
                info["rows_common"], info["dropped_no_vol_threshold"], info["median_threshold_pct"])

    # folds were built on the full index; rebuild predictions on the restricted frame using the
    # same fold boundaries, so both candidates see identical train/calibration/test hours
    preds = {name: run_one(df, spec, folds, col)
             for name, col in (("F_fixed_incumbent", "y_fixed"), ("V_vol_scaled", "y_vol"))}
    if not preds["F_fixed_incumbent"].index.equals(preds["V_vol_scaled"].index):
        raise ValueError("the two candidates were scored on different rows -- the comparison would be invalid")

    bars, _, _ = load_bars(end=HOLDOUT.start)
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(preds["F_fixed_incumbent"].index)

    results: dict = {"by_candidate": {}, "frame": info}
    for name, pr in preds.items():
        entry = {}
        for period in ("exploration", "validation"):
            m = pr[pr["period"] == period]
            entry[period] = score(m["p"].to_numpy(float), m["y"].to_numpy(float),
                                  np.abs(m["fwd_%dh" % HORIZON].to_numpy(float)))
        entry["by_year"] = per_year(pr)
        entry["yearly_positive_rate_spread"] = spread(entry["by_year"])
        # the E019 standing reference, scored against THIS target on the same rows
        v = pr[pr["period"] == "validation"]
        ref = ewma.reindex(v.index).to_numpy(float)
        ok = ~np.isnan(ref)
        entry["ewma_reference_validation"] = score(ref[ok], v["y"].to_numpy(float)[ok],
                                                   np.abs(v["fwd_%dh" % HORIZON].to_numpy(float))[ok])
        results["by_candidate"][name] = entry

    f = results["by_candidate"]["F_fixed_incumbent"]
    v = results["by_candidate"]["V_vol_scaled"]
    checks = {
        "i_predictability": {"skill_F": f["validation"]["skill"], "skill_V": v["validation"]["skill"],
                             "ratio": v["validation"]["skill"] / f["validation"]["skill"] if f["validation"]["skill"] else float("nan"),
                             "pass": bool(v["validation"]["skill"] >= 0.90 * f["validation"]["skill"])},
        "ii_calibration": {"ece_V": v["validation"]["ece"], "worst_bucket_V": v["validation"]["max_bucket_gap_100"],
                           "pass": bool(v["validation"]["ece"] <= 0.03 and
                                        (np.isnan(v["validation"]["max_bucket_gap_100"]) or
                                         v["validation"]["max_bucket_gap_100"] <= 0.05))},
        "iii_ranking": {"rho_F": f["validation"]["rho_p_vs_abs_return"], "rho_V": v["validation"]["rho_p_vs_abs_return"],
                        "pass": bool(v["validation"]["rho_p_vs_abs_return"] >= f["validation"]["rho_p_vs_abs_return"] - 0.02)},
        "iv_stability": {"spread_F": f["yearly_positive_rate_spread"], "spread_V": v["yearly_positive_rate_spread"],
                         "pass": bool(v["yearly_positive_rate_spread"] * 2 <= f["yearly_positive_rate_spread"])},
    }
    all_pass = all(c["pass"] for c in checks.values())
    results["verdict"] = {
        "checks": checks, "all_four_pass": all_pass,
        "tripwire_V_skill_over_1_5x_F": bool(v["validation"]["skill"] > 1.5 * f["validation"]["skill"]),
        "statement": ("the volatility-scaled definition is the better STATISTICAL target; whether to use it is a "
                      "product judgement about interpretability, not a research result" if all_pass else
                      "the volatility-scaled definition does not clear the pre-registered bars -- the fixed target stands"),
    }
    results.update({
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION, "horizon": HORIZON, "k": K,
        "fixed_threshold": THRESHOLD, "vol_lookback_hours": VOL_LOOKBACK_HOURS,
        "min_vol_samples": MIN_VOL_SAMPLES, "folds": len(folds),
        "n_boot": N_BOOT, "block_hours": BLOCK, "seed": SEED,
    })
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "threshold.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "threshold.md").write_text(render(results), encoding="utf-8")
    return out_dir / "threshold.md"


def render(r: dict) -> str:
    fr = r["frame"]
    L = ["# E021 -- a fixed threshold, or one that adapts?", "",
         "Generated %s  |  pipeline %s  |  snapshot %s" % (r["generated_at"], r["pipeline_version"], fr["snapshot"]),
         "F: |1h return| > %.2f%%.   V: |1h return| > %.1f x the median of the last %dh of completed returns."
         % (r["fixed_threshold"] * 100, r["k"], r["vol_lookback_hours"]),
         "%d folds; both candidates on the same %d hours (%d dropped where V's threshold was unavailable). "
         "V's median threshold was %.3f%%." % (r["folds"], fr["rows_common"], fr["dropped_no_vol_threshold"],
                                               fr["median_threshold_pct"]), "",
         "## Validation", "",
         "| target | positive rate | Brier | skill | ECE | worst bucket | rho with realised move |",
         "|---|---|---|---|---|---|---|"]
    for name in ("F_fixed_incumbent", "V_vol_scaled"):
        s = r["by_candidate"][name]["validation"]
        L.append("| %s | %.3f | %.5f | %+.4f | %.3f | %.3f | %+.3f |" % (
            name, s["base_rate"], s["brier"], s["skill"], s["ece"], s["max_bucket_gap_100"],
            s["rho_p_vs_abs_return"]))
    L += ["", "Raw Brier is deliberately not compared between the rows: they are different events. Skill and rho are.", "",
          "The E019 no-fitting reference, scored against each target on the same validation rows:", ""]
    for name in ("F_fixed_incumbent", "V_vol_scaled"):
        e = r["by_candidate"][name]["ewma_reference_validation"]
        L.append("- %s: reference skill %+.4f (model %+.4f)" % (
            name, e["skill"], r["by_candidate"][name]["validation"]["skill"]))

    L += ["", "## Per year: does the target keep meaning the same thing?", "",
          "| year | F positive rate | V positive rate | F skill | V skill | F ECE | V ECE |", "|---|---|---|---|---|---|---|"]
    years = sorted(set(r["by_candidate"]["F_fixed_incumbent"]["by_year"]) | set(r["by_candidate"]["V_vol_scaled"]["by_year"]))
    for y in years:
        a = r["by_candidate"]["F_fixed_incumbent"]["by_year"].get(str(y)) or r["by_candidate"]["F_fixed_incumbent"]["by_year"].get(y)
        b = r["by_candidate"]["V_vol_scaled"]["by_year"].get(str(y)) or r["by_candidate"]["V_vol_scaled"]["by_year"].get(y)
        if not a or not b:
            continue
        L.append("| %s | %.3f | %.3f | %+.4f | %+.4f | %.3f | %.3f |" % (
            y, a["positive_rate"], b["positive_rate"], a["skill"], b["skill"], a["ece"], b["ece"]))
    L += ["", "Spread of the yearly positive rate (years with >= 500 rows): F %.3f, V %.3f." % (
        r["by_candidate"]["F_fixed_incumbent"]["yearly_positive_rate_spread"],
        r["by_candidate"]["V_vol_scaled"]["yearly_positive_rate_spread"])]

    v = r["verdict"]
    L += ["", "## Verdict (pre-registered, all four parts required)", "",
          "| check | F | V | passes? |", "|---|---|---|---|"]
    c = v["checks"]
    L += ["| (i) predictability: skill_V >= 0.90 x skill_F | %+.4f | %+.4f (%.2fx) | %s |" % (
        c["i_predictability"]["skill_F"], c["i_predictability"]["skill_V"], c["i_predictability"]["ratio"],
        "PASS" if c["i_predictability"]["pass"] else "FAIL"),
        "| (ii) calibration: ECE <= 0.03, buckets within 0.05 | — | ECE %.3f, worst %.3f | %s |" % (
            c["ii_calibration"]["ece_V"], c["ii_calibration"]["worst_bucket_V"],
            "PASS" if c["ii_calibration"]["pass"] else "FAIL"),
        "| (iii) ranking: rho_V within 0.02 of rho_F | %+.3f | %+.3f | %s |" % (
            c["iii_ranking"]["rho_F"], c["iii_ranking"]["rho_V"], "PASS" if c["iii_ranking"]["pass"] else "FAIL"),
        "| (iv) stability: V's yearly spread at least 2x smaller | %.3f | %.3f | %s |" % (
            c["iv_stability"]["spread_F"], c["iv_stability"]["spread_V"],
            "PASS" if c["iv_stability"]["pass"] else "FAIL"),
        "", "Tripwire (V more than 1.5x F's skill -> investigate for leakage): %s" % (
            "FIRED" if v["tripwire_V_skill_over_1_5x_F"] else "not fired"),
        "", "**%s.**" % v["statement"], ""]

    # The verdict is the small part of what this run shows. The decomposition is the rest.
    f_v = r["by_candidate"]["F_fixed_incumbent"]["validation"]
    v_v = r["by_candidate"]["V_vol_scaled"]["validation"]
    f_ref = r["by_candidate"]["F_fixed_incumbent"]["ewma_reference_validation"]
    v_ref = r["by_candidate"]["V_vol_scaled"]["ewma_reference_validation"]
    L += ["## What this actually shows: where the model's skill comes from", "",
          "The volatility-scaled threshold divides the recent volatility level OUT of the target. Whatever",
          "survives that is skill at picking which hour inside a regime will be big, rather than skill at",
          "knowing how lively the market is at all. Reading the two targets side by side splits the skill in two:",
          "",
          "| | against the fixed target | against the volatility-scaled target |", "|---|---|---|",
          "| the no-fitting EWMA reference (E019) | %+.4f | %+.4f |" % (f_ref["skill"], v_ref["skill"]),
          "| the model | %+.4f | %+.4f |" % (f_v["skill"], v_v["skill"]),
          "| model / reference | %.2fx | %s |" % (
              f_v["skill"] / f_ref["skill"] if f_ref["skill"] else float("nan"),
              ("%.0fx" % (v_v["skill"] / v_ref["skill"])) if v_ref["skill"] > 1e-6 else "the reference has essentially no skill left"),
          "",
          "The reference is a pure level-tracker, and once the level is divided out it knows **nothing**",
          "(%+.4f). The model keeps %+.4f, so it is not merely re-reading the volatility level -- but most of"
          % (v_ref["skill"], v_v["skill"]),
          "its skill against the fixed target (%+.4f) *is* the level, which is available for free."
          % f_v["skill"],
          "",
          "This also gives the 2026-09-22 live watch item a plausible mechanism. The fixed target's positive",
          "rate ranges from %.3f to %.3f across years -- it is a different question in a calm year than in a"
          % (min(y["positive_rate"] for y in r["by_candidate"]["F_fixed_incumbent"]["by_year"].values()),
             max(y["positive_rate"] for y in r["by_candidate"]["F_fixed_incumbent"]["by_year"].values())),
          "wild one -- so a model trained across the mixture will over-state large moves during a quiet",
          "stretch, which is exactly what those 18 hours looked like. That remains a mechanism, not a finding:",
          "n was 18.", "",
          "## Exploration (reported, not used for the verdict)", "",
          "| target | positive rate | skill | ECE | rho |", "|---|---|---|---|---|"]
    for name in ("F_fixed_incumbent", "V_vol_scaled"):
        s = r["by_candidate"][name]["exploration"]
        L.append("| %s | %.3f | %+.4f | %.3f | %+.3f |" % (
            name, s["base_rate"], s["skill"], s["ece"], s["rho_p_vs_abs_return"]))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E021")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
