"""
E035 (RESEARCH-ONLY, pre-registered before this code): does ONE shared calibration slope with four six-hour block
intercepts remove E027's intraday miscalibration without E031's cost in the confident tail? One variant fixed in
advance (research/experiments/E035_shared_slope_calibration.json); the second and last variant on this line.

    python -m agent.research.shared_slope_calibration --experiment E035

Everything except the calibrator is E031's code, imported, not copied: the nine inputs, the same logistic, the same
frame, identical rows, the same 27 folds, the same recorded calibration slices, the same scores and the same four
hypotheses. The incumbent fits one Platt map per fold (E013); the variant fits p -> sigmoid(a * logit(p) + b_k), one
slope a for all blocks and one intercept b_k per block of the reference hour, on the same slice (5 parameters; E031's
four maps had 8). E031's fallback rule is kept: if any block of a slice has < 100 rows or one class, that fold uses
its single map.

Development data only: build_frame / load_bars truncate at the holdout's start; no prospective outcome is read.
Nothing here touches the live system, move_size_1h_v1 or the direction track. Hypothesis-generating (validation wear).
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.block_calibration import (MIN_BLOCK_CALIB_ROWS, RecordingPlatt, block_platt, expected_slices, judge,
                                              scores)
from agent.research.model_test import _logit
from agent.research.regime_calibration import REGIMES, assign
from agent.research.simple_baselines import paired_difference
from agent.research.slice_calibration import BLOCK_NAMES, block_group
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)
E031_RESULT = Path("research/results/E031/block_calibration.json")


class SharedSlopeBlockCalibrator:
    """p -> sigmoid(a * logit(p) + b_k): one slope for every block, one intercept per block. Unregularised."""

    def fit(self, p, y, hours: pd.DatetimeIndex):
        from sklearn.linear_model import LogisticRegression

        self.lr = LogisticRegression(C=1e6, max_iter=5000, fit_intercept=False)
        self.lr.fit(self._design(p, hours), np.asarray(y, float))
        return self

    @staticmethod
    def _design(p, hours: pd.DatetimeIndex) -> np.ndarray:
        g = block_group(hours)
        X = np.zeros((len(g), 1 + len(BLOCK_NAMES)))
        X[:, 0] = _logit(np.asarray(p, float))
        X[np.arange(len(g)), 1 + g] = 1.0
        return X

    def transform(self, p, hours: pd.DatetimeIndex) -> np.ndarray:
        return self.lr.predict_proba(self._design(p, hours))[:, 1]

    def params(self) -> dict:
        c = self.lr.coef_[0]
        return {"slope": float(c[0]), **{f"intercept_{n}": float(b) for n, b in zip(BLOCK_NAMES, c[1:])}}


def needs_fallback(calib_y: np.ndarray, calib_hours: pd.DatetimeIndex) -> bool:
    """E031's rule, applied to the whole fold: any block with < MIN_BLOCK_CALIB_ROWS rows or one class."""
    g = block_group(calib_hours)
    for k in range(len(BLOCK_NAMES)):
        y_k = calib_y[g == k]
        if len(y_k) < MIN_BLOCK_CALIB_ROWS or len(np.unique(y_k)) < 2:
            return True
    return False


def shared_slope(calib_p, calib_y, calib_hours, test_p, test_hours, single) -> tuple[np.ndarray, dict | None]:
    """The variant for one fold. Returns (p, fitted parameters), or (single map's p, None) on the fallback."""
    if needs_fallback(np.asarray(calib_y, float), calib_hours):
        return single.transform(test_p), None
    c = SharedSlopeBlockCalibrator().fit(calib_p, calib_y, calib_hours)
    return c.transform(test_p, test_hours), c.params()


def check_reproduces_e031(res: dict) -> None:
    """Stop unless the incumbent reproduces E031's recorded incumbent to the digit."""
    rec = json.loads(E031_RESULT.read_text(encoding="utf-8"))
    for period in ("exploration", "validation"):
        mine, theirs = res["by_period"][period]["incumbent"], rec["by_period"][period]["incumbent"]
        for k in ("rows", "brier", "skill", "rho", "ece", "worst_block_offset"):
            a, b = mine[k], theirs[k]
            if (round(a, 10) if isinstance(a, float) else a) != (round(b, 10) if isinstance(b, float) else b):
                raise RuntimeError(f"incumbent does not reproduce E031 on {period}.{k}: {a} vs {b}")


