"""
E018 -- feature redundancy, group ablation, and how many features the 1h move-size model
actually needs (master plan sections 14-19).

    python -m agent.research.feature_count --experiment E018

The 1h move-size model (E012 + E013 Platt) is the only model in this project that has ever
passed a pre-registered out-of-sample criterion, and it carries nine inputs -- four of which
measure volatility and two measure trade intensity. This asks whether it needs them.

Everything except the feature list is held exactly at E013's settings, and every variant is
scored on IDENTICAL test rows: the frame is restricted once to the hours where all nine
inputs exist, and the folds are built once and reused. A difference between two variants can
therefore only come from the features.

Selection (greedy forward, by out-of-sample Brier) happens on the EXPLORATION test rows.
Those rows are out-of-sample with respect to fitting but in-sample with respect to selection,
which is why the number that decides anything is measured on the VALIDATION period, which no
selection step touches. The sealed holdout is never read.

Pre-registration: research/experiments/E018_feature_count_move_size.json (committed before
this ran). The decision rule is the one-standard-error rule stated there.
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
from agent.research.metrics import block_bootstrap_estimates, brier_score, log_loss, reliability_table
from agent.research.model_test import LogisticModel, PlattCalibrator, build_frame
from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward
from agent.scoring.scorer import SCORING_VERSION
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

HORIZON = 1
THRESHOLD = 0.0025
C = 0.1
N_BOOT = 2000
BLOCK = 48
SEED = 31

FULL = ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168",
        "trades_rel_24h", "trades_rel_168h", "hour_sin", "hour_cos", "is_weekend"]
LOG_FEATURES = ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168", "trades_rel_24h", "trades_rel_168h"]
GROUPS_UNDER_TEST = {
    "volatility": ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168"],
    "trade_intensity": ["trades_rel_24h", "trades_rel_168h"],
    "calendar": ["hour_sin", "hour_cos", "is_weekend"],
}


# ---------------------------------------------------------------- data
def prepare() -> tuple[pd.DataFrame, WalkForwardSpec, list]:
    """The E013 frame and folds, restricted to hours where every one of the nine inputs exists."""
    df, _ = build_frame(HORIZON, [], FULL, "large_move", THRESHOLD)
    attrs = dict(df.attrs)
    for c in LOG_FEATURES:
        bad = int((df[c].dropna() <= 0).sum())
        if bad:
            logger.warning("%s: %d non-positive values treated as missing before log-transform", c, bad)
        df[c] = np.log(df[c].where(df[c] > 0))
    # Restrict ONCE so that a variant with fewer inputs cannot quietly gain rows that the
    # full model had to drop. Every variant then trains, calibrates and is scored on the same hours.
    common = df[FULL + ["y"]].dropna().index
    df = df.loc[common]
    df.attrs.update(attrs)
    spec = WalkForwardSpec(horizon_hours=HORIZON, scheme="expanding", min_train_days=365,
                           test_block_days=90, embargo_hours=24, calib_days=90)
    folds = make_folds(common, spec)
    return df, spec, folds


# ---------------------------------------------------------------- one variant
def evaluate(df: pd.DataFrame, spec, folds, cols: list[str], cache: dict) -> dict:
    """Walk-forward + Platt for one feature set; per-period metrics and the per-row predictions."""
    key = tuple(sorted(cols))
    if key in cache:
        return cache[key]
    fitted: list[LogisticModel] = []

    def make_model():
        m = LogisticModel(C=C)
        fitted.append(m)
        return m

    preds, _ = run_walk_forward(df, list(cols), "y", make_model, spec, folds=folds, make_calibrator=PlattCalibrator)
    joined = preds.join(df[["period", "fwd_%dh" % HORIZON]], how="left")
    per_fold = [m.coefficients(list(cols)) for m in fitted]
    out = {
        "features": list(cols), "n_features": len(cols), "rows": int(len(joined)),
        "coefficient_sign_agreement": {
            c: float(np.mean([np.sign(pf[c]) == np.sign(np.median([q[c] for q in per_fold])) for pf in per_fold]))
            for c in cols
        },
        "coefficients_median": {c: float(np.median([pf[c] for pf in per_fold])) for c in cols},
        "predictions": joined,
    }
    for period in ("exploration", "validation"):
        m = joined[joined["period"] == period]
        if len(m) == 0:
            out[period] = {"n": 0}
            continue
        p = m["p"].to_numpy(float)
        y = m["y"].to_numpy(float)
        size = np.abs(m["fwd_%dh" % HORIZON].to_numpy(float))
        base = float(np.mean(y))
        brier = brier_score(p, y)
        brier_base = brier_score(np.full(len(y), base), y)
        buckets, ece, _ = reliability_table(p, y)
        gaps = [abs(b.observed - b.mean_predicted) for b in buckets if b.n >= 100]
        out[period] = {
            "n": int(len(y)), "base_rate": base, "brier": brier, "brier_base_rate": brier_base,
            "skill": 1.0 - brier / brier_base, "log_loss": log_loss(p, y), "ece": ece,
            "rho_p_vs_abs_return": spearman(p, size),
            "max_bucket_gap_100": max(gaps) if gaps else float("nan"),
        }
    cache[key] = out
    return out


def paired_brier_se(a: dict, b: dict, period: str) -> tuple[float, float]:
    """
    (difference in Brier, block-bootstrap SD of that difference) for two variants on the same
    rows. Paired: each resample draws hour-blocks once and scores BOTH models on them, so the
    shared market noise cancels and what is left is the difference between the models.
    """
    pa, pb = a["predictions"], b["predictions"]
    ma = pa[pa["period"] == period]
    mb = pb[pb["period"] == period]
    if not ma.index.equals(mb.index):
        raise ValueError("variants were scored on different rows -- the paired comparison is invalid")
    stacked = np.column_stack([ma["p"].to_numpy(float), mb["p"].to_numpy(float), ma["y"].to_numpy(float)])

    def diff(arr):
        return brier_score(arr[:, 0], arr[:, 2]) - brier_score(arr[:, 1], arr[:, 2])

    point, estimates = block_bootstrap_estimates(stacked, diff, block=BLOCK, n_boot=N_BOOT, seed=SEED)
    return point, (float(np.std(estimates, ddof=1)) if len(estimates) else float("nan"))


# ---------------------------------------------------------------- the four questions
def redundancy(df: pd.DataFrame) -> dict:
    """Q1: how much do the nine inputs repeat each other? Descriptive only, exploration rows."""
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler

    expl = df[df["period"] == "exploration"][FULL].dropna()
    corr = {a: {b: round(spearman(expl[a].to_numpy(), expl[b].to_numpy()), 3) for b in FULL} for a in FULL}
    # variance inflation: how well each input is explained by the other eight (linear, standardised)
    X = StandardScaler().fit_transform(expl.to_numpy(float))
    vif = {}
    for i, name in enumerate(FULL):
        others = np.delete(X, i, axis=1)
        r2 = LinearRegression().fit(others, X[:, i]).score(others, X[:, i])
        vif[name] = round(float(1.0 / max(1e-12, 1.0 - r2)), 2)
    pairs = sorted(((abs(corr[a][b]), a, b) for i, a in enumerate(FULL) for b in FULL[i + 1:]), reverse=True)[:6]
    return {"spearman": corr, "vif": vif,
            "most_correlated_pairs": [{"a": a, "b": b, "abs_rho": round(v, 3)} for v, a, b in pairs],
            "rows": int(len(expl))}


def ablation(df, spec, folds, cache) -> dict:
    """Q2: does removing a whole group measurably hurt? Paired against the full nine."""
    full = evaluate(df, spec, folds, FULL, cache)
    out = {"full": {"n_features": full["n_features"],
                    "exploration": full["exploration"], "validation": full["validation"]}}
    for name, cols in GROUPS_UNDER_TEST.items():
        kept = [c for c in FULL if c not in cols]
        var = evaluate(df, spec, folds, kept, cache)
        d_expl, se_expl = paired_brier_se(var, full, "exploration")
        d_vali, se_vali = paired_brier_se(var, full, "validation")
        out["without_" + name] = {
            "features": kept, "n_features": len(kept),
            "exploration": var["exploration"], "validation": var["validation"],
            "brier_minus_full": {
                "exploration": {"diff": d_expl, "se": se_expl,
                                "sigma": d_expl / se_expl if se_expl else float("nan")},
                "validation": {"diff": d_vali, "se": se_vali,
                               "sigma": d_vali / se_vali if se_vali else float("nan")}},
            # pre-registered: a group carries information only if dropping it costs more than 1 SE
            "group_carries_information": bool(d_vali > se_vali),
        }
    return out


def forward_selection(df, spec, folds, cache) -> dict:
    """Q3: greedy forward selection by EXPLORATION out-of-sample Brier; validation is untouched."""
    selected: list[str] = []
    remaining = list(FULL)
    steps = []
    while remaining:
        scored = []
        for f in remaining:
            res = evaluate(df, spec, folds, selected + [f], cache)
            scored.append((res["exploration"]["brier"], f))
        scored.sort()
        best = scored[0][1]
        selected = selected + [best]
        res = evaluate(df, spec, folds, selected, cache)
        steps.append({
            "k": len(selected), "added": best, "set": list(selected),
            "exploration_brier": res["exploration"]["brier"], "exploration_skill": res["exploration"]["skill"],
            "validation_brier": res["validation"]["brier"], "validation_skill": res["validation"]["skill"],
            "validation_ece": res["validation"]["ece"], "validation_rho": res["validation"]["rho_p_vs_abs_return"],
            "validation_max_bucket_gap_100": res["validation"]["max_bucket_gap_100"],
            "candidates_this_step": [{"feature": f, "exploration_brier": b} for b, f in scored],
        })
        remaining.remove(best)
        logger.info("k=%d added %s  expl brier %.5f  vali brier %.5f", len(selected), best,
                    res["exploration"]["brier"], res["validation"]["brier"])
    return {"steps": steps}


def exact_dependence(df: pd.DataFrame) -> dict:
    """
    Is any input an exact function of the others? Checked, not assumed: after the declared log
    transforms, log(vol_ratio_24_168) should equal log(rv_24) - log(rv_168) by construction,
    which would mean the nine inputs contain only eight independent pieces of information.
    """
    e = df[df["period"] == "exploration"][FULL].dropna()
    resid = (e["vol_ratio_24_168"] - (e["rv_24"] - e["rv_168"])).abs().max()
    return {"identity": "log(vol_ratio_24_168) == log(rv_24) - log(rv_168)",
            "max_abs_residual": float(resid), "rows": int(len(e)),
            "exact_to_floating_point": bool(resid < 1e-9)}


def secondary_analysis(steps: list[dict], df, spec, folds, cache) -> dict:
    """
    NOT PRE-REGISTERED. Added after the pre-registered rule returned k = 9 and the per-step
    numbers showed why: the rule compares models with a PAIRED bootstrap, whose standard error
    shrinks as fast as the difference it is measuring. At k = 8 the validation Brier is worse
    by 0.00001 -- 0.005% in relative terms -- with a paired SE of 0.000005, so the rule calls it
    two standard errors worse. The rule therefore answers "are these two models statistically
    distinguishable on 13,127 paired rows?" (almost always yes) rather than "does the extra
    feature matter?". Breiman's classical one-standard-error rule uses the standard error of
    the BEST MODEL'S OWN estimate, unpaired; that version is computed here, alongside a plain
    practical threshold. Both are reported as secondary and neither overrides the primary result.
    """
    best = max(steps, key=lambda s: s["validation_skill"])
    ref = evaluate(df, spec, folds, best["set"], cache)
    pr = ref["predictions"]
    m = pr[pr["period"] == "validation"]
    stacked = np.column_stack([m["p"].to_numpy(float), m["y"].to_numpy(float)])
    point, est = block_bootstrap_estimates(stacked, lambda a: brier_score(a[:, 0], a[:, 1]),
                                           block=BLOCK, n_boot=N_BOOT, seed=SEED)
    se_unpaired = float(np.std(est, ddof=1))
    classical = min((s for s in steps if s["validation_brier"] <= point + se_unpaired),
                    key=lambda s: s["k"])
    best_skill = best["validation_skill"]
    practical = {}
    for frac in (0.99, 0.95):
        hit = [s for s in steps if s["validation_skill"] >= frac * best_skill]
        practical["k_reaching_%d_pct_of_best_skill" % int(frac * 100)] = min(s["k"] for s in hit)
    # the exactly-redundant input, removed
    eight = [c for c in FULL if c != "vol_ratio_24_168"]
    var8 = evaluate(df, spec, folds, eight, cache)
    d8, se8 = paired_brier_se(var8, evaluate(df, spec, folds, FULL, cache), "validation")
    return {
        "why": "the pre-registered paired rule measures distinguishability, not importance",
        "unpaired_se_of_best_validation_brier": se_unpaired,
        "classical_one_se_rule_k": classical["k"], "classical_one_se_rule_set": classical["set"],
        "classical_one_se_rule_validation": {k: classical[k] for k in
                                             ("validation_brier", "validation_skill", "validation_ece", "validation_rho",
                                              "validation_max_bucket_gap_100")},
        "practical_thresholds": practical,
        "drop_the_exactly_redundant_input": {
            "set": eight, "validation_brier": var8["validation"]["brier"],
            "validation_skill": var8["validation"]["skill"], "validation_ece": var8["validation"]["ece"],
            "validation_rho": var8["validation"]["rho_p_vs_abs_return"],
            "brier_minus_full": d8, "paired_se": se8,
            "relative_brier_change": d8 / evaluate(df, spec, folds, FULL, cache)["validation"]["brier"],
        },
    }


def decide(steps: list[dict], df, spec, folds, cache) -> dict:
    """
    The PRE-REGISTERED one-standard-error rule: k* has the best validation skill; the answer is
    the smallest k whose validation skill is within 1 SE (paired block bootstrap vs k*) of it.
    """
    best = max(steps, key=lambda s: s["validation_skill"])
    ref = evaluate(df, spec, folds, best["set"], cache)
    within = []
    for s in steps:
        var = evaluate(df, spec, folds, s["set"], cache)
        diff, se = paired_brier_se(var, ref, "validation")  # positive = this set is WORSE than k*
        s["brier_minus_best"] = {"diff": diff, "se": se, "sigma": diff / se if se else float("nan")}
        s["within_1se_of_best"] = bool(diff <= se)
        if s["within_1se_of_best"]:
            within.append(s)
    chosen = min(within, key=lambda s: s["k"])
    full = evaluate(df, spec, folds, FULL, cache)
    gap = chosen["validation_max_bucket_gap_100"]
    return {
        "k_star": best["k"], "k_star_set": best["set"], "k_star_validation_skill": best["validation_skill"],
        "chosen_k": chosen["k"], "chosen_set": chosen["set"],
        "chosen_validation": {k: chosen[k] for k in
                              ("validation_brier", "validation_skill", "validation_ece",
                               "validation_rho", "validation_max_bucket_gap_100")},
        "C1_calibrated": bool(chosen["validation_ece"] <= 0.03 and (np.isnan(gap) or gap <= 0.05)),
        "C2_ranking_preserved": bool(
            abs(chosen["validation_rho"] - full["validation"]["rho_p_vs_abs_return"]) <= 0.02),
        "full_nine_validation_rho": full["validation"]["rho_p_vs_abs_return"],
        "full_nine_validation_brier": full["validation"]["brier"],
        "relative_brier_vs_full": (full["validation"]["brier"] - chosen["validation_brier"]) / full["validation"]["brier"],
    }


# ---------------------------------------------------------------- report
def render(res: dict) -> str:
    L = ["# E018 -- how many features does the 1h move-size model need?", "",
         "Generated %s  |  pipeline %s  |  snapshot %s" % (res["generated_at"], res["pipeline_version"], res["snapshot"]),
         "Target: |1h return| > %.2f%%.  Settings identical to E013 except the feature list." % (THRESHOLD * 100),
         "Folds: %d; every variant scored on the same %d hours." % (res["folds"], res["rows_common"]), ""]

    L += ["## Q1 -- redundancy among the nine inputs (exploration, descriptive)", "",
          "| input | variance inflation | most like |", "|---|---|---|"]
    r = res["redundancy"]
    for f in FULL:
        partner = max((x for x in FULL if x != f), key=lambda x: abs(r["spearman"][f][x]))
        vif = "exactly determined by the others" if r["vif"][f] > 1e6 else "%.1f" % r["vif"][f]
        L.append("| `%s` | %s | `%s` (rho %+.2f) |" % (f, vif, partner, r["spearman"][f][partner]))
    L += ["", "Highest absolute correlations: " +
          ", ".join("`%s`/`%s` %.2f" % (p["a"], p["b"], p["abs_rho"]) for p in r["most_correlated_pairs"]), ""]
    ed = res["exact_dependence"]
    L += ["**One input is not new information at all.** `%s`, to floating point "
          "(largest disagreement %.1e over %d hours). After the declared log transforms the "
          "nine inputs carry **eight** independent pieces of information; the ninth is their "
          "arithmetic. L2 regularisation keeps the predictions well behaved, but the individual "
          "coefficients of the three volatility terms cannot be read separately." % (
              ed["identity"], ed["max_abs_residual"], ed["rows"]), ""]

    L += ["## Q2 -- group ablation (paired against all nine)", "",
          "| variant | validation Brier | skill | Brier minus full | in SEs | carries information? |",
          "|---|---|---|---|---|---|"]
    a = res["ablation"]
    L.append("| all nine | %.5f | %+.4f | -- | -- | -- |" % (a["full"]["validation"]["brier"], a["full"]["validation"]["skill"]))
    for name in GROUPS_UNDER_TEST:
        v = a["without_" + name]
        d = v["brier_minus_full"]["validation"]
        L.append("| without %s | %.5f | %+.4f | %+.5f | %+.1f | %s |" % (
            name, v["validation"]["brier"], v["validation"]["skill"], d["diff"], d["sigma"],
            "YES" if v["group_carries_information"] else "no"))

    L += ["", "## Q3 -- forward selection (order fixed on exploration only)", "",
          "| k | added | exploration Brier | validation Brier | validation skill | ECE | rho | within 1 SE of best? |",
          "|---|---|---|---|---|---|---|---|"]
    for s in res["forward_selection"]["steps"]:
        L.append("| %d | `%s` | %.5f | %.5f | %+.4f | %.3f | %+.3f | %s |" % (
            s["k"], s["added"], s["exploration_brier"], s["validation_brier"], s["validation_skill"],
            s["validation_ece"], s["validation_rho"], "yes" if s.get("within_1se_of_best") else "no"))

    d = res["decision"]
    L += ["", "## Decision (pre-registered one-standard-error rule)", "",
          "- best validation skill at **k = %d**: %s" % (d["k_star"], ", ".join("`%s`" % c for c in d["k_star_set"])),
          "- smallest k within 1 SE: **k = %d** -> %s" % (d["chosen_k"], ", ".join("`%s`" % c for c in d["chosen_set"])),
          "- validation Brier %.5f, skill %+.4f, ECE %.3f, rho %+.3f" % (
              d["chosen_validation"]["validation_brier"], d["chosen_validation"]["validation_skill"],
              d["chosen_validation"]["validation_ece"], d["chosen_validation"]["validation_rho"]),
          "- C1 calibrated: **%s**; C2 ranking preserved (within 0.02 of the nine-feature rho %+.3f): **%s**" % (
              "PASS" if d["C1_calibrated"] else "FAIL", d["full_nine_validation_rho"],
              "PASS" if d["C2_ranking_preserved"] else "FAIL"),
          "- relative Brier vs all nine: %+.2f%% (tripwire at +3%%: %s)" % (
              d["relative_brier_vs_full"] * 100,
              "FIRED -- investigate" if d["relative_brier_vs_full"] > 0.03 else "not fired"), ""]

    s2 = res["secondary_analysis"]
    dr = s2["drop_the_exactly_redundant_input"]
    L += ["## Secondary analysis -- NOT pre-registered, and why it was added", "",
          "The pre-registered rule compares two models with a **paired** bootstrap, whose standard",
          "error shrinks as fast as the difference it is measuring. At k = 8 the validation Brier is",
          "worse by 0.00001 -- 0.005% relative -- with a paired standard error of 0.000005, so the rule",
          "calls it two standard errors worse. It is answering *are these two models statistically",
          "distinguishable on 13,127 paired rows?* (nearly always yes) rather than *does the extra",
          "feature matter?*. Breiman's classical one-standard-error rule uses the standard error of the",
          "best model's own estimate, unpaired. Both variants below are secondary; the pre-registered",
          "answer above stands as the primary result.", "",
          "| view | answer | validation Brier | skill |", "|---|---|---|---|",
          "| pre-registered, paired | k = %d | %.5f | %+.4f |" % (
              res["decision"]["chosen_k"], res["decision"]["chosen_validation"]["validation_brier"],
              res["decision"]["chosen_validation"]["validation_skill"]),
          "| classical one-SE (unpaired SE = %.5f) | k = %d | %.5f | %+.4f |" % (
              s2["unpaired_se_of_best_validation_brier"], s2["classical_one_se_rule_k"],
              s2["classical_one_se_rule_validation"]["validation_brier"],
              s2["classical_one_se_rule_validation"]["validation_skill"]),
          "| smallest k with >= 99%% of the best skill | k = %d | | |" % s2["practical_thresholds"]["k_reaching_99_pct_of_best_skill"],
          "| smallest k with >= 95%% of the best skill | k = %d | | |" % s2["practical_thresholds"]["k_reaching_95_pct_of_best_skill"],
          "",
          "Dropping the mathematically redundant input (`vol_ratio_24_168`), leaving eight:",
          "validation Brier %.5f (%+.4f%% relative to all nine), skill %+.4f, ECE %.3f, rho %+.3f." % (
              dr["validation_brier"], dr["relative_brier_change"] * 100, dr["validation_skill"],
              dr["validation_ece"], dr["validation_rho"]), ""]

    L += ["## Q4 -- coefficient sign stability across folds (all nine)", "",
          "| input | sign agreement | median coefficient |", "|---|---|---|"]
    st = res["stability_full"]
    for f in FULL:
        L.append("| `%s` | %.2f | %+.3f |" % (f, st["coefficient_sign_agreement"][f], st["coefficients_median"][f]))
    return "\n".join(L) + "\n"


def main(experiment: str) -> Path:
    df, spec, folds = prepare()
    cache: dict = {}
    logger.info("frame: %d common hours, %d folds", len(df), len(folds))
    red = redundancy(df)
    abl = ablation(df, spec, folds, cache)
    fwd = forward_selection(df, spec, folds, cache)
    dec = decide(fwd["steps"], df, spec, folds, cache)
    sec = secondary_analysis(fwd["steps"], df, spec, folds, cache)
    exact = exact_dependence(df)
    full = evaluate(df, spec, folds, FULL, cache)
    res = {
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION, "scoring_version": SCORING_VERSION,
        "snapshot": df.attrs.get("snapshot", "unknown"), "horizon": HORIZON, "threshold": THRESHOLD,
        "spec": spec.__dict__, "folds": len(folds), "rows_common": int(len(df)),
        "features_under_test": FULL, "log_features": LOG_FEATURES,
        "n_boot": N_BOOT, "block_hours": BLOCK, "seed": SEED,
        "redundancy": red, "exact_dependence": exact, "ablation": abl,
        "forward_selection": fwd, "decision": dec, "secondary_analysis": sec,
        "stability_full": {"coefficient_sign_agreement": full["coefficient_sign_agreement"],
                           "coefficients_median": full["coefficients_median"]},
        "variants_evaluated": len(cache),
    }
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "feature_count.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "feature_count.md").write_text(render(res), encoding="utf-8")
    return out_dir / "feature_count.md"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E018")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(main(args.experiment))
