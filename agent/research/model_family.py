"""
E020 -- is the logistic the right KIND of model, or just the first one tried?

    python -m agent.research.model_family --experiment E020

E012 chose L2 logistic regression because it is the simplest thing that could work, not
because anything was compared against it. Three candidates, declared in the pre-registration
and run once each, with no hyperparameter search:

    L  the incumbent logistic (nine inputs, C = 0.1)
    I  the same logistic plus every square and pairwise product of the six continuous inputs
    T  gradient-boosted trees with settings fixed in advance

Everything except the model is held at E013's settings, and every candidate is scored on
identical rows. A complex family replaces the incumbent only if it clears the pre-registered
practical bar (10% more skill), the statistical bar (a paired interval excluding zero) AND
stays calibrated -- the deliverable is a calibrated probability, not a ranking.

Pre-registration: research/experiments/E020_model_family_move_size.json.
"""

import argparse
import itertools
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.feature_count import BLOCK, C, FULL, LOG_FEATURES, N_BOOT, SEED, THRESHOLD, prepare
from agent.research.history import load_bars
from agent.research.metrics import brier_score
from agent.research.model_test import LogisticModel, PlattCalibrator
from agent.research.periods import HOLDOUT
from agent.research.simple_baselines import paired_difference, score, simple_rules
from agent.research.walkforward import run_walk_forward
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

# Fixed in the pre-registration. Never tuned, never searched.
TREE_PARAMS = {"max_iter": 200, "learning_rate": 0.05, "max_leaf_nodes": 15,
               "min_samples_leaf": 200, "l2_regularization": 1.0,
               "early_stopping": False, "random_state": 0}
CONTINUOUS = LOG_FEATURES  # the six inputs that get squares and products in candidate I


class TreeModel:
    """Gradient-boosted trees with pre-declared settings; no standardisation needed."""

    def __init__(self):
        from sklearn.ensemble import HistGradientBoostingClassifier
        self.clf = HistGradientBoostingClassifier(**TREE_PARAMS)

    def fit(self, X, y):
        self.clf.fit(X.to_numpy(dtype=float), y)

    def predict_proba(self, X):
        return self.clf.predict_proba(X.to_numpy(dtype=float))[:, 1]