def run(experiment: str) -> Path:
    from agent.research.feature_count import FULL, HORIZON, C, prepare
    from agent.research.history import load_bars
    from agent.research.live_checkpoint import TERCILES_PATH
    from agent.research.model_test import LogisticModel
    from agent.research.periods import HOLDOUT
    from agent.research.simple_baselines import simple_rules
    from agent.research.walkforward import run_walk_forward

    df, spec, folds = prepare()
    recorders: list[RecordingPlatt] = []

    def make_calibrator():
        rec = RecordingPlatt()
        recorders.append(rec)
        return rec

    preds, _ = run_walk_forward(df, list(FULL), "y", lambda: LogisticModel(C=C), spec, folds=folds, make_calibrator=make_calibrator)
    slices = expected_slices(df, list(FULL), "y", folds)
    assert len(slices) == len(recorders), "the recorded folds do not line up with the runner's"
    variant = pd.Series(np.nan, index=preds.index, dtype=float)
    e031 = pd.Series(np.nan, index=preds.index, dtype=float)
    params, fallbacks = [], 0
    for rec, (calib_hours, test_hours) in zip(recorders, slices):
        assert len(rec.calib_p) == len(calib_hours) and len(rec.test_p) == len(test_hours), "fold rows misaligned"
        p, fitted = shared_slope(rec.calib_p, rec.calib_y, calib_hours, rec.test_p, test_hours, rec.platt)
        variant.loc[test_hours] = p
        if fitted is None:
            fallbacks += 1
        else:
            params.append(fitted)
        e031.loc[test_hours] = block_platt(rec.calib_p, rec.calib_y, calib_hours, rec.test_p, test_hours, rec.platt)[0]
    assert not variant.isna().any() and not e031.isna().any(), "every out-of-sample row must have a variant probability"

    joined = preds.join(df[["period", "fwd_%dh" % HORIZON, "rv_168"]], how="left").sort_index()
    variant, e031 = variant.reindex(joined.index), e031.reindex(joined.index)
    bars, _, _ = load_bars(end=HOLDOUT.start)  # truncated at the holdout; the free rule needs only candles
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(joined.index)
    cuts = tuple(json.loads(TERCILES_PATH.read_text(encoding="utf-8"))["tercile_cut_points"])
    regime_all = assign(np.exp(joined["rv_168"].to_numpy(float)), cuts)  # prepare() stores log(rv_168)

    pf = pd.DataFrame(params)
    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "rows": int(len(joined)), "folds_calibrated": len(recorders), "folds_on_the_fallback": fallbacks,
           "fitted_parameters_across_folds": {c: {"mean": float(pf[c].mean()), "sd": float(pf[c].std(ddof=1)),
                                                  "min": float(pf[c].min()), "max": float(pf[c].max())} for c in pf.columns},
           "by_period": {}}
    for period in ("exploration", "validation"):
        m = (joined["period"] == period).to_numpy()
        idx = joined.index[m]
        y, size = joined["y"].to_numpy(float)[m], np.abs(joined["fwd_%dh" % HORIZON].to_numpy(float))[m]
        pi, pv, p31 = joined["p"].to_numpy(float)[m], variant.to_numpy(float)[m], e031.to_numpy(float)[m]
        ew, rg = ewma.to_numpy(float)[m], regime_all[m]
        res["by_period"][period] = {"incumbent": scores(pi, y, size, ew, idx, rg), "variant": scores(pv, y, size, ew, idx, rg),
                                    "e031_four_maps_descriptive": scores(p31, y, size, ew, idx, rg),
                                    "incumbent_minus_variant_brier": paired_difference(pi, pv, y)}
    check_reproduces_e031(res)
    res["verdict"] = judge(res)  # E031's four hypotheses, the same code
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "shared_slope_calibration.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "shared_slope_calibration.md").write_text(render(res), encoding="utf-8")
    return out_dir / "shared_slope_calibration.md"


