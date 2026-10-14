"""
E031 (RESEARCH-ONLY, pre-registered in 61db93d before this code): does a time-of-day-conditional CALIBRATION remove
the intraday miscalibration E027 found? One variant fixed in advance (research/experiments/E031_block_calibration.json).

    python -m agent.research.block_calibration --experiment E031

The model is untouched: the nine inputs, the same logistic, the same frame, identical rows and the same 27 folds.
Only the calibration layer differs. The incumbent fits ONE Platt map per fold on the fold's purged 90-day slice
(E013); the variant fits FOUR on the same slice, one per six-hour UTC block of the reference hour (E027's blocks),
and maps each test row with its block's map. A block with < 100 calibration rows or one class falls back to the
fold's single map (fixed in advance, counted).

Development data only: build_frame / load_bars truncate at the holdout's start; no prospective outcome is read.
Nothing here touches the live system or the frozen artefact move_size_1h_v1. Hypothesis-generating (validation wear).
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.checkpoint_power import e013_passes
from agent.research.diagnose import spearman
from agent.research.metrics import brier_score, reliability_table
from agent.research.model_test import PlattCalibrator
from agent.research.regime_calibration import REGIMES, assign, group_table
from agent.research.simple_baselines import paired_difference
from agent.research.slice_calibration import BLOCK_NAMES, block_group
from agent.research.walkforward import _slice
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)
MIN_BLOCK_CALIB_ROWS = 100  # the fallback rule, fixed in advance
RANKING_TOLERANCE = 0.02    # H_d (E018's ranking-preserved rule)


class RecordingPlatt:
    """The incumbent's PlattCalibrator, which also keeps what it was given: the fold's calibration-slice raw
    probabilities and outcomes (fit) and its test rows' raw probabilities (transform)."""

    def __init__(self):
        self.platt = PlattCalibrator()
        self.calib_p = self.calib_y = self.test_p = None

    def fit(self, p, y):
        self.calib_p, self.calib_y = np.asarray(p, float), np.asarray(y, float)
        self.platt.fit(p, y)

    def transform(self, p):
        self.test_p = np.asarray(p, float)
        return self.platt.transform(p)


def expected_slices(df: pd.DataFrame, cols: list[str], label: str, folds) -> list[tuple[pd.DatetimeIndex, pd.DatetimeIndex]]:
    """(calibration hours, test hours) of every fold the walk-forward runner calibrates, in its order. Mirrors
    run_walk_forward exactly (same `usable`, same _slice, same skips), and run() asserts the lengths agree."""
    usable = df[cols + [label]].dropna()
    out = []
    for fold in folds:
        test = _slice(usable, fold.test_start, fold.test_end)
        if len(test) == 0:
            continue
        calib = _slice(usable, fold.calib_start, fold.calib_end) if fold.calib_start is not None else None
        if calib is None or len(calib) == 0:
            continue
        out.append((calib.index, test.index))
    return out


def block_platt(calib_p, calib_y, calib_hours, test_p, test_hours, single: PlattCalibrator) -> tuple[np.ndarray, list[str]]:
    """The variant for one fold: a Platt map per six-hour block, fitted on that block's calibration rows; the
    fold's single map where a block has < MIN_BLOCK_CALIB_ROWS rows or one class. Returns (p, fallbacks used)."""
    cb, tb = block_group(calib_hours), block_group(test_hours)
    out = np.empty(len(test_p))
    fallbacks = []
    for k, name in enumerate(BLOCK_NAMES):
        cm, tm = cb == k, tb == k
        if not tm.any():
            continue
        y_k = calib_y[cm]
        if cm.sum() < MIN_BLOCK_CALIB_ROWS or len(np.unique(y_k)) < 2:
            fallbacks.append(name)
            out[tm] = single.transform(test_p[tm])
            continue
        c = PlattCalibrator()
        c.fit(calib_p[cm], y_k)
        out[tm] = c.transform(test_p[tm])
    return out, fallbacks


def worst_block_offset(table: dict) -> float:
    return max(abs(t["stated_minus_observed"]) for t in table.values())


def calibration_line(p: np.ndarray, y: np.ndarray) -> dict:
    """Calibration intercept and slope: unregularised logistic regression of the outcome on logit(p)."""
    from sklearn.linear_model import LogisticRegression

    q = np.clip(p, 1e-6, 1 - 1e-6)
    lr = LogisticRegression(C=1e6, max_iter=2000).fit(np.log(q / (1 - q)).reshape(-1, 1), y)
    return {"intercept": float(lr.intercept_[0]), "slope": float(lr.coef_[0][0])}