def interaction_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Add every square and pairwise product of the six continuous inputs. Deterministic
    functions of columns that already exist, so no row gains or loses availability: a product
    is missing exactly when one of its parents is, and the parents were already required.
    """
    df = df.copy()
    added = []
    for a in CONTINUOUS:
        name = "sq_%s" % a
        df[name] = df[a] * df[a]
        added.append(name)
    for a, b in itertools.combinations(CONTINUOUS, 2):
        name = "x_%s__%s" % (a, b)
        df[name] = df[a] * df[b]
        added.append(name)
    return df, added


def evaluate_family(df, spec, folds, cols, make_model) -> pd.DataFrame:
    preds, _ = run_walk_forward(df, list(cols), "y", make_model, spec, folds=folds,
                                make_calibrator=PlattCalibrator)
    return preds.join(df[["period", "fwd_1h"]], how="left")


def run(experiment: str) -> Path:
    base_df, spec, folds = prepare()
    df, extra = interaction_columns(base_df)
    logger.info("rows %d, folds %d, interaction columns %d", len(df), len(folds), len(extra))

    families = {
        "L_logistic_incumbent": (FULL, lambda: LogisticModel(C=C)),
        "I_logistic_interactions": (FULL + extra, lambda: LogisticModel(C=C)),
        "T_gradient_boosted_trees": (FULL, TreeModel),
    }
    preds = {}
    for name, (cols, make) in families.items():
        logger.info("running %s (%d inputs)", name, len(cols))
        preds[name] = evaluate_family(df, spec, folds, cols, make)

    ref_index = preds["L_logistic_incumbent"].index
    for name, p in preds.items():
        if not p.index.equals(ref_index):
            raise ValueError("%s was scored on different rows -- the comparison would be invalid" % name)

    # the E019 standing reference, on the same rows
    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(ref_index)

    results: dict = {"by_family": {}, "n_inputs": {n: len(c) for n, (c, _) in families.items()}}
    for period in ("exploration", "validation"):
        mask = (preds["L_logistic_incumbent"]["period"] == period).to_numpy()
        y = preds["L_logistic_incumbent"]["y"].to_numpy(float)[mask]
        size = np.abs(preds["L_logistic_incumbent"]["fwd_1h"].to_numpy(float))[mask]
        for name, p in preds.items():
            results["by_family"].setdefault(name, {})[period] = score(
                p["p"].to_numpy(float)[mask], y, size)
        e = ewma.to_numpy(float)[mask]
        ok = ~np.isnan(e)
        results.setdefault("ewma_reference", {})[period] = score(e[ok], y[ok], size[ok])

    # --- the criterion, on validation
    mask = (preds["L_logistic_incumbent"]["period"] == "validation").to_numpy()
    y = preds["L_logistic_incumbent"]["y"].to_numpy(float)[mask]
    p_inc = preds["L_logistic_incumbent"]["p"].to_numpy(float)[mask]
    inc = results["by_family"]["L_logistic_incumbent"]["validation"]
    verdicts = {}
    for name in families:
        if name == "L_logistic_incumbent":
            continue
        s = results["by_family"][name]["validation"]
        p = preds[name]["p"].to_numpy(float)[mask]
        d = paired_difference(p_inc, p, y)  # positive = the incumbent is worse, i.e. candidate better
        calibrated = s["ece"] <= 0.03 and (np.isnan(s["max_bucket_gap_100"]) or s["max_bucket_gap_100"] <= 0.05)
        practical = s["skill"] >= 1.10 * inc["skill"]
        statistical = d["ci_low"] > 0
        verdicts[name] = {
            "skill": s["skill"], "skill_ratio_vs_incumbent": s["skill"] / inc["skill"] if inc["skill"] else float("inf"),
            "incumbent_brier_minus_candidate": d, "stays_calibrated": bool(calibrated),
            "practical_bar_10pct_more_skill": bool(practical),
            "statistical_bar_interval_excludes_zero": bool(statistical),
            "replaces_the_incumbent": bool(practical and statistical and calibrated),
            "tripwire_skill_ratio_over_1_5": bool(s["skill"] > 1.5 * inc["skill"]),
            "statement": ("clears every bar" if practical and statistical and calibrated else
                          "not calibrated enough to be the deliverable, whatever its Brier" if not calibrated else
                          "statistically better, practically equivalent -- the complexity is not earned"
                          if statistical and not practical else
                          "no better than the incumbent"),
        }
    winner = [n for n, v in verdicts.items() if v["replaces_the_incumbent"]]
    results["verdict"] = {
        "incumbent_validation_skill": inc["skill"], "by_candidate": verdicts,
        "replacement": winner[0] if winner else None,
        "statement": ("%s clears every bar and would replace the incumbent" % winner[0]) if winner else
                     "no candidate clears the pre-registered bars -- the logistic stands",
    }
    results.update({
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION, "snapshot": snapshot.name, "threshold": THRESHOLD,
        "folds": len(folds), "oos_rows": int(len(ref_index)), "tree_params": TREE_PARAMS,
        "n_boot": N_BOOT, "block_hours": BLOCK, "seed": SEED, "C": C,
    })
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model_family.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "model_family.md").write_text(render(results), encoding="utf-8")
    return out_dir / "model_family.md"


def render(r: dict) -> str:
    L = ["# E020 -- is the logistic the right kind of model?", "",
         "Generated %s  |  pipeline %s  |  snapshot %s" % (r["generated_at"], r["pipeline_version"], r["snapshot"]),
         "%d folds, %d out-of-sample rows, every candidate on identical rows. Settings fixed in advance; no search."
         % (r["folds"], r["oos_rows"]), "",
         "## Validation", "",
         "| model | inputs | Brier | skill | ECE | worst bucket | rho |", "|---|---|---|---|---|---|---|"]
    for name in sorted(r["by_family"]):
        s = r["by_family"][name]["validation"]
        L.append("| %s | %d | %.5f | %+.4f | %.3f | %.3f | %+.3f |" % (
            name, r["n_inputs"][name], s["brier"], s["skill"], s["ece"], s["max_bucket_gap_100"],
            s["rho_p_vs_abs_return"]))
    e = r["ewma_reference"]["validation"]
    L.append("| *(E019 reference: 24h EWMA, no fitting)* | 0 | %.5f | %+.4f | %.3f | %.3f | %+.3f |" % (
        e["brier"], e["skill"], e["ece"], e["max_bucket_gap_100"], e["rho_p_vs_abs_return"]))

    v = r["verdict"]
    L += ["", "## Verdict (pre-registered: 10% more skill AND a paired interval excluding zero AND still calibrated)", "",
          "| candidate | skill ratio | practical | statistical | calibrated | replaces incumbent? | reading |",
          "|---|---|---|---|---|---|---|"]
    for name in sorted(v["by_candidate"]):
        c = v["by_candidate"][name]
        L.append("| %s | %.2fx | %s | %s | %s | **%s** | %s |" % (
            name, c["skill_ratio_vs_incumbent"],
            "PASS" if c["practical_bar_10pct_more_skill"] else "fail",
            "PASS" if c["statistical_bar_interval_excludes_zero"] else "fail",
            "yes" if c["stays_calibrated"] else "NO",
            "YES" if c["replaces_the_incumbent"] else "no", c["statement"]))
    L += ["", "Paired Brier differences (positive = the candidate is better than the incumbent):", ""]
    for name in sorted(v["by_candidate"]):
        d = v["by_candidate"][name]["incumbent_brier_minus_candidate"]
        L.append("- %s: %+.5f [%+.5f, %+.5f]" % (name, d["diff"], d["ci_low"], d["ci_high"]))
    L += ["", "**%s.**" % v["statement"], "",
          "## Exploration (reported, not used for the verdict)", "",
          "| model | Brier | skill | ECE | rho |", "|---|---|---|---|---|"]
    for name in sorted(r["by_family"]):
        s = r["by_family"][name]["exploration"]
        L.append("| %s | %.5f | %+.4f | %.3f | %+.3f |" % (name, s["brier"], s["skill"], s["ece"], s["rho_p_vs_abs_return"]))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E020")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
