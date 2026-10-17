"""
The safe-signal-research batch: E036 (MS-A, move-size) and E037 (D1, D2, direction), registered in
research/experiments/E036_ms_a_liquidity_pair.json and E037_direction_d1_d2.json before this code existed.

    python -m agent.research.signal_batch reproduce     # Phase 3: the registered references must reproduce first
    python -m agent.research.signal_batch compare       # Phase 4: the three registered comparisons, run once

PHASE 3. Before any candidate is fitted, the references both records name must reproduce their recorded figures to
1e-9 through the corrected, governed data path (agent/research/snapshots.py: registered files only, cut at the
holdout, never downloaded):
  * move-size: E018's full model (= E019's incumbent = E013's Platt variant), through feature_count.prepare/evaluate,
    the functions E018 and E019 used; and E019's free 24 h EWMA rule, scored exactly as E019 scored it;
  * direction: E032, by running agent/research/direction_probability.run itself (its code unchanged) into
    research/results/E037/reproduction_E032/, then comparing every number of its result with E032's.
The expected figures are read from the committed result files, never retyped. PASSED 2026-10-17 (50d246f).

PHASE 4. The three comparisons exactly as registered (E036: MS-A; E037: D1 and D2): the same model code as the
references (feature_count.evaluate for move-size, E032's LogisticModel and scores for direction), rows restricted
ONCE so that every model is scored on identical hours, the paired 48 h block bootstrap (2,000 resamples, seed 31),
Holm within each track, the copied 1.10x practical bar, the copied calibration rules, the 6-of-8 year rule, the
tripwires, and SUPPORTED / NOT_SUPPORTED / INCONCLUSIVE as written in the records. The judging rules are pure
functions (tested); nothing is tuned, searched or re-tried.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TOLERANCE = 1e-9  # both records: same machine, code and bytes, so the figures must agree to the last digits
# ---- Phase 4: every constant below is copied from research/experiments/E036_* and E037_* (registered before this code)
MS_CANDIDATE = ["amihud_rel_168", "trade_size_rel_24"]  # E036: log-transformed like the reference's ratio inputs
UP_STREAK = "up_streak_6"                               # E037 D2: enters raw, standardised by the model's scaler
ALPHA = 0.05                                            # family-wise, Holm within each track
PRACTICAL_RATIO = 1.10                                  # E019 / E020 / E032 H_b
ECE_BAR = 0.03                                          # E013 / E032 H_c
RHO_TOLERANCE = 0.02                                    # E013 C2 (E036 S6)
YEARS = tuple(range(2018, 2026))
MIN_POSITIVE_YEARS = 6                                  # E032 H_d, applied to the difference
MS_TRIPWIRE_RATIO = 1.5                                 # E020's tripwire (E036)
D2_TRIPWIRE_RATIO = 2.0                                 # E037 D2
RESULTS = Path("research") / "results"
E018_RESULT = RESULTS / "E018" / "feature_count.json"
E019_RESULT = RESULTS / "E019" / "simple_baselines.json"
E032_RESULT = RESULTS / "E032" / "direction_probability.json"
NOT_COMPARED = {"experiment", "generated_at"}  # labels of a run, not results


def compare(expected, got, path: str = "") -> list[str]:
    """Every difference between two result trees: floats beyond TOLERANCE, any other value unequal, keys missing on
    either side. Pure, so tests can prove it catches what it must."""
    if isinstance(expected, dict) and isinstance(got, dict):
        out = []
        for k in sorted(set(expected) | set(got)):
            if k in NOT_COMPARED:
                continue
            if k not in got or k not in expected:
                out.append(f"{path}.{k}: present only in the {'expected' if k in expected else 'reproduced'} result")
                continue
            out += compare(expected[k], got[k], f"{path}.{k}")
        return out
    if isinstance(expected, list) and isinstance(got, list):
        if len(expected) != len(got):
            return [f"{path}: {len(expected)} items expected, {len(got)} reproduced"]
        return [d for i, (a, b) in enumerate(zip(expected, got)) for d in compare(a, b, f"{path}[{i}]")]
    if isinstance(expected, bool) or isinstance(got, bool) or not isinstance(expected, (int, float)) or not isinstance(got, (int, float)):
        return [] if expected == got else [f"{path}: expected {expected!r}, reproduced {got!r}"]
    if isinstance(expected, int) and isinstance(got, int):
        return [] if expected == got else [f"{path}: expected {expected}, reproduced {got}"]
    a, b = float(expected), float(got)
    if np.isnan(a) and np.isnan(b):
        return []
    return [] if abs(a - b) <= TOLERANCE else [f"{path}: expected {a!r}, reproduced {b!r} (difference {b - a:+.3e})"]


def _jsonable(o):
    return json.loads(json.dumps(o, default=str))


def reproduce_move_size() -> dict:
    """E018's full model and E019's EWMA rule, with E018/E019's own functions, on E013's rows."""
    from agent.research.feature_count import FULL, evaluate, prepare
    from agent.research.history import load_bars
    from agent.research.periods import HOLDOUT
    from agent.research.simple_baselines import paired_difference, score, simple_rules

    e018 = json.loads(E018_RESULT.read_text(encoding="utf-8"))
    e019 = json.loads(E019_RESULT.read_text(encoding="utf-8"))
    df, spec, folds = prepare()
    full = evaluate(df, spec, folds, FULL, {})
    oos = full["predictions"]
    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(oos.index)

    got_full = {"n_features": full["n_features"], "exploration": full["exploration"], "validation": full["validation"]}
    got_ewma = {}
    for period in ("exploration", "validation"):
        mask = (oos["period"] == period).to_numpy()
        p, y = ewma.to_numpy(float)[mask], oos["y"].to_numpy(float)[mask]
        size = np.abs(oos["fwd_1h"].to_numpy(float))[mask]
        ok = ~np.isnan(p)
        got_ewma[period] = {**score(p[ok], y[ok], size[ok]), "rows_scored": int(ok.sum()), "rows_unavailable": int((~ok).sum())}
    mask = (oos["period"] == "validation").to_numpy()
    p_ewma, p_ref, y = ewma.to_numpy(float)[mask], oos["p"].to_numpy(float)[mask], oos["y"].to_numpy(float)[mask]
    ok = ~np.isnan(p_ewma)
    got = _jsonable({
        "folds": len(folds), "rows_common": int(len(df)), "oos_rows": int(len(oos)), "snapshot": snapshot.name,
        "E018_full": got_full, "E019_ewma": got_ewma,
        "E019_ewma_minus_incumbent_validation": paired_difference(p_ewma[ok], p_ref[ok], y[ok]),
    })
    expected = {"folds": e018["folds"], "rows_common": e018["rows_common"], "oos_rows": e019["oos_rows"], "snapshot": e018["snapshot"],
                "E018_full": e018["ablation"]["full"], "E019_ewma": e019["by_candidate"]["E_ewma_halflife_24h"],
                "E019_ewma_minus_incumbent_validation": e019["verdict"]["paired_brier_difference"]}
    # E019's incumbent IS E018's full model; the copy in E019 must agree as well (one more independent check)
    incumbent = {p: e019["by_candidate"]["G_incumbent"][p] for p in ("exploration", "validation")}
    differences = compare(expected, got) + compare(
        {p: {k: v for k, v in incumbent[p].items() if k in got_full[p]} for p in incumbent},
        {p: _jsonable(got_full[p]) for p in incumbent}, "E019_incumbent")
    return {"track": "move-size (E036's gate)", "reproduces": not differences, "differences": differences,
            "expected": expected, "reproduced": got}


def reproduce_direction() -> dict:
    """E032 by its own unchanged code, written next to E037's results, then compared number by number."""
    from agent.research.direction_probability import run

    md = run("E037/reproduction_E032")
    got = json.loads((md.parent / "direction_probability.json").read_text(encoding="utf-8"))
    expected = json.loads(E032_RESULT.read_text(encoding="utf-8"))
    differences = compare(expected, got)
    return {"track": "direction (E037's gate)", "reproduces": not differences, "differences": differences,
            "reproduction_files": md.parent.as_posix()}