def render(r: dict) -> str:
    L = ["# E035 — one shared slope with four block intercepts: does it fix the intraday miscalibration without E031's cost? (research-only)", "",
         f"Generated {r['generated_at'][:16]} UTC · {r['rows']:,} development hours, identical rows for all · "
         f"{r['folds_calibrated']} calibrated folds · folds on the fallback: {r['folds_on_the_fallback']} · "
         "hypothesis-generating (validation wear) · never adopted into move_size_1h_v1", "",
         "Fitted across folds (mean, sd, range): " + "; ".join(
             f"{k} {v['mean']:+.3f} (sd {v['sd']:.3f}, {v['min']:+.3f} to {v['max']:+.3f})" for k, v in r["fitted_parameters_across_folds"].items()), ""]
    for period, d in r["by_period"].items():
        i, v, e, pdf = d["incumbent"], d["variant"], d["e031_four_maps_descriptive"], d["incumbent_minus_variant_brier"]
        L += [f"## {period} ({i['rows']:,} hours)", "",
              "| measure | incumbent (one Platt) | variant (shared slope + block intercepts) | E031 four maps (descriptive) |", "|---|---|---|---|"]
        for label, fn in (("Brier skill vs base rate", lambda s: f"{s['skill']:+.4f}"),
                          ("skill as a multiple of the free EWMA rule's", lambda s: f"{s['vs_ewma']['model_skill_over_ewma_skill']:.2f}×"),
                          ("Spearman ρ(p, move size)", lambda s: f"{s['rho']:+.3f}"),
                          ("ECE", lambda s: f"{s['ece']:.3f}"),
                          ("buckets n ≥ 100 within 0.05 (E013)", lambda s: "yes" if s["e013_buckets_ok"] else "no"),
                          ("calibration intercept / slope", lambda s: f"{s['calibration_line']['intercept']:+.3f} / {s['calibration_line']['slope']:.3f}"),
                          ("accuracy at 0.5", lambda s: f"{s['accuracy_at_0_5']:.3f} (naive {s['naive_accuracy']:.3f})"),
                          ("worst block offset", lambda s: f"{s['worst_block_offset']:.3f}")):
            L.append(f"| {label} | {fn(i)} | {fn(v)} | {fn(e)} |")
        L += ["", f"Brier(incumbent) − Brier(variant): {pdf['diff']:+.5f} [{pdf['ci_low']:+.5f}, {pdf['ci_high']:+.5f}] (positive = variant better)", "",
              "| block (UTC) | incumbent stated − observed | variant | E031 four maps |", "|---|---|---|---|"]
        for name in BLOCK_NAMES:
            a, b, c = i["blocks"][name], v["blocks"][name], e["blocks"][name]
            L.append(f"| {name} | {a['stated_minus_observed']:+.3f} [{a['ci95'][0]:+.3f}, {a['ci95'][1]:+.3f}] | "
                     f"{b['stated_minus_observed']:+.3f} [{b['ci95'][0]:+.3f}, {b['ci95'][1]:+.3f}] | {c['stated_minus_observed']:+.3f} |")
        L += ["", "Descriptive (never used to choose anything): per year, skill and worst block offset, incumbent → variant: "
              + "; ".join(f"{yr} {i['by_year'][yr]['skill']:+.3f}→{v['by_year'][yr]['skill']:+.3f}, "
                          f"{i['by_year'][yr]['worst_block_offset']:.3f}→{v['by_year'][yr]['worst_block_offset']:.3f}" for yr in i["by_year"]),
              "", "Descriptive: stated − observed per frozen volatility tercile, incumbent → variant: "
              + "; ".join(f"{g} {i['regimes'][g]['stated_minus_observed']:+.3f}→{v['regimes'][g]['stated_minus_observed']:+.3f}"
                          for g in REGIMES if i["regimes"][g].get("rows")), ""]
    L += ["## Pre-registered hypotheses (E031's, unchanged)", ""] + [f"- {k}: **{'HOLDS' if ok else 'FAILS'}**" for k, ok in r["verdict"].items()]
    L += ["", "*Research-only and hypothesis-generating: the validation period is worn, E027 found these offsets on these rows, "
          "and this design was chosen after E031 failed on them. Whatever the verdict, move_size_1h_v1, the live system, both "
          "shadow tracks and the checkpoints are unchanged.*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E035")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
