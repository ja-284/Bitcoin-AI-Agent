"""
E033 -- how many prospective hours does the direction shadow track need? (descriptive planning)

    python -m agent.research.direction_power --experiment E033

Registered in 970a94a before this code (research/experiments/E033_direction_track_power.json). The master plan
(Phase 3, 5A) wants the prospective direction test sized before it collects anything, without promising an answer
the sample cannot give.

Method, as registered. E032's walk-forward out-of-sample predictions are rebuilt exactly as E032 built them and must
reproduce E032's recorded Brier scores first. A paired Brier difference is a mean of per-hour terms, so each
comparison is a series d_t (positive = the second-named model is better). As in E024, every contiguous N-hour window
of the record is a possible prospective record (laid every 168 hours, within each period). The planned test runs in
each window: the window's mean of d and its 48h circular block-bootstrap 95% interval. The share of windows whose
lower end is above zero is the power. The same windows on the series centred to a zero mean over its period (the
effect removed, the autocorrelation kept) give the false-positive rate.

Development data only (load_bars stops at the holdout). Nothing is fitted for use and nothing is chosen. It assumes
the prospective effect equals the development effect, so if the true effect is smaller every "hours needed" figure
is an UNDER-estimate.
"""

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.research.direction_probability import C, HORIZON, INPUTS, ONE_FEATURE
from agent.research.metrics import reliability_table
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

N_GRID = (500, 1000, 2000, 3000, 4000, 5000, 6000, 8000, 10000, 13000)
STEP_HOURS = 168
BLOCK, N_BOOT, SEED = 48, 500, 33
SIM_SEED = 7                  # outcomes of the perfectly calibrated control
SESOI = 0.0005                # smallest effect of interest: about half of E032's development gains (0.00094 / 0.00107)
Z_SUM = 1.959964 + 0.841621   # two-sided 5%, 80% power
TERCILES = Path("research/monitoring/regime_terciles_v1.json")
E032_RECORD = Path("research/experiments/E032_direction_probability.json")
# (reference, challenger): d = (p_ref - y)^2 - (p_challenger - y)^2, positive = the challenger is better
COMPARISONS = {"model_vs_base_rate": ("p_base", "p_model"), "model_vs_one_feature": ("p_one", "p_model"),
               "one_feature_vs_base_rate": ("p_base", "p_one")}


def boot_means(d: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED, block: int = BLOCK) -> np.ndarray:
    """
    The circular block bootstrap of the MEAN of d, resampled exactly as metrics.block_bootstrap_estimates does (same
    random draws, same blocks, the last block cut to length n), but summed with cumulative sums, so a window of
    10,000 hours costs no more than one of 500. tests/test_direction_power.py checks the two agree.
    """
    d = np.asarray(d, float)
    n = len(d)
    if n < 2 * block:
        return np.empty(0)
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    last = n - (n_blocks - 1) * block
    c = np.concatenate([[0.0], np.cumsum(np.concatenate([d, d[:block]]))])
    out = np.empty(n_boot)
    for b in range(n_boot):
        s = rng.integers(0, n, size=n_blocks)
        out[b] = ((c[s[:-1] + block] - c[s[:-1]]).sum() + c[s[-1] + last] - c[s[-1]]) / n
    return out


def window_table(d: np.ndarray, n: int, period_mean: float, step: int = STEP_HOURS) -> dict:
    """The planned test in every contiguous n-hour window of d, on the real series and on the centred one."""
    starts = range(0, len(d) - n + 1, step)
    detect, detect_null, below, below_null, means = [], [], [], [], []
    for s in starts:
        w = d[s:s + n]
        est = boot_means(w)
        lo, hi = float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))
        # each resample has exactly n terms, so centring shifts every resampled mean by the same constant
        lo0, hi0 = lo - period_mean, hi - period_mean
        detect.append(lo > 0)
        detect_null.append(lo0 > 0)
        below.append(hi < SESOI)
        below_null.append(hi0 < SESOI)
        means.append(float(w.mean()))
    return {"windows": len(means), "power_lower_end_above_0": float(np.mean(detect)),
            "false_positive_rate_centred": float(np.mean(detect_null)),
            "no_improvement_fires_real": float(np.mean(below)), "no_improvement_fires_centred": float(np.mean(below_null)),
            "window_mean_p05_median_p95": [float(np.percentile(means, q)) for q in (5, 50, 95)]}


