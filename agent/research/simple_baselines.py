"""
E019 -- does the fitted move-size model beat "how often has a large move happened lately?"

    python -m agent.research.simple_baselines --experiment E019

E012 compared the 1h move-size model against the base rate and against chance. It has never
been compared against a rule that ADAPTS. The share of recent hours that exceeded the
threshold is a direct empirical estimate of exactly the quantity the model predicts, and it
needs no fitting, no calibration, no walk-forward and no stored artefact. If it matches the
model, then nine inputs, quarterly refits and Platt calibration are buying nothing.

Point-in-time argument (the whole experiment depends on it). The label for reference hour s
is the size of the candle that OPENS at s + 1h. At decision hour t the reference candle
(opening at t) has closed, so every close up to close(t) is known, and therefore the size of
every candle opening at or before t. Writing ind(t) = 1{|close(t)/close(t-1) - 1| > threshold},
the label at t is ind(t + 1h) and every rule here is a function of ind(s) for s <= t only.
Windows are measured in TIME, not rows, so a data gap shortens a window rather than silently
reaching further back.

Pre-registration: research/experiments/E019_simple_baselines_move_size.json.
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
from agent.research.feature_count import BLOCK, FULL, N_BOOT, SEED, THRESHOLD, evaluate, prepare
from agent.research.history import load_bars
from agent.research.model_test import PlattCalibrator
from agent.research.metrics import block_bootstrap_estimates, brier_score, log_loss, reliability_table
from agent.research.periods import HOLDOUT
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

# Half the window must actually be present; a gap shortens the window instead of reaching back.
MIN_FRACTION = 0.5
EXPANDING_MIN = 720  # a month of completed hours before the expanding prior means anything


def indicator_series(bars) -> pd.Series:
    """ind(t) = 1 if the candle OPENING at t moved more than the threshold, known at t + 1h."""
    closes = pd.Series({b.as_of: b.close for b in bars}).sort_index()
    ret = closes / closes.shift(1) - 1.0
    # shift(1) is by row; across a data gap the "previous close" is hours older than one hour,
    # so that one return is not a one-hour return and must not count.
    real_hour = closes.index.to_series().diff() == pd.Timedelta(hours=1)
    ind = (ret.abs() > THRESHOLD).astype(float)
    ind[~real_hour.to_numpy()] = np.nan
    return ind


def simple_rules(bars) -> dict[str, pd.Series]:
    """Every rule is a causal function of ind(s) for s <= t. Nothing here is fitted."""
    ind = indicator_series(bars)
    known = ind.dropna()
    rules = {"A_expanding_base_rate": known.expanding(min_periods=EXPANDING_MIN).mean()}
    for hours in (24, 168, 720):
        rules["%s_trailing_%dh" % ("BCD"[(24, 168, 720).index(hours)], hours)] = known.rolling(
            "%dh" % hours, min_periods=int(hours * MIN_FRACTION)).mean()
    rules["E_ewma_halflife_24h"] = known.ewm(halflife=pd.Timedelta("24h"), times=known.index).mean()
    return {k: v.reindex(ind.index) for k, v in rules.items()}


# ---------------------------------------------------------------- scoring
def score(p: np.ndarray, y: np.ndarray, size: np.ndarray) -> dict:
    base = float(np.mean(y))
    brier = brier_score(p, y)
    brier_base = brier_score(np.full(len(y), base), y)
    buckets, ece, _ = reliability_table(p, y)
    gaps = [abs(b.observed - b.mean_predicted) for b in buckets if b.n >= 100]
    return {"n": int(len(y)), "base_rate": base, "brier": brier, "brier_base_rate": brier_base,
            "skill": 1.0 - brier / brier_base, "log_loss": log_loss(p, y), "ece": ece,
            "mean_p": float(np.mean(p)), "rho_p_vs_abs_return": spearman(p, size),
            "max_bucket_gap_100": max(gaps) if gaps else float("nan")}


def paired_difference(p_other: np.ndarray, p_ref: np.ndarray, y: np.ndarray) -> dict:
    """Brier(other) - Brier(reference) with a paired circular block bootstrap interval."""
    stacked = np.column_stack([p_other, p_ref, y])

    def diff(a):
        return brier_score(a[:, 0], a[:, 2]) - brier_score(a[:, 1], a[:, 2])

    point, est = block_bootstrap_estimates(stacked, diff, block=BLOCK, n_boot=N_BOOT, seed=SEED)
    if len(est) == 0:
        return {"diff": point, "ci_low": float("nan"), "ci_high": float("nan"), "se": float("nan")}
    return {"diff": point, "ci_low": float(np.percentile(est, 2.5)),
            "ci_high": float(np.percentile(est, 97.5)), "se": float(np.std(est, ddof=1))}


def calibrate_like_the_incumbent(rule: pd.Series, df: pd.DataFrame, folds) -> pd.Series:
    """
    Give a simple rule the SAME advantage the incumbent has: a Platt re-map fitted on each
    fold's purged 90-day calibration slice and applied to that fold's test block. Nothing about
    the rule itself is fitted -- only the mapping from its number to a probability. Used for the
    fairness check in the secondary analysis, not for the pre-registered verdict.
    """
    out = pd.Series(np.nan, index=rule.index, dtype=float)
    y_all = df["y"]
    for fold in folds:
        if fold.calib_start is None:
            continue
        cal = rule[(rule.index >= fold.calib_start) & (rule.index < fold.calib_end)].dropna()
        test = rule[(rule.index >= fold.test_start) & (rule.index < fold.test_end)].dropna()
        y_cal = y_all.reindex(cal.index)
        ok = y_cal.notna().to_numpy()
        if ok.sum() < 100 or len(test) == 0:
            continue
        c = PlattCalibrator()
        c.fit(cal.to_numpy(float)[ok], y_cal.to_numpy(float)[ok])
        out.loc[test.index] = np.asarray(c.transform(test.to_numpy(float)), dtype=float)
    return out


# ---------------------------------------------------------------- the experiment
def run(experiment: str) -> Path:
    df, spec, folds = prepare()
    cache: dict = {}
    incumbent = evaluate(df, spec, folds, FULL, cache)
    one_feature = evaluate(df, spec, folds, ["tr_mean_14_rel"], cache)
    oos = incumbent["predictions"]  # the rows every candidate is judged on
    logger.info("out-of-sample rows: %d", len(oos))

    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    rules = simple_rules(bars)

    candidates: dict[str, pd.Series] = {name: s.reindex(oos.index) for name, s in rules.items()}
    candidates["F_one_feature_logistic"] = one_feature["predictions"]["p"].reindex(oos.index)
    candidates["G_incumbent"] = oos["p"]

    results: dict = {"by_candidate": {}, "coverage": {}}
    for period in ("exploration", "validation"):
        mask = (oos["period"] == period).to_numpy()
        y_all = oos["y"].to_numpy(float)[mask]
        size_all = np.abs(oos["fwd_1h"].to_numpy(float))[mask]
        for name, series in candidates.items():
            p_all = series.to_numpy(float)[mask]
            ok = ~np.isnan(p_all)
            entry = results["by_candidate"].setdefault(name, {})
            entry[period] = score(p_all[ok], y_all[ok], size_all[ok])
            entry[period]["rows_scored"] = int(ok.sum())
            entry[period]["rows_unavailable"] = int((~ok).sum())

    # The criterion is judged on validation, on the rows where EVERY candidate has a value.
    mask = (oos["period"] == "validation").to_numpy()
    stack = np.column_stack([candidates[n].to_numpy(float)[mask] for n in candidates])
    common = ~np.isnan(stack).any(axis=1)
    y = oos["y"].to_numpy(float)[mask][common]
    size = np.abs(oos["fwd_1h"].to_numpy(float))[mask][common]
    p_ref = candidates["G_incumbent"].to_numpy(float)[mask][common]
    results["common_validation_rows"] = int(common.sum())
    results["common_validation_dropped"] = int((~common).sum())

    head_to_head = {}
    for name in candidates:
        if name == "G_incumbent":
            continue
        p = candidates[name].to_numpy(float)[mask][common]
        head_to_head[name] = {"on_common_rows": score(p, y, size),
                              "brier_minus_incumbent": paired_difference(p, p_ref, y)}
    results["incumbent_on_common_rows"] = score(p_ref, y, size)
    results["head_to_head_validation"] = head_to_head

    # --- the pre-registered two-part criterion, applied to the best SIMPLE (non-fitted) rule
    simple_names = [n for n in candidates if n.startswith(("A_", "B_", "C_", "D_", "E_"))]
    best_simple = max(simple_names, key=lambda n: head_to_head[n]["on_common_rows"]["skill"])
    inc_skill = results["incumbent_on_common_rows"]["skill"]
    best_skill = head_to_head[best_simple]["on_common_rows"]["skill"]
    d = head_to_head[best_simple]["brier_minus_incumbent"]
    practical = inc_skill >= 1.10 * best_skill
    statistical = d["ci_low"] > 0
    results["verdict"] = {
        "best_simple_rule": best_simple, "best_simple_skill": best_skill, "incumbent_skill": inc_skill,
        "skill_ratio": inc_skill / best_skill if best_skill else float("inf"),
        "practical_bar_10pct_more_skill": bool(practical),
        "statistical_bar_interval_excludes_zero": bool(statistical),
        "paired_brier_difference": d,
        "earns_its_complexity": bool(practical and statistical),
        "statement": ("the fitted model earns its complexity" if practical and statistical else
                      "statistically better, practically equivalent -- the complexity is not earned"
                      if statistical and not practical else
                      "the fitted model does NOT clear the pre-registered bars"),
        "tripwire_a_simple_rule_beats_the_incumbent": bool(
            any(head_to_head[n]["brier_minus_incumbent"]["diff"] < 0 for n in simple_names)),
    }
    # --- secondary, NOT pre-registered: give the simple rules the incumbent's calibration too.
    # The pre-registration scored them uncalibrated on the stated ground that a rule needing a
    # fitted calibrator is no longer simple. That is a fair rule, but it invites the obvious
    # objection that the comparison was rigged, so the objection is answered with numbers.
    fair = {}
    for name in simple_names:
        cal = calibrate_like_the_incumbent(rules[name].reindex(oos.index), df, folds)
        p = cal.to_numpy(float)[mask][common]
        ok = ~np.isnan(p)
        if ok.sum() < 100:
            continue
        fair[name] = {"rows_scored": int(ok.sum()), "on_common_rows": score(p[ok], y[ok], size[ok]),
                      "brier_minus_incumbent": paired_difference(p[ok], p_ref[ok], y[ok])}
    if fair:
        best_fair = max(fair, key=lambda n: fair[n]["on_common_rows"]["skill"])
        results["secondary_fair_calibration"] = {
            "why": "answers the objection that the simple rules were scored uncalibrated",
            "by_candidate": fair, "best": best_fair,
            "best_skill": fair[best_fair]["on_common_rows"]["skill"],
            "skill_ratio_incumbent_over_best": inc_skill / fair[best_fair]["on_common_rows"]["skill"]
            if fair[best_fair]["on_common_rows"]["skill"] else float("inf"),
            "verdict_unchanged": bool(inc_skill >= 1.10 * fair[best_fair]["on_common_rows"]["skill"]
                                      and fair[best_fair]["brier_minus_incumbent"]["ci_low"] > 0),
        }

    results.update({
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION, "snapshot": snapshot.name, "threshold": THRESHOLD,
        "oos_rows": int(len(oos)), "folds": len(folds), "n_boot": N_BOOT, "block_hours": BLOCK, "seed": SEED,
        "min_window_fraction": MIN_FRACTION, "expanding_min_periods": EXPANDING_MIN,
    })

    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "simple_baselines.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "simple_baselines.md").write_text(render(results), encoding="utf-8")
    return out_dir / "simple_baselines.md"


def render(r: dict) -> str:
    L = ["# E019 -- does the move-size model beat \"how often lately?\"", "",
         "Generated %s  |  pipeline %s  |  snapshot %s" % (r["generated_at"], r["pipeline_version"], r["snapshot"]),
         "Threshold |1h return| > %.2f%%.  All candidates scored on the incumbent's own out-of-sample rows"
         " (%d hours, %d folds); the criterion is judged on the %d validation hours where every candidate"
         " has a value." % (r["threshold"] * 100, r["oos_rows"], r["folds"], r["common_validation_rows"]), "",
         "## Validation, on identical rows", "",
         "| candidate | fitted? | Brier | skill | ECE | rho | mean p | Brier minus incumbent [95%] |",
         "|---|---|---|---|---|---|---|---|"]
    inc = r["incumbent_on_common_rows"]
    order = sorted(r["head_to_head_validation"])
    fitted = {"F_one_feature_logistic": "yes (1 input)", "G_incumbent": "yes (9 inputs)"}
    for name in order:
        h = r["head_to_head_validation"][name]
        s, d = h["on_common_rows"], h["brier_minus_incumbent"]
        L.append("| %s | %s | %.5f | %+.4f | %.3f | %+.3f | %.3f | %+.5f [%+.5f, %+.5f] |" % (
            name, fitted.get(name, "no"), s["brier"], s["skill"], s["ece"], s["rho_p_vs_abs_return"],
            s["mean_p"], d["diff"], d["ci_low"], d["ci_high"]))
    L.append("| **G_incumbent** | yes (9 inputs) | **%.5f** | **%+.4f** | %.3f | %+.3f | %.3f | -- |" % (
        inc["brier"], inc["skill"], inc["ece"], inc["rho_p_vs_abs_return"], inc["mean_p"]))

    v = r["verdict"]
    L += ["", "A positive difference means the candidate is WORSE than the incumbent.", "",
          "## Verdict (pre-registered, two parts)", "",
          "- best simple (non-fitted) rule: **%s**, skill %+.4f" % (v["best_simple_rule"], v["best_simple_skill"]),
          "- incumbent skill %+.4f -> ratio **%.2fx**" % (v["incumbent_skill"], v["skill_ratio"]),
          "- practical bar (at least 1.10x the skill): **%s**" % ("PASS" if v["practical_bar_10pct_more_skill"] else "FAIL"),
          "- statistical bar (paired 95%% interval excludes zero): **%s** (%+.5f [%+.5f, %+.5f])" % (
              "PASS" if v["statistical_bar_interval_excludes_zero"] else "FAIL",
              v["paired_brier_difference"]["diff"], v["paired_brier_difference"]["ci_low"],
              v["paired_brier_difference"]["ci_high"]),
          "- tripwire (a simple rule beats the incumbent): **%s**" % (
              "FIRED -- investigate" if v["tripwire_a_simple_rule_beats_the_incumbent"] else "not fired"),
          "", "**%s.**" % v["statement"], ""]
    if "secondary_fair_calibration" in r:
        s2 = r["secondary_fair_calibration"]
        L += ["## Secondary check -- NOT pre-registered: the same calibration for everyone", "",
              "The pre-registration scored the simple rules uncalibrated, on the stated ground that a rule",
              "needing a fitted calibrator is no longer simple. That invites the objection that the",
              "comparison was rigged, so here every simple rule gets the incumbent's exact advantage: a",
              "Platt re-map fitted on the same purged 90-day slice of each fold and applied to the same",
              "test block. Only the mapping is fitted; the rules themselves are untouched.", "",
              "| candidate | Brier (calibrated) | skill | ECE | Brier minus incumbent [95%] |",
              "|---|---|---|---|---|"]
        for name in sorted(s2["by_candidate"]):
            h = s2["by_candidate"][name]
            sc, d = h["on_common_rows"], h["brier_minus_incumbent"]
            L.append("| %s | %.5f | %+.4f | %.3f | %+.5f [%+.5f, %+.5f] |" % (
                name, sc["brier"], sc["skill"], sc["ece"], d["diff"], d["ci_low"], d["ci_high"]))
        L += ["", "Best simple rule once calibrated: **%s**, skill %+.4f -- the incumbent is still **%.2fx** "
                  "more skilful, and the verdict is **%s**." % (
                      s2["best"], s2["best_skill"], s2["skill_ratio_incumbent_over_best"],
                      "unchanged" if s2["verdict_unchanged"] else "CHANGED -- investigate"), ""]
    L += ["## Exploration period (reported, not used for the verdict)", "",
          "| candidate | Brier | skill | ECE | rho |", "|---|---|---|---|---|"]
    for name in sorted(r["by_candidate"]):
        e = r["by_candidate"][name]["exploration"]
        L.append("| %s | %.5f | %+.4f | %.3f | %+.3f |" % (name, e["brier"], e["skill"], e["ece"], e["rho_p_vs_abs_return"]))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E019")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