# ================================================================ Phase 4: the registered judging rules (pure)
def bootstrap_p(estimates: np.ndarray) -> float:
    """Two-sided bootstrap p as both records define it: min(1, 2 * min(1 + #{d* <= 0}, 1 + #{d* >= 0}) / (1 + B))."""
    est = np.asarray(estimates, float)
    return float(min(1.0, 2 * min(1 + int(np.sum(est <= 0)), 1 + int(np.sum(est >= 0))) / (1 + len(est))))


def holm(pvalues: dict[str, float], alpha: float = ALPHA) -> dict[str, dict]:
    """Holm step-down within one family: adjusted p_(i) = max_{j<=i} min(1, (m - j + 1) p_(j)); reject when < alpha."""
    order = sorted(pvalues, key=lambda k: pvalues[k])
    m, running, out = len(order), 0.0, {}
    for j, name in enumerate(order):
        running = max(running, min(1.0, (m - j) * pvalues[name]))
        out[name] = {"p": pvalues[name], "p_holm": running, "rejected": running < alpha}
    return out


def practical_threshold(skill_smaller: float, brier_denominator: float) -> float:
    """The Brier gain equivalent to the larger model reaching 1.10x the smaller one's skill (never below zero)."""
    return max(0.0, (PRACTICAL_RATIO - 1.0) * skill_smaller * brier_denominator)