def scores(p, y, size, ewma, index, regime) -> dict:
    base = float(y.mean())
    b, b_base = brier_score(p, y), brier_score(np.full(len(y), base), y)
    ok = ~np.isnan(ewma)
    b_ewma = brier_score(ewma[ok], y[ok])
    ece_ok, buckets_ok, ece = e013_passes(p, y)
    blocks = group_table(p, y, block_group(index), BLOCK_NAMES)
    years = {}
    for yr in sorted(set(index.year)):
        m = index.year == yr
        yb = float(y[m].mean())
        years[str(yr)] = {"rows": int(m.sum()),
                          "skill": 1 - brier_score(p[m], y[m]) / brier_score(np.full(int(m.sum()), yb), y[m]),
                          "worst_block_offset": worst_block_offset(group_table(p[m], y[m], block_group(index[m]), BLOCK_NAMES))}
    return {"rows": int(len(y)), "brier": b, "skill": 1 - b / b_base,
            "vs_ewma": {"rows_with_rule": int(ok.sum()), "model_brier": brier_score(p[ok], y[ok]), "ewma_brier": b_ewma,
                        "model_skill_over_ewma_skill": (1 - brier_score(p[ok], y[ok]) / brier_score(np.full(int(ok.sum()), y[ok].mean()), y[ok]))
                        / (1 - b_ewma / brier_score(np.full(int(ok.sum()), y[ok].mean()), y[ok]))},
            "rho": spearman(p, size), "ece": ece, "e013_ece_ok": bool(ece_ok), "e013_buckets_ok": bool(buckets_ok),
            "calibration_line": calibration_line(p, y), "mean_stated": float(p.mean()), "observed": base,
            "accuracy_at_0_5": float(np.mean((p > 0.5) == (y > 0.5))), "naive_accuracy": max(base, 1 - base),
            "blocks": blocks, "worst_block_offset": worst_block_offset(blocks), "by_year": years,
            "regimes": group_table(p, y, regime, REGIMES)}


def judge(r: dict) -> dict:
    """The four pre-registered hypotheses, exactly as written. Pure."""
    inc, var = {p: r["by_period"][p]["incumbent"] for p in r["by_period"]}, {p: r["by_period"][p]["variant"] for p in r["by_period"]}
    h_a = all(var[p]["worst_block_offset"] <= 0.5 * inc[p]["worst_block_offset"] for p in inc)
    h_b = r["by_period"]["validation"]["incumbent_minus_variant_brier"]["ci_high"] >= 0
    h_c = all(var[p]["ece"] <= 0.03 for p in var) and var["validation"]["e013_buckets_ok"]
    h_d = abs(var["validation"]["rho"] - inc["validation"]["rho"]) <= RANKING_TOLERANCE
    return {"H_a_removes_the_offsets": bool(h_a), "H_b_no_skill_loss": bool(h_b), "H_c_calibration": bool(h_c),
            "H_d_ranking": bool(h_d)}


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
    fallbacks: dict[str, int] = {}
    for rec, (calib_hours, test_hours) in zip(recorders, slices):
        assert len(rec.calib_p) == len(calib_hours) and len(rec.test_p) == len(test_hours), "fold rows misaligned"
        p, used = block_platt(rec.calib_p, rec.calib_y, calib_hours, rec.test_p, test_hours, rec.platt)
        variant.loc[test_hours] = p
        for name in used:
            fallbacks[name] = fallbacks.get(name, 0) + 1
    assert not variant.isna().any(), "every out-of-sample row must have a variant probability"

    joined = preds.join(df[["period", "fwd_%dh" % HORIZON, "rv_168"]], how="left").sort_index()
    variant = variant.reindex(joined.index)
    bars, _, _ = load_bars(end=HOLDOUT.start)  # truncated at the holdout; the free rule needs only candles
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(joined.index)
    cuts = tuple(json.loads(TERCILES_PATH.read_text(encoding="utf-8"))["tercile_cut_points"])
    regime_all = assign(np.exp(joined["rv_168"].to_numpy(float)), cuts)  # prepare() stores log(rv_168)

    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "rows": int(len(joined)), "folds_calibrated": len(recorders), "fallback_blocks_used": fallbacks, "by_period": {}}
    for period in ("exploration", "validation"):
        m = (joined["period"] == period).to_numpy()
        idx = joined.index[m]
        y, size = joined["y"].to_numpy(float)[m], np.abs(joined["fwd_%dh" % HORIZON].to_numpy(float))[m]
        pi, pv, ew, rg = joined["p"].to_numpy(float)[m], variant.to_numpy(float)[m], ewma.to_numpy(float)[m], regime_all[m]
        res["by_period"][period] = {"incumbent": scores(pi, y, size, ew, idx, rg), "variant": scores(pv, y, size, ew, idx, rg),
                                    "incumbent_minus_variant_brier": paired_difference(pi, pv, y)}
    res["verdict"] = judge(res)
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "block_calibration.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "block_calibration.md").write_text(render(res), encoding="utf-8")
    return out_dir / "block_calibration.md"


