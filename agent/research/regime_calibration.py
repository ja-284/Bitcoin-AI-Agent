"""
E026 -- is the move-size model family calibrated within volatility regimes? (descriptive, pre-registered)

    python -m agent.research.regime_calibration --experiment E026

Triggered by the 2026-09-26 drift flag (a calmer live market than development). Uses the walk-forward
out-of-sample predictions of the E013/E018 setup on DEVELOPMENT data only, split by the FROZEN rv_168
terciles the 5,000-hour checkpoint will use. It fits nothing for use, selects nothing and recalibrates
nothing: it is a reference for reading future live readings. Hypothesis and consequences were committed
before this module existed (research/experiments/E026_regime_calibration.json).
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.research.metrics import block_bootstrap_estimates, reliability_table
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

REGIMES = ("low", "mid", "high")
TOLERANCE = 0.02            # the pre-registered |mean stated - observed| bound
BLOCK, N_BOOT, SEED = 48, 500, 26


def assign(rv168_raw: np.ndarray, cuts: tuple[float, float]) -> np.ndarray:
    """0 / 1 / 2 = low / mid / high, the same rule as live_checkpoint.regime_of (low < cut1 <= mid < cut2 <= high)."""
    return np.where(rv168_raw < cuts[0], 0, np.where(rv168_raw < cuts[1], 1, 2))


def regime_table(p: np.ndarray, y: np.ndarray, regime: np.ndarray) -> dict:
    """Per volatility regime (E026)."""
    return group_table(p, y, regime, REGIMES)


def group_table(p: np.ndarray, y: np.ndarray, group: np.ndarray, names: tuple[str, ...]) -> dict:
    """Per group (codes 0..len(names)-1): rows, mean stated p, observed share, their difference with a
    block-bootstrap interval, ECE. Rows must be in time order: the bootstrap resamples blocks of the whole
    series and recomputes each group inside every resample, so the hour-to-hour dependence is respected.
    Shared by E026 (volatility regimes) and E027 (weekday/weekend, hour blocks)."""
    regime = group
    stacked = np.column_stack([p, y, regime.astype(float)])
    out = {}
    for k, name in enumerate(names):
        mask = regime == k
        n = int(mask.sum())
        if n == 0:
            out[name] = {"rows": 0}
            continue

        def diff(a, k=k):
            m = a[:, 2] == k
            return float(a[m, 0].mean() - a[m, 1].mean()) if m.any() else np.nan

        point, est = block_bootstrap_estimates(stacked, diff, block=BLOCK, n_boot=N_BOOT, seed=SEED + k)
        est = est[~np.isnan(est)]
        lo, hi = (float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))) if len(est) else (np.nan, np.nan)
        out[name] = {"rows": n, "mean_stated": float(p[mask].mean()), "observed": float(y[mask].mean()),
                     "stated_minus_observed": point, "ci95": [lo, hi], "ece": reliability_table(p[mask], y[mask])[1],
                     "H_holds": bool(abs(point) <= TOLERANCE and lo <= 0 <= hi)}
    return out


def run(experiment: str) -> Path:
    from agent.research.feature_count import FULL, evaluate, prepare
    from agent.research.live_checkpoint import TERCILES_PATH

    cuts = tuple(json.loads(TERCILES_PATH.read_text(encoding="utf-8"))["tercile_cut_points"])
    df, spec, folds = prepare()
    oos = evaluate(df, spec, folds, FULL, {})["predictions"].sort_index()
    rv_raw = np.exp(df.loc[oos.index, "rv_168"].to_numpy(float))  # prepare() stores log(rv_168)
    regime = assign(rv_raw, cuts)
    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "cuts": list(cuts), "rows": int(len(oos)), "by_period": {}}
    for period in ("exploration", "validation"):
        m = (oos["period"] == period).to_numpy()
        res["by_period"][period] = {"rows": int(m.sum()),
                                    "regime_share": {r: float(np.mean(regime[m] == k)) for k, r in enumerate(REGIMES)},
                                    "table": regime_table(oos["p"].to_numpy(float)[m], oos["y"].to_numpy(float)[m], regime[m])}
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "regime_calibration.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "regime_calibration.md").write_text(render(res), encoding="utf-8")
    return out_dir / "regime_calibration.md"


def render(r: dict) -> str:
    L = ["# E026 — calibration of the move-size model family within volatility regimes (descriptive)", "",
         f"Generated {r['generated_at'][:16]} UTC · walk-forward out-of-sample predictions, {r['rows']:,} development hours · "
         f"frozen rv_168 cut points {r['cuts'][0]:.6f} / {r['cuts'][1]:.6f}", "",
         f"Hypothesis (pre-registered): in every regime |mean stated − observed| ≤ {TOLERANCE} and the 95% interval contains 0.", ""]
    for period, d in r["by_period"].items():
        L += [f"## {period} ({d['rows']:,} hours)", "",
              "| regime | share of hours | rows | mean stated | observed | stated − observed [95%] | ECE | H holds |",
              "|---|---|---|---|---|---|---|---|"]
        for name in REGIMES:
            t = d["table"][name]
            if not t.get("rows"):
                L.append(f"| {name} | 0% | 0 | | | | | |")
                continue
            L.append(f"| {name} | {100 * d['regime_share'][name]:.0f}% | {t['rows']:,} | {t['mean_stated']:.3f} | {t['observed']:.3f} | "
                     f"{t['stated_minus_observed']:+.3f} [{t['ci95'][0]:+.3f}, {t['ci95'][1]:+.3f}] | {t['ece']:.3f} | "
                     f"{'yes' if t['H_holds'] else 'NO'} |")
        L.append("")
    L += ["*Descriptive. Nothing about the frozen model, its calibration, the live signal or any checkpoint rule changes "
          "because of these numbers (pre-registered).*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E026")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
