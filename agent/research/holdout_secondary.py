"""
E023: the secondary hypotheses, evaluated on the same window as E014 -- and ONLY there.

research/experiments/E023_holdout_secondary_hypotheses.json registered five hypotheses from
E018-E022 before the holdout was ever opened, because they were generated on a validation period
twenty-plus experiments had already examined and can only be CONFIRMED on clean data. This module
evaluates them, exactly as written there.

It never loads data. It receives the candles and the frame that agent/research/holdout_eval.py
loaded through its one guarded route (load_bars with allow_holdout=True and a logged reason for
the real run; truncated at the holdout for the dry run), and the same walk-forward function E014
uses, so the holdout's access rules and fold layout are E014's own. A test pins that down.

E014 is not changed by any of this. Its verdict is computed first and separately, and nothing here
can alter it.
"""

import numpy as np
import pandas as pd

from agent.research.metrics import brier_score
from agent.research.simple_baselines import paired_difference, simple_rules
from agent.research.threshold_test import vol_scaled_threshold

# Fixed by E023 and the experiments it draws on -- never chosen here.
VOLATILITY_GROUP = ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168"]
E018_SIX = ["tr_mean_14_rel", "trades_rel_24h", "rv_168", "hour_cos", "hour_sin", "is_weekend"]
H1_RATIO, H3_MAX_SKILL, H4_MAX_VOL_COST, H5_MIN_SHARE = 1.10, 0.01, 0.40, 0.95


def _skill(p: np.ndarray, y: np.ndarray) -> float:
    base = float(np.mean(y))
    b_base = brier_score(np.full(len(y), base), y)
    return 1.0 - brier_score(p, y) / b_base if b_base > 0 else float("nan")


def evaluate(df_sz: pd.DataFrame, cols: list[str], bars, window, fit_and_score) -> dict:
    """
    df_sz: E014's move-size frame (fixed 0.25% target in "y", the six log transforms applied).
    fit_and_score(df, cols, horizon, window, calib_days, calibrator) -> (window predictions, folds):
    E014's own walk-forward, passed in so that the fold layout is identical to object D's.
    """
    # the volatility-scaled target (E021), from the same candles, point in time by construction
    thresholds = vol_scaled_threshold(bars).reindex(df_sz.index)
    ret = df_sz["fwd_1h"]
    df = df_sz.copy()
    df["y_vol"] = (ret.abs() > thresholds).astype(float).where(ret.notna() & thresholds.notna())
    df = df[df[cols + ["y", "y_vol"]].notna().all(axis=1)]  # identical rows for every comparison
    df_vol = df.copy()
    df_vol["y"] = df_vol["y_vol"]

    def score(frame, use_cols):
        preds, _ = fit_and_score(frame, list(use_cols), 1, window, 90, "platt")
        return preds

    fixed = score(df, cols)                       # object D, rebuilt on the common rows
    scaled = score(df_vol, cols)
    idx = fixed.index.intersection(scaled.index)
    fixed, scaled = fixed.loc[idx], scaled.loc[idx]
    y_fixed, y_scaled = fixed["y"].to_numpy(float), scaled["y"].to_numpy(float)
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(idx).to_numpy(float)
    ok = ~np.isnan(ewma)

    out: dict = {"rows": int(len(idx)), "rows_with_reference": int(ok.sum())}

    # H1 -- the model against the free rule, fixed target, identical rows
    s_model, s_ref = _skill(fixed["p"].to_numpy(float)[ok], y_fixed[ok]), _skill(ewma[ok], y_fixed[ok])
    d = paired_difference(ewma[ok], fixed["p"].to_numpy(float)[ok], y_fixed[ok])  # Brier(ref) - Brier(model)
    out["H1"] = {"model_skill": s_model, "reference_skill": s_ref,
                 "ratio": s_model / s_ref if s_ref > 0 else float("inf"),
                 "reference_brier_minus_model": d,
                 # the rule exactly as registered in E023 -- no special cases added afterwards
                 "pass": bool(s_model >= H1_RATIO * s_ref and d["ci_low"] > 0)}

    # H2 -- the fixed target is the more predictable one
    s_fixed, s_scaled = _skill(fixed["p"].to_numpy(float), y_fixed), _skill(scaled["p"].to_numpy(float), y_scaled)
    out["H2"] = {"skill_fixed": s_fixed, "skill_scaled": s_scaled, "pass": bool(s_fixed > s_scaled)}

    # H3 -- once the level is divided out, the free rule knows (almost) nothing
    s_ref_scaled = _skill(ewma[ok], y_scaled[ok])
    out["H3"] = {"reference_skill_on_scaled_target": s_ref_scaled, "pass": bool(s_ref_scaled < H3_MAX_SKILL)}

    # H4 -- trade intensity carries the within-regime timing
    singles = {}
    for c in cols:
        preds = score(df_vol, [c]).reindex(idx)
        singles[c] = _skill(preds["p"].to_numpy(float), y_scaled)
    best = max(singles, key=singles.get)
    without_vol = score(df_vol, [c for c in cols if c not in VOLATILITY_GROUP]).reindex(idx)
    s_without = _skill(without_vol["p"].to_numpy(float), y_scaled)
    vol_cost = 1.0 - s_without / s_scaled if s_scaled > 0 else float("nan")
    out["H4"] = {"single_input_skill": singles, "best_single_input": best,
                 "skill_without_volatility_group": s_without, "volatility_group_cost": vol_cost,
                 "pass": bool(best == "trades_rel_168h" and vol_cost < H4_MAX_VOL_COST)}

    # H5 -- six inputs keep >= 95% of the nine-input skill, fixed target
    six = score(df, E018_SIX).reindex(idx)
    s_six = _skill(six["p"].to_numpy(float), y_fixed)
    out["H5"] = {"skill_six": s_six, "skill_nine": s_fixed,
                 "share": s_six / s_fixed if s_fixed > 0 else float("nan"),
                 "pass": bool(s_fixed > 0 and s_six >= H5_MIN_SHARE * s_fixed)}

    out["held"] = [h for h in ("H1", "H2", "H3", "H4", "H5") if out[h]["pass"]]
    return out