def analytic(d: np.ndarray) -> dict:
    """Whole-period mean, block-bootstrap SE, and the hours an effect of this size needs for 80% power."""
    est = boot_means(d)
    m, se = float(d.mean()), float(np.std(est, ddof=1))
    need = None if m <= 0 else int(math.ceil(len(d) * (Z_SUM * se / m) ** 2))
    return {"rows": int(len(d)), "mean": m, "se": se, "hours_for_80pct_power": need}


def calibration_spread(p: np.ndarray, y: np.ndarray, y_cal: np.ndarray, n: int, step: int = STEP_HOURS) -> dict:
    """Calibration-in-the-large and ECE across the windows, on the real outcomes and on perfectly calibrated ones."""
    rows = []
    for s in range(0, len(p) - n + 1, step):
        pw, yw, cw = p[s:s + n], y[s:s + n], y_cal[s:s + n]
        rows.append((pw.mean() - yw.mean(), reliability_table(pw, yw)[1], pw.mean() - cw.mean(), reliability_table(pw, cw)[1]))
    a = np.array(rows)
    pct = lambda k: [float(np.percentile(a[:, k], q)) for q in (5, 50, 95)]  # noqa: E731
    return {"windows": len(rows), "real": {"stated_minus_observed_p05_median_p95": pct(0), "ece_p05_median_p95": pct(1)},
            "perfectly_calibrated": {"stated_minus_observed_p05_median_p95": pct(2), "ece_p05_median_p95": pct(3)}}


def predictions():
    """E032's out-of-sample predictions, rebuilt exactly as E032 built them, plus rv_168 for the regime split."""
    from agent.research.model_test import BaseRateModel, LogisticModel, build_frame
    from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward

    df, _ = build_frame(HORIZON, [], INPUTS + ["rv_168"], "direction")  # load_bars(end=HOLDOUT.start) inside
    common = df[INPUTS + ["y"]].dropna().index  # E032's rows: rv_168 does not restrict them
    df = df.loc[common]
    spec = WalkForwardSpec(horizon_hours=HORIZON, scheme="expanding", min_train_days=365, test_block_days=90,
                           embargo_hours=24, calib_days=0)
    folds = make_folds(common, spec)
    model, _ = run_walk_forward(df, INPUTS, "y", lambda: LogisticModel(C=C), spec, folds=folds)
    one, _ = run_walk_forward(df, ONE_FEATURE, "y", lambda: LogisticModel(C=C), spec, folds=folds)
    base, _ = run_walk_forward(df, INPUTS, "y", BaseRateModel, spec, folds=folds)
    assert model.index.equals(one.index) and model.index.equals(base.index), "the candidates must be scored on identical rows"
    out = model[["p", "y"]].rename(columns={"p": "p_model"}).join(df[["period", "rv_168"]], how="left").sort_index()
    out["p_one"] = one["p"].reindex(out.index)
    out["p_base"] = base["p"].reindex(out.index)
    return out, len(folds)


def check_reproduces_e032(frame) -> dict:
    """Stop unless the rebuilt predictions give E032's recorded Brier scores to 5 decimals."""
    rec = json.loads(E032_RECORD.read_text(encoding="utf-8"))["result"]
    got = {}
    for period in ("exploration", "validation"):
        f = frame[frame["period"] == period]
        y = f["y"].to_numpy(float)
        mine = {k: round(float(np.mean((f[col].to_numpy(float) - y) ** 2)), 5)
                for k, col in (("base_rate", "p_base"), ("model", "p_model"), ("one_feature", "p_one"))}
        want = {k: round(float(v), 5) for k, v in rec[period]["brier"].items()}
        if mine != want or int(len(f)) != int(rec[period]["rows"]):
            raise RuntimeError(f"E032 not reproduced on {period}: {mine} ({len(f)} rows) vs recorded {want} ({rec[period]['rows']} rows)")
        got[period] = {"rows": int(len(f)), "brier": mine}
    return got