def year_differences(index: pd.DatetimeIndex, p_without: np.ndarray, p_with: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Brier(without) - Brier(with) per calendar year (positive = the extra information helps)."""
    from agent.research.metrics import brier_score

    out = {}
    for yr in YEARS:
        m = index.year == yr
        if m.any():
            out[str(yr)] = brier_score(p_without[m], y[m]) - brier_score(p_with[m], y[m])
    return out


def judge(validation: dict, exploration: dict, years: dict[str, float], p_used: float, threshold: float, ci_key: str,
          calibration_ok: bool, rho_ok: bool | None = None, small_skill_not_positive: bool = False,
          large_skill_positive: bool = True) -> dict:
    """
    The verdict, exactly as both records wrote it. `validation` / `exploration`: {"diff", ci_key: [lo, hi]} with diff =
    Brier(without) - Brier(with). S6 (rho) applies to E036 only (rho_ok None for E037).
    """
    s = {
        "S1_difference_positive_and_significant": bool(validation["diff"] > 0 and p_used < ALPHA),
        "S2_practical": bool(large_skill_positive if small_skill_not_positive else validation["diff"] >= threshold),
        "S3_exploration_point_estimate_positive": bool(exploration["diff"] > 0),
        "S4_calibration": bool(calibration_ok),
        "S5_years_positive": int(sum(1 for yr in YEARS if years.get(str(yr), float("nan")) > 0)),
    }
    s["S5_at_least_6_of_8_years"] = s["S5_years_positive"] >= MIN_POSITIVE_YEARS
    if rho_ok is not None:
        s["S6_ranking_not_worse"] = bool(rho_ok)
    supported = all(v for k, v in s.items() if k != "S5_years_positive")
    not_supported = validation[ci_key][1] < threshold or not calibration_ok
    verdict = "SUPPORTED" if supported else "NOT_SUPPORTED" if not_supported else "INCONCLUSIVE"
    return {"criteria": s, "threshold": threshold, "interval_used_for_failure": ci_key,
            "upper_bound_below_threshold": bool(validation[ci_key][1] < threshold), "verdict": verdict}


def paired(p_without: np.ndarray, p_with: np.ndarray, y: np.ndarray) -> dict:
    """d = Brier(without) - Brier(with), the registered paired bootstrap (simple_baselines.paired_difference's own
    resampling: 48 h blocks, 2,000 resamples, seed 31), with the 95% and 97.5% intervals and the bootstrap p."""
    from agent.research.metrics import block_bootstrap_estimates, brier_score
    from agent.research.simple_baselines import BLOCK, N_BOOT, SEED, paired_difference

    stacked = np.column_stack([p_without, p_with, y])
    point, est = block_bootstrap_estimates(stacked, lambda a: brier_score(a[:, 0], a[:, 2]) - brier_score(a[:, 1], a[:, 2]),
                                           block=BLOCK, n_boot=N_BOOT, seed=SEED)
    check = paired_difference(p_without, p_with, y)  # the very function E019/E032 used: identical resamples, same interval
    lo, hi = float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))
    assert abs(check["diff"] - point) <= TOLERANCE and abs(check["ci_low"] - lo) <= TOLERANCE and abs(check["ci_high"] - hi) <= TOLERANCE
    return {"diff": float(point), "ci95": [lo, hi], "ci975": [float(np.percentile(est, 1.25)), float(np.percentile(est, 98.75))],
            "se": float(np.std(est, ddof=1)), "p_two_sided": bootstrap_p(est), "resamples": int(len(est))}


def _calibration(p: np.ndarray, y: np.ndarray) -> dict:
    from agent.research.block_calibration import calibration_line
    from agent.research.checkpoint_power import e013_passes

    ece_ok, buckets_ok, ece = e013_passes(p, y)
    return {"ece": float(ece), "ece_ok": bool(ece_ok), "e013_buckets_ok": bool(buckets_ok), "calibration_line": calibration_line(p, y),
            "mean_stated": float(np.mean(p)), "observed": float(np.mean(y))}


# ================================================================ Phase 4: E036, MS-A
def run_ms_a() -> dict:
    from agent.research.feature_count import FULL, HORIZON, LOG_FEATURES, THRESHOLD, evaluate
    from agent.research.history import load_bars
    from agent.research.model_test import BaseRateModel, build_frame
    from agent.research.periods import HOLDOUT
    from agent.research.simple_baselines import score, simple_rules
    from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward

    cols_ref, cols_cand = list(FULL), list(FULL) + MS_CANDIDATE
    df, _ = build_frame(HORIZON, [], cols_cand, "large_move", THRESHOLD)
    attrs = dict(df.attrs)
    for c in LOG_FEATURES + MS_CANDIDATE:  # the reference's rule, extended to the two new ratio inputs (registered)
        df[c] = np.log(df[c].where(df[c] > 0))
    frame_rows = int(len(df))
    common = df[cols_cand + ["y"]].dropna().index  # restricted ONCE: every model is scored on the same hours
    lost_ref_only = int(df[cols_ref + ["y"]].dropna().index.difference(common).size)
    df = df.loc[common]
    df.attrs.update(attrs)
    spec = WalkForwardSpec(horizon_hours=HORIZON, scheme="expanding", min_train_days=365, test_block_days=90, embargo_hours=24, calib_days=90)
    folds = make_folds(common, spec)
    cache: dict = {}
    ref = evaluate(df, spec, folds, cols_ref, cache)
    cand = evaluate(df, spec, folds, cols_cand, cache)
    _, per_fold = run_walk_forward(df, cols_ref, "y", BaseRateModel, spec, folds=folds)  # row counts per fold (identical for all models)
    pr, pc = ref["predictions"], cand["predictions"]
    assert pr.index.equals(pc.index), "reference and candidate must be scored on identical hours"
    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(pr.index)

    e018 = json.loads(E018_RESULT.read_text(encoding="utf-8"))
    res: dict = {"experiment": "E036", "rows": {
        "frame_rows_with_label_or_not": frame_rows, "common_rows": int(len(common)), "E013_common_rows": e018["rows_common"],
        "rows_the_reference_alone_would_have_had_but_the_candidate_lacks": lost_ref_only,
        "out_of_sample_rows": int(len(pr)), "folds": len(folds), "per_fold": per_fold,
        "ewma_rows_unavailable": int(ewma.isna().sum())},
        "snapshot": snapshot.name, "by_period": {}}
    for period in ("exploration", "validation"):
        m = (pr["period"] == period).to_numpy()
        y = pr["y"].to_numpy(float)[m]
        size = np.abs(pr["fwd_1h"].to_numpy(float))[m]
        p_ref, p_cand, p_ewma = pr["p"].to_numpy(float)[m], pc["p"].to_numpy(float)[m], ewma.to_numpy(float)[m]
        ok = ~np.isnan(p_ewma)
        res["by_period"][period] = {
            "reference": {**ref[period], **_calibration(p_ref, y)}, "candidate": {**cand[period], **_calibration(p_cand, y)},
            "ewma_rule": score(p_ewma[ok], y[ok], size[ok]),
            "d_reference_minus_candidate": paired(p_ref, p_cand, y),
            "ewma_minus_candidate": paired(p_ewma[ok], p_cand[ok], y[ok]),
            "ewma_minus_reference": paired(p_ewma[ok], p_ref[ok], y[ok]),
        }
    res["years_d"] = year_differences(pr.index, pr["p"].to_numpy(float), pc["p"].to_numpy(float), pr["y"].to_numpy(float))
    res["coefficients"] = {"reference": {"median": ref["coefficients_median"], "sign_agreement": ref["coefficient_sign_agreement"]},
                           "candidate": {"median": cand["coefficients_median"], "sign_agreement": cand["coefficient_sign_agreement"]}}
    v, e = res["by_period"]["validation"], res["by_period"]["exploration"]
    skill_ref, skill_cand = v["reference"]["skill"], v["candidate"]["skill"]
    threshold = practical_threshold(skill_ref, v["reference"]["brier_base_rate"])
    d = v["d_reference_minus_candidate"]
    res["multiple_testing"] = holm({"MS-A": d["p_two_sided"]})
    res["tripwire"] = {"candidate_skill_over_reference": skill_cand / skill_ref if skill_ref else float("inf"),
                       "fired": bool(skill_cand >= MS_TRIPWIRE_RATIO * skill_ref)}
    if res["tripwire"]["fired"]:
        res["judgement"] = {"verdict": "STOPPED_TRIPWIRE", "threshold": threshold}
        return res
    calibration_ok = v["candidate"]["ece_ok"] and v["candidate"]["e013_buckets_ok"] and e["candidate"]["ece"] <= ECE_BAR
    rho_ok = v["candidate"]["rho_p_vs_abs_return"] >= v["reference"]["rho_p_vs_abs_return"] - RHO_TOLERANCE
    res["judgement"] = judge(d, e["d_reference_minus_candidate"], res["years_d"], res["multiple_testing"]["MS-A"]["p_holm"],
                             threshold, "ci95", calibration_ok, rho_ok)
    res["judgement"]["skill_ratio_candidate_over_reference"] = skill_cand / skill_ref
    return res


# ================================================================ Phase 4: E037, D1 and D2
def run_d1_d2() -> dict:
    from agent.research.direction_probability import C, HORIZON, INPUTS, ONE_FEATURE, scores
    from agent.research.metrics import brier_score
    from agent.research.model_test import BaseRateModel, LogisticModel, build_frame
    from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward

    inputs_m = list(INPUTS)
    inputs_r = [c for c in INPUTS if not c.endswith("_score")]  # D1: the four category scores removed
    inputs_c = inputs_m + [UP_STREAK]                            # D2: up_streak_6 added
    assert len(inputs_r) == 4 and len(inputs_m) == 8
    df, _ = build_frame(HORIZON, [], inputs_c, "direction")
    common = df[inputs_c + ["y"]].dropna().index  # restricted ONCE: M, R, C, F and B on the same hours
    lost_e032_only = int(df[inputs_m + ["y"]].dropna().index.difference(common).size)
    df = df.loc[common]
    spec = WalkForwardSpec(horizon_hours=HORIZON, scheme="expanding", min_train_days=365, test_block_days=90, embargo_hours=24, calib_days=0)
    folds = make_folds(common, spec)

    coefficients: dict[str, list] = {}

    def logistic(name, cols):
        def make():
            mdl = LogisticModel(C=C)
            coefficients.setdefault(name, []).append((mdl, cols))
            return mdl
        return make

    preds = {}
    for name, cols in (("M", inputs_m), ("R", inputs_r), ("C", inputs_c), ("F", list(ONE_FEATURE))):
        preds[name], diag = run_walk_forward(df, cols, "y", logistic(name, cols), spec, folds=folds)
    preds["B"], _ = run_walk_forward(df, inputs_m, "y", BaseRateModel, spec, folds=folds)
    index = preds["M"].index
    assert all(p.index.equals(index) for p in preds.values()), "every model must be scored on identical hours"
    joined = preds["M"].join(df[["period", "fwd_%dh" % HORIZON]], how="left")
    p = {k: v["p"].reindex(index).to_numpy(float) for k, v in preds.items()}
    y_all, ret_all = joined["y"].to_numpy(float), joined["fwd_%dh" % HORIZON].to_numpy(float)

    e032 = json.loads(E032_RESULT.read_text(encoding="utf-8"))
    res: dict = {"experiment": "E037", "rows": {
        "common_rows": int(len(common)), "out_of_sample_rows": int(len(index)), "E032_out_of_sample_rows": e032["rows"],
        "rows_E032_had_but_up_streak_6_lacks": lost_e032_only, "folds": len(folds), "per_fold": diag}, "by_period": {}}
    for period in ("exploration", "validation"):
        m = (joined["period"] == period).to_numpy()
        idx, y, ret = index[m], y_all[m], ret_all[m]
        res["by_period"][period] = {
            "models": {k: scores(p[k][m], y, ret, p["B"][m], idx) for k in ("M", "R", "C", "F")},
            "base_rate": {"brier": brier_score(p["B"][m], y), "mean_stated": float(p["B"][m].mean())},
            "D1_d_R_minus_M": paired(p["R"][m], p["M"][m], y),
            "D2_d_M_minus_C": paired(p["M"][m], p["C"][m], y),
            "R_minus_F": paired(p["F"][m], p["R"][m], y), "B_minus_R": paired(p["B"][m], p["R"][m], y),
            "C_minus_F": paired(p["F"][m], p["C"][m], y), "B_minus_C": paired(p["B"][m], p["C"][m], y),
        }
    res["years"] = {"D1": year_differences(index, p["R"], p["M"], y_all), "D2": year_differences(index, p["M"], p["C"], y_all)}
    res["coefficients"] = {}
    for name, fitted in coefficients.items():
        per_fold_coef = [mdl.coefficients(cols) for mdl, cols in fitted]
        cols = fitted[0][1]
        res["coefficients"][name] = {c: {"median": float(np.median([f[c] for f in per_fold_coef])),
                                         "sign_agreement": float(np.mean([np.sign(f[c]) == np.sign(np.median([g[c] for g in per_fold_coef]))
                                                                          for f in per_fold_coef]))} for c in cols}
    v, e = res["by_period"]["validation"], res["by_period"]["exploration"]
    brier_b = v["base_rate"]["brier"]
    skill = {k: v["models"][k]["skill_vs_base_rate"] for k in ("M", "R", "C", "F")}
    e032_m = e032["by_period"]["validation"]["model"]["brier"]
    res["E032_cross_check"] = {"validation_brier_M": v["models"]["M"]["brier"], "E032_validation_brier_M": e032_m,
                               "identical_to_E032": abs(v["models"]["M"]["brier"] - e032_m) <= TOLERANCE}
    res["multiple_testing"] = holm({"D1": v["D1_d_R_minus_M"]["p_two_sided"], "D2": v["D2_d_M_minus_C"]["p_two_sided"]})
    res["tripwires"] = {"D1_R_better_than_M_by_more_than_M_skill": bool(skill["R"] - skill["M"] > skill["M"]),
                        "D2_C_skill_over_twice_M": bool(skill["C"] > D2_TRIPWIRE_RATIO * skill["M"])}

    def calibrated(k):
        return bool(v["models"][k]["ece"] <= ECE_BAR and e["models"][k]["ece"] <= ECE_BAR and v["models"][k]["e013_buckets_ok"])

    res["judgement"] = {}
    for comp, (small, large, key) in {"D1": ("R", "M", "D1_d_R_minus_M"), "D2": ("M", "C", "D2_d_M_minus_C")}.items():
        trip = res["tripwires"]["D1_R_better_than_M_by_more_than_M_skill" if comp == "D1" else "D2_C_skill_over_twice_M"]
        threshold = practical_threshold(skill[small], brier_b)
        if trip:
            res["judgement"][comp] = {"verdict": "STOPPED_TRIPWIRE", "threshold": threshold}
            continue
        res["judgement"][comp] = judge(v[key], e[key], res["years"][comp], res["multiple_testing"][comp]["p_holm"], threshold, "ci975",
                                       calibrated(large), None, small_skill_not_positive=skill[small] <= 0,
                                       large_skill_positive=skill[large] > 0)
        res["judgement"][comp]["skill_ratio_large_over_small"] = skill[large] / skill[small] if skill[small] else float("inf")
    return res


def render_ms_a(r: dict) -> str:
    v, e, j = r["by_period"]["validation"], r["by_period"]["exploration"], r["judgement"]
    d = v["d_reference_minus_candidate"]
    L = [f"# E036 (MS-A): do amihud_rel_168 and trade_size_rel_24 add move-size information? Verdict: **{j['verdict']}**", "",
         f"Generated {r['generated_at'][:16]} UTC · code {r.get('code', '?')} · development data only · hypothesis-generating "
         "(about 35 experiments have seen these periods) · statistics, not economics", "",
         f"Rows: {r['rows']['common_rows']:,} common frame rows (E013: {r['rows']['E013_common_rows']:,}; "
         f"{r['rows']['rows_the_reference_alone_would_have_had_but_the_candidate_lacks']:,} hours lost because a new input is "
         f"undefined there); {r['rows']['out_of_sample_rows']:,} out-of-sample rows in {r['rows']['folds']} folds; EWMA unavailable on "
         f"{r['rows']['ewma_rows_unavailable']} rows.", "",
         "| validation (exploration) | reference (9 inputs) | candidate (11 inputs) | EWMA rule |", "|---|---|---|---|"]
    for key, label, fmt in (("brier", "Brier", ".5f"), ("skill", "skill vs in-period base rate", "+.5f"), ("log_loss", "log loss", ".5f"),
                            ("ece", "ECE", ".4f"), ("rho_p_vs_abs_return", "Spearman rho(p, |r|)", "+.4f")):
        L.append(f"| {label} | {v['reference'][key]:{fmt}} ({e['reference'][key]:{fmt}}) | {v['candidate'][key]:{fmt}} ({e['candidate'][key]:{fmt}}) | "
                 f"{v['ewma_rule'][key]:{fmt}} ({e['ewma_rule'][key]:{fmt}}) |")
    L += [f"| E013 bucket rule (validation) | {v['reference']['e013_buckets_ok']} | {v['candidate']['e013_buckets_ok']} | |", "",
          f"**Primary:** validation d = Brier(reference) − Brier(candidate) = {d['diff']:+.6f} [{d['ci95'][0]:+.6f}, {d['ci95'][1]:+.6f}] "
          f"(95%), bootstrap p {d['p_two_sided']:.4f} (one comparison in its family). Practical threshold {j['threshold']:.6f}; "
          f"exploration d {e['d_reference_minus_candidate']['diff']:+.6f} [{e['d_reference_minus_candidate']['ci95'][0]:+.6f}, "
          f"{e['d_reference_minus_candidate']['ci95'][1]:+.6f}].", "",
          "d per year: " + "; ".join(f"{k} {x:+.5f}" for k, x in r["years_d"].items()), ""]
    if "criteria" in j:
        L += ["| registered criterion | result |", "|---|---|"] + [f"| {k} | {x} |" for k, x in j["criteria"].items()]
        L += ["", f"Candidate skill / reference skill: {j['skill_ratio_candidate_over_reference']:.4f} (bar 1.10; tripwire 1.5)"]
    L += ["", "Candidate coefficients (median across folds, share of folds with the median's sign): " +
          "; ".join(f"{c} {r['coefficients']['candidate']['median'][c]:+.4f} ({r['coefficients']['candidate']['sign_agreement'][c]:.2f})"
                    for c in MS_CANDIDATE)]
    return "\n".join(L) + "\n"


def render_d1_d2(r: dict) -> str:
    v, e = r["by_period"]["validation"], r["by_period"]["exploration"]
    L = [f"# E037 (direction): D1 {r['judgement']['D1']['verdict']} · D2 {r['judgement']['D2']['verdict']}", "",
         f"Generated {r['generated_at'][:16]} UTC · code {r.get('code', '?')} · development data only · directional track only · "
         "hypothesis-generating (about 35 experiments, about ten directional, have seen these rows) · statistics, not economics", "",
         f"Rows: {r['rows']['out_of_sample_rows']:,} out-of-sample rows (E032: {r['rows']['E032_out_of_sample_rows']:,}; "
         f"{r['rows']['rows_E032_had_but_up_streak_6_lacks']} lost to up_streak_6) in {r['rows']['folds']} folds. M identical to E032: "
         f"{r['E032_cross_check']['identical_to_E032']}.", "",
         "| validation (exploration) | M (8 inputs) | R (M without the 4 category scores) | C (M + up_streak_6) | F (taker-buy share) |",
         "|---|---|---|---|---|"]
    for key, label, fmt in (("brier", "Brier", ".6f"), ("skill_vs_base_rate", "skill vs the leak-free base rate", "+.5f"),
                            ("ece", "ECE", ".4f"), ("rho_p_vs_return", "Spearman rho(p, 1h return)", "+.4f")):
        L.append(f"| {label} | " + " | ".join(f"{v['models'][k][key]:{fmt}} ({e['models'][k][key]:{fmt}})" for k in ("M", "R", "C", "F")) + " |")
    L.append("| E013 bucket rule (validation) | " + " | ".join(str(v["models"][k]["e013_buckets_ok"]) for k in ("M", "R", "C", "F")) + " |")
    L += [f"| base rate Brier | {v['base_rate']['brier']:.6f} ({e['base_rate']['brier']:.6f}) | | | |", ""]
    for comp, key, what in (("D1", "D1_d_R_minus_M", "Brier(R) − Brier(M): do the category scores help?"),
                            ("D2", "D2_d_M_minus_C", "Brier(M) − Brier(C): does up_streak_6 help?")):
        d, j, h = v[key], r["judgement"][comp], r["multiple_testing"][comp]
        L += [f"## {comp}: {what} **{j['verdict']}**", "",
              f"Validation d {d['diff']:+.7f}, 95% [{d['ci95'][0]:+.7f}, {d['ci95'][1]:+.7f}], 97.5% [{d['ci975'][0]:+.7f}, {d['ci975'][1]:+.7f}]; "
              f"p {h['p']:.4f}, Holm-adjusted {h['p_holm']:.4f}. Practical threshold {j['threshold']:.7f}. Exploration d {e[key]['diff']:+.7f} "
              f"[{e[key]['ci95'][0]:+.7f}, {e[key]['ci95'][1]:+.7f}].", "",
              "d per year: " + "; ".join(f"{k} {x:+.6f}" for k, x in r["years"][comp].items()), ""]
        if "criteria" in j:
            L += ["| registered criterion | result |", "|---|---|"] + [f"| {k} | {x} |" for k, x in j["criteria"].items()]
            L += ["", f"Skill of the larger model / the smaller: {j['skill_ratio_large_over_small']:.4f} (bar 1.10)", ""]
    c = r["coefficients"]["C"][UP_STREAK]
    L += [f"up_streak_6 in C: median coefficient {c['median']:+.4f} (standardised), same sign in {c['sign_agreement']:.0%} of folds.", "",
          "Descriptive economics (decide nothing; no profitability is claimed): gross signed return per hour at a 0.10% round trip — " +
          "; ".join(f"{k} {100 * v['models'][k]['gross_signed_return_per_hour']:+.4f}%" for k in ("M", "R", "C", "F")) + " (validation)."]
    return "\n".join(L) + "\n"


def render(r: dict) -> str:
    L = [f"# {r['experiment']}: Phase 3 reference reproduction", "",
         f"Generated {r['generated_at'][:16]} UTC. Tolerance {TOLERANCE:g} absolute on every float, exact on every count "
         "and label. Expected figures are read from the committed result files.", "",
         f"**{'REPRODUCES' if r['reproduces'] else 'DOES NOT REPRODUCE: the track stops here'}** ({r['track']})", ""]
    if r["differences"]:
        L += ["Differences:", ""] + [f"- `{d}`" for d in r["differences"]]
    if "reproduced" in r:
        g = r["reproduced"]
        v, e = g["E018_full"]["validation"], g["E018_full"]["exploration"]
        L += ["| figure | reproduced |", "|---|---|",
              f"| folds · frame rows · out-of-sample rows | {g['folds']} · {g['rows_common']:,} · {g['oos_rows']:,} |",
              f"| reference validation Brier · skill · ECE · rho | {v['brier']!r} · {v['skill']!r} · {v['ece']!r} · {v['rho_p_vs_abs_return']!r} |",
              f"| reference exploration Brier · skill | {e['brier']!r} · {e['skill']!r} |",
              f"| EWMA rule validation Brier · skill | {g['E019_ewma']['validation']['brier']!r} · {g['E019_ewma']['validation']['skill']!r} |",
              f"| EWMA minus reference, validation (paired, 2,000 resamples) | {g['E019_ewma_minus_incumbent_validation']['diff']!r} "
              f"[{g['E019_ewma_minus_incumbent_validation']['ci_low']!r}, {g['E019_ewma_minus_incumbent_validation']['ci_high']!r}] |"]
    else:
        L += [f"E032's own code was re-run into `{r['reproduction_files']}/`; every number of its result was compared with "
              "`research/results/E032/direction_probability.json`."]
    return "\n".join(L) + "\n"


def compare_main(now: str) -> int:
    import subprocess

    code = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "agent"], capture_output=True, text=True).stdout.strip()
    if dirty:
        print("refusing to run: agent/ has uncommitted changes, so the result could not name the exact code that produced it")
        return 2
    for experiment, fn, render_fn, name in (("E036", run_ms_a, render_ms_a, "ms_a"), ("E037", run_d1_d2, render_d1_d2, "d1_d2")):
        r = {**fn(), "generated_at": now, "code": code}
        out = RESULTS / experiment
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        (out / f"{name}.md").write_text(render_fn(r), encoding="utf-8")
        verdicts = r["judgement"]["verdict"] if "verdict" in r["judgement"] else {k: x["verdict"] for k, x in r["judgement"].items()}
        print(f"{experiment}: {verdicts}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["reproduce", "compare"])
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc).isoformat()
    if args.phase == "compare":
        return compare_main(now)
    ok = True
    for experiment, fn in (("E036", reproduce_move_size), ("E037", reproduce_direction)):
        r = {"experiment": experiment, "generated_at": now, **fn()}
        out = RESULTS / experiment
        out.mkdir(parents=True, exist_ok=True)
        (out / "reproduction.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        (out / "reproduction.md").write_text(render(r), encoding="utf-8")
        print(f"{experiment}: {'REPRODUCES' if r['reproduces'] else 'DOES NOT REPRODUCE'} ({len(r['differences'])} differences)")
        ok = ok and r["reproduces"]
    return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
