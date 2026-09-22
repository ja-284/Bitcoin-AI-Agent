"""
E022 -- which inputs carry the part of the skill that is actually the model's?

    python -m agent.research.timing_features --experiment E022

E021 split the move-size model's skill in two. Against the FIXED 0.25% target, a 24-hour EWMA
that needs no fitting already scores +0.0398 and the model +0.0983. Against a VOLATILITY-SCALED
target -- which divides the recent volatility level out of the question -- the EWMA scores
+0.0003, nothing at all, and the model still scores +0.0736. That remainder is skill at
within-regime TIMING, and it is the only part of the model that is not freely available.

Nobody has asked which inputs provide it. E018 asked the feature question against the fixed
target, where the answer is contaminated: an input can look essential there merely by proxying
the volatility level. Running the identical machinery against the scaled target isolates the
part that is genuinely the model's.

Exploratory. Three predictions are pre-registered so the run can be wrong; nothing is adopted,
nothing is decided, and the sealed holdout is not read.

Pre-registration: research/experiments/E022_within_regime_timing_features.json.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.research.feature_count import FULL, GROUPS_UNDER_TEST, ablation, evaluate, forward_selection, prepare
from agent.research.threshold_test import build as add_vol_label
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

LEVEL_FEATURES = ["rv_24", "rv_168", "tr_mean_14_rel"]          # absolute volatility level
RELATIVE_FEATURES = ["vol_ratio_24_168", "trades_rel_24h", "trades_rel_168h",
                     "hour_sin", "hour_cos", "is_weekend"]      # everything else
E021_VALIDATION_SKILL = 0.07363   # tripwire reference
TRIPWIRE_TOLERANCE = 0.002


def order_of(steps: list[dict]) -> dict[str, int]:
    """feature -> the k at which forward selection picked it."""
    return {s["added"]: s["k"] for s in steps}


def check_predictions(f: dict, v: dict) -> dict:
    """
    The three predictions written down in the pre-registration, evaluated exactly as worded.
    Pure, so a test can prove that a prediction which should fail does fail -- otherwise
    "3 of 3 held" would only be evidence that the checker agrees with itself.
    """
    later = [c for c in LEVEL_FEATURES if v["selection_k"][c] > f["selection_k"][c]]
    earlier = [c for c in RELATIVE_FEATURES if v["selection_k"][c] < f["selection_k"][c]]
    return {
        "P1_level_later_and_relative_earlier": {
            "level_features_selected_later": later, "relative_features_selected_earlier": earlier,
            "holds": bool(later and earlier),
        },
        "P2_volatility_group_costs_less_than_40pct": {
            "cost_against_fixed": f["group_ablation_skill_cost"]["volatility"],
            "cost_against_scaled": v["group_ablation_skill_cost"]["volatility"],
            "holds": bool(v["group_ablation_skill_cost"]["volatility"] < 0.40),
        },
        "P3_first_pick_is_not_tr_mean_14_rel": {
            "first_against_fixed": f["selection_order"][0], "first_against_scaled": v["selection_order"][0],
            "holds": bool(v["selection_order"][0] != "tr_mean_14_rel"),
        },
    }


def run(experiment: str) -> Path:
    base_df, spec, folds = prepare()
    df, info = add_vol_label(base_df)
    logger.info("rows %d (%d dropped without a volatility threshold), %d folds",
                info["rows_common"], info["dropped_no_vol_threshold"], len(folds))

    cache: dict = {}
    results: dict = {"by_target": {}, "frame": info}
    for name, label in (("F_fixed", "y_fixed"), ("V_vol_scaled", "y_vol")):
        logger.info("=== %s ===", name)
        full = evaluate(df, spec, folds, FULL, cache, label)
        fwd = forward_selection(df, spec, folds, cache, label)
        abl = ablation(df, spec, folds, cache, label)
        results["by_target"][name] = {
            "validation": {k: full["validation"][k] for k in
                           ("n", "base_rate", "brier", "skill", "ece", "rho_p_vs_abs_return")},
            "exploration": {k: full["exploration"][k] for k in ("n", "base_rate", "brier", "skill", "ece")},
            "selection_order": [s["added"] for s in fwd["steps"]],
            "selection_k": order_of(fwd["steps"]),
            "skill_by_k": {s["k"]: round(s["validation_skill"], 4) for s in fwd["steps"]},
            "group_ablation_skill_cost": {
                g: round(1.0 - abl["without_" + g]["validation"]["skill"] / abl["full"]["validation"]["skill"], 4)
                if abl["full"]["validation"]["skill"] else float("nan")
                for g in GROUPS_UNDER_TEST
            },
            "coefficient_sign_agreement": full["coefficient_sign_agreement"],
            "coefficients_median": full["coefficients_median"],
        }

    f = results["by_target"]["F_fixed"]
    v = results["by_target"]["V_vol_scaled"]

    # --- tripwire: this run must reproduce E021's scaled-target skill
    drift = abs(v["validation"]["skill"] - E021_VALIDATION_SKILL)
    results["tripwire"] = {
        "e021_validation_skill": E021_VALIDATION_SKILL, "this_run": v["validation"]["skill"],
        "difference": drift, "tolerance": TRIPWIRE_TOLERANCE,
        "fired": bool(drift > TRIPWIRE_TOLERANCE),
    }

    results["predictions"] = check_predictions(f, v)
    held = [k for k, p in results["predictions"].items() if p["holds"]]
    results["summary"] = {
        "predictions_that_held": held, "n_held": len(held), "n_total": 3,
        "statement": ("the inputs that carry within-regime timing differ from the ones that carry the headline "
                      "skill" if len(held) >= 2 else
                      "the same inputs carry both: the decomposition is real about SKILL but says nothing useful "
                      "about FEATURES"),
    }
    results.update({
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION, "folds": len(folds),
        "level_features": LEVEL_FEATURES, "relative_features": RELATIVE_FEATURES,
        "variants_evaluated": len(cache),
    })
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "timing_features.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "timing_features.md").write_text(render(results), encoding="utf-8")
    return out_dir / "timing_features.md"


def render(r: dict) -> str:
    f, v = r["by_target"]["F_fixed"], r["by_target"]["V_vol_scaled"]
    L = ["# E022 -- which inputs carry the part of the skill that is ours?", "",
         "Generated %s  |  pipeline %s  |  %d folds, %d variants evaluated"
         % (r["generated_at"], r["pipeline_version"], r["folds"], r["variants_evaluated"]),
         "", "Identical machinery, identical rows, identical folds -- only the target definition differs.",
         "**Exploratory.** Nothing here is adopted; the three predictions exist so the run can be wrong.", "",
         "## The two targets", "",
         "| target | validation base rate | Brier | skill | ECE | rho |", "|---|---|---|---|---|---|"]
    for name, d in (("fixed 0.25%", f), ("volatility-scaled", v)):
        s = d["validation"]
        L.append("| %s | %.3f | %.5f | %+.4f | %.3f | %+.3f |" % (
            name, s["base_rate"], s["brier"], s["skill"], s["ece"], s["rho_p_vs_abs_return"]))
    t = r["tripwire"]
    L += ["", "Tripwire (this run must reproduce E021's scaled-target skill of %+.5f): difference %.5f, %s."
          % (t["e021_validation_skill"], t["difference"], "FIRED" if t["fired"] else "not fired"), "",
          "## The order features get picked, and how much each target needs them", "",
          "| feature | picked at k (fixed) | picked at k (scaled) | moved |", "|---|---|---|---|"]
    for c in FULL:
        kf, kv = f["selection_k"][c], v["selection_k"][c]
        arrow = "earlier" if kv < kf else ("later" if kv > kf else "same")
        kind = "level" if c in r["level_features"] else "relative"
        L.append("| `%s` (%s) | %d | %d | **%s**%s |" % (c, kind, kf, kv, arrow,
                                                          "" if arrow == "same" else " (%+d)" % (kv - kf)))
    L += ["", "## What each group is worth to each target", "",
          "| group removed | skill lost against fixed | skill lost against scaled |", "|---|---|---|"]
    for g in GROUPS_UNDER_TEST:
        L.append("| %s | %.0f%% | %.0f%% |" % (g, f["group_ablation_skill_cost"][g] * 100,
                                               v["group_ablation_skill_cost"][g] * 100))
    p = r["predictions"]
    L += ["", "## The three pre-registered predictions", "",
          "| # | prediction | outcome |", "|---|---|---|",
          "| P1 | a level feature is picked later AND a relative one earlier | **%s** — later: %s; earlier: %s |" % (
              "HOLDS" if p["P1_level_later_and_relative_earlier"]["holds"] else "fails",
              p["P1_level_later_and_relative_earlier"]["level_features_selected_later"] or "none",
              p["P1_level_later_and_relative_earlier"]["relative_features_selected_earlier"] or "none"),
          "| P2 | the volatility group costs under 40%% of skill | **%s** — %.0f%% against fixed, %.0f%% against scaled |" % (
              "HOLDS" if p["P2_volatility_group_costs_less_than_40pct"]["holds"] else "fails",
              p["P2_volatility_group_costs_less_than_40pct"]["cost_against_fixed"] * 100,
              p["P2_volatility_group_costs_less_than_40pct"]["cost_against_scaled"] * 100),
          "| P3 | the first pick is not `tr_mean_14_rel` | **%s** — first pick is `%s` |" % (
              "HOLDS" if p["P3_first_pick_is_not_tr_mean_14_rel"]["holds"] else "fails",
              p["P3_first_pick_is_not_tr_mean_14_rel"]["first_against_scaled"]),
          "", "**%d of 3 held: %s.**" % (r["summary"]["n_held"], r["summary"]["statement"]), "",
          "## Coefficient signs (all nine, against each target)", "",
          "| feature | median coef (fixed) | sign agreement | median coef (scaled) | sign agreement |",
          "|---|---|---|---|---|"]
    for c in FULL:
        L.append("| `%s` | %+.3f | %.2f | %+.3f | %.2f |" % (
            c, f["coefficients_median"][c], f["coefficient_sign_agreement"][c],
            v["coefficients_median"][c], v["coefficient_sign_agreement"][c]))
    L += ["", "## Skill by feature count (validation)", "",
          "| k | fixed | scaled |", "|---|---|---|"]
    def at(d, k):  # a JSON round-trip turns the integer keys into strings; accept either
        return d[k] if k in d else d[str(k)]

    for k in sorted(int(x) for x in f["skill_by_k"]):
        L.append("| %d | %+.4f | %+.4f |" % (k, at(f["skill_by_k"], k), at(v["skill_by_k"], k)))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E022")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