def run(experiment: str) -> Path:
    frame, n_folds = predictions()
    repro = check_reproduces_e032(frame)
    cuts = json.loads(TERCILES.read_text(encoding="utf-8"))["tercile_cut_points"]
    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "reproduces_e032": repro, "folds": n_folds, "step_hours": STEP_HOURS, "block": BLOCK, "n_boot": N_BOOT, "seed": SEED,
           "sesoi": SESOI, "by_period": {}}
    for period in ("exploration", "validation"):
        f = frame[frame["period"] == period]
        y = f["y"].to_numpy(float)
        p = {k: f[k].to_numpy(float) for k in ("p_model", "p_one", "p_base")}
        y_cal = (np.random.default_rng(SIM_SEED).uniform(size=len(y)) < p["p_model"]).astype(float)
        rv = f["rv_168"].to_numpy(float)
        regime = np.where(np.isnan(rv), "unknown", np.where(rv < cuts[0], "low", np.where(rv < cuts[1], "mid", "high")))
        entry = {"rows": int(len(y)), "comparisons": {}, "calibration_of_model": {}}
        for name, (ref, ch) in COMPARISONS.items():
            d = (p[ref] - y) ** 2 - (p[ch] - y) ** 2
            whole = analytic(d)
            entry["comparisons"][name] = {
                "whole_period": whole,
                "by_regime_mean": {r: {"rows": int((regime == r).sum()), "mean": float(d[regime == r].mean())}
                                   for r in ("low", "mid", "high") if (regime == r).any()},
                "by_window_hours": {str(n): window_table(d, n, whole["mean"]) for n in N_GRID if n <= len(d)}}
            logger.info("%s %s: mean %.6f se %.6f need %s", period, name, whole["mean"], whole["se"], whole["hours_for_80pct_power"])
        for n in N_GRID:
            if n <= len(y):
                entry["calibration_of_model"][str(n)] = calibration_spread(p["p_model"], y, y_cal, n)
        res["by_period"][period] = entry
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "direction_power.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (out_dir / "direction_power.md").write_text(render(res), encoding="utf-8")
    return out_dir / "direction_power.md"


def render(r: dict) -> str:
    L = ["# E033 — how many prospective hours does the direction shadow track need? (descriptive planning)", "",
         f"Generated {r['generated_at'][:16]} UTC · E032's out-of-sample predictions rebuilt ({r['folds']} folds) and checked "
         f"against E032's Brier scores: exploration {r['reproduces_e032']['exploration']['rows']:,} rows, validation "
         f"{r['reproduces_e032']['validation']['rows']:,} rows, both reproduced · windows every {r['step_hours']} h · "
         f"{r['block']}h circular block bootstrap, {r['n_boot']} resamples · development data only.", "",
         "*Assumes the prospective effect equals the development effect. If it is smaller, every \"hours needed\" figure "
         "below is an UNDER-estimate.*", ""]
    for period, e in r["by_period"].items():
        L += [f"## {period} ({e['rows']:,} hours)", ""]
        for name, c in e["comparisons"].items():
            w = c["whole_period"]
            need = "not reachable (no positive effect)" if w["hours_for_80pct_power"] is None else f"{w['hours_for_80pct_power']:,}"
            L += [f"### {name.replace('_', ' ')}", "",
                  f"Whole period: mean Brier gain {w['mean']:+.6f}, SE {w['se']:.6f}; hours for 80% power ≈ **{need}**. "
                  "By regime (mean gain): " + "; ".join(f"{k} {v['mean']:+.6f} (n {v['rows']:,})" for k, v in c["by_regime_mean"].items()), "",
                  "| N hours | windows | power (lower end > 0) | false positives, centred | 'no improvement' fires (real / centred) | window gain p05 / median / p95 |",
                  "|---|---|---|---|---|---|"]
            for n, t in c["by_window_hours"].items():
                q = t["window_mean_p05_median_p95"]
                L.append(f"| {int(n):,} | {t['windows']} | {t['power_lower_end_above_0']:.2f} | {t['false_positive_rate_centred']:.3f} | "
                         f"{t['no_improvement_fires_real']:.2f} / {t['no_improvement_fires_centred']:.2f} | {q[0]:+.5f} / {q[1]:+.5f} / {q[2]:+.5f} |")
            L.append("")
        L += ["### calibration of the eight-input model across windows (5th / median / 95th percentile)", "",
              "| N hours | windows | stated − observed (real) | stated − observed (perfectly calibrated) | ECE (real) | ECE (perfectly calibrated) |",
              "|---|---|---|---|---|---|"]
        fmt = lambda v: f"{v[0]:+.3f} / {v[1]:+.3f} / {v[2]:+.3f}"  # noqa: E731
        for n, c in e["calibration_of_model"].items():
            L.append(f"| {int(n):,} | {c['windows']} | {fmt(c['real']['stated_minus_observed_p05_median_p95'])} | "
                     f"{fmt(c['perfectly_calibrated']['stated_minus_observed_p05_median_p95'])} | {fmt(c['real']['ece_p05_median_p95'])} | "
                     f"{fmt(c['perfectly_calibrated']['ece_p05_median_p95'])} |")
        L.append("")
    L += ["*Descriptive planning only: nothing was fitted for use, nothing was chosen, and no rule or model changed. "
          "The live BUY/HOLD/SELL signal, move_size_1h_v1 and its checkpoints are untouched.*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E033")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