def render(r: dict) -> str:
    L = ["# E031 — does a time-of-day-conditional calibration remove the intraday miscalibration? (research-only)", "",
         f"Generated {r['generated_at'][:16]} UTC · {r['rows']:,} development hours, identical rows for both · "
         f"{r['folds_calibrated']} calibrated folds · fallback to the single map: {r['fallback_blocks_used'] or 'never'} · "
         "hypothesis-generating (validation wear) · never adopted into move_size_1h_v1", ""]
    for period, d in r["by_period"].items():
        i, v, pdf = d["incumbent"], d["variant"], d["incumbent_minus_variant_brier"]
        L += [f"## {period} ({i['rows']:,} hours)", "",
              "| measure | incumbent (one Platt) | variant (four block Platts) |", "|---|---|---|",
              f"| Brier skill vs base rate | {i['skill']:+.4f} | {v['skill']:+.4f} |",
              f"| skill as a multiple of the free EWMA rule's | {i['vs_ewma']['model_skill_over_ewma_skill']:.2f}× | {v['vs_ewma']['model_skill_over_ewma_skill']:.2f}× |",
              f"| Spearman ρ(p, move size) | {i['rho']:+.3f} | {v['rho']:+.3f} |",
              f"| ECE | {i['ece']:.3f} | {v['ece']:.3f} |",
              f"| buckets n ≥ 100 within 0.05 (E013) | {'yes' if i['e013_buckets_ok'] else 'no'} | {'yes' if v['e013_buckets_ok'] else 'no'} |",
              f"| calibration intercept / slope | {i['calibration_line']['intercept']:+.3f} / {i['calibration_line']['slope']:.3f} | "
              f"{v['calibration_line']['intercept']:+.3f} / {v['calibration_line']['slope']:.3f} |",
              f"| accuracy at 0.5 (naive {i['naive_accuracy']:.3f}) | {i['accuracy_at_0_5']:.3f} | {v['accuracy_at_0_5']:.3f} |",
              f"| worst block offset | {i['worst_block_offset']:.3f} | {v['worst_block_offset']:.3f} |", "",
              f"Brier(incumbent) − Brier(variant): {pdf['diff']:+.5f} [{pdf['ci_low']:+.5f}, {pdf['ci_high']:+.5f}] (positive = variant better)", "",
              "| block (UTC) | incumbent stated − observed | variant stated − observed |", "|---|---|---|"]
        for name in BLOCK_NAMES:
            a, b = i["blocks"][name], v["blocks"][name]
            L.append(f"| {name} | {a['stated_minus_observed']:+.3f} [{a['ci95'][0]:+.3f}, {a['ci95'][1]:+.3f}] | "
                     f"{b['stated_minus_observed']:+.3f} [{b['ci95'][0]:+.3f}, {b['ci95'][1]:+.3f}] |")
        L += ["", "Descriptive (never used to choose anything): per year, skill and worst block offset, incumbent → variant: "
              + "; ".join(f"{yr} {i['by_year'][yr]['skill']:+.3f}→{v['by_year'][yr]['skill']:+.3f}, "
                          f"{i['by_year'][yr]['worst_block_offset']:.3f}→{v['by_year'][yr]['worst_block_offset']:.3f}" for yr in i["by_year"]),
              "", "Descriptive: stated − observed per frozen volatility tercile, incumbent → variant: "
              + "; ".join(f"{g} {i['regimes'][g]['stated_minus_observed']:+.3f}→{v['regimes'][g]['stated_minus_observed']:+.3f}"
                          for g in REGIMES if i["regimes"][g].get("rows")), ""]
    L += ["## Pre-registered hypotheses", ""] + [f"- {k}: **{'HOLDS' if ok else 'FAILS'}**" for k, ok in r["verdict"].items()]
    L += ["", "*Research-only and hypothesis-generating: the validation period is worn, and E027 found these offsets on "
          "these rows. Whatever the verdict, move_size_1h_v1, the live system and the checkpoints are unchanged.*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E031")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