def render(e: dict, dry_run: bool) -> list[str]:
    title = "## E023 — secondary hypotheses (registered before unsealing; they cannot change E014's verdict)"
    L = ["", title, "",
         ("*Dry run on the already-seen validation period: these numbers prove the code and should sit close to the "
          "development values in E023 -- they are NOT evidence.*" if dry_run else
          "*One-time evaluation on the sealed holdout. Reported hypothesis by hypothesis; not summarised into one verdict.*"),
         "", f"Identical rows for every comparison: {e['rows']} ({e['rows_with_reference']} with the free-rule reference).", "",
         "| # | hypothesis | measured | pass |", "|---|---|---|---|"]
    h = e
    L.append("| H1 | model ≥ 1.10× the free rule's skill, interval excluding zero | %+.4f vs %+.4f (%.2f×), lead %+.5f [%+.5f, %+.5f] | %s |" % (
        h["H1"]["model_skill"], h["H1"]["reference_skill"], h["H1"]["ratio"],
        h["H1"]["reference_brier_minus_model"]["diff"], h["H1"]["reference_brier_minus_model"]["ci_low"],
        h["H1"]["reference_brier_minus_model"]["ci_high"], "YES" if h["H1"]["pass"] else "no"))
    L.append("| H2 | fixed target more predictable than volatility-scaled | %+.4f vs %+.4f | %s |" % (
        h["H2"]["skill_fixed"], h["H2"]["skill_scaled"], "YES" if h["H2"]["pass"] else "no"))
    L.append("| H3 | free rule's skill on the scaled target < 0.01 | %+.4f | %s |" % (
        h["H3"]["reference_skill_on_scaled_target"], "YES" if h["H3"]["pass"] else "no"))
    L.append("| H4 | `trades_rel_168h` best single input on the scaled target; volatility group < 40%% of its skill | best `%s`; volatility cost %.0f%% | %s |" % (
        h["H4"]["best_single_input"], 100 * h["H4"]["volatility_group_cost"], "YES" if h["H4"]["pass"] else "no"))
    L.append("| H5 | six inputs keep ≥ 95%% of the nine-input skill | %.1f%% | %s |" % (
        100 * h["H5"]["share"], "YES" if h["H5"]["pass"] else "no"))
    L += ["", "Held: %d of 5 (%s)." % (len(e["held"]), ", ".join(e["held"]) or "none")]
    return L
