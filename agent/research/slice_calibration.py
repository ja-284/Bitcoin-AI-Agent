"""
E027 -- calibration of the move-size model family by weekday/weekend and by six-hour block of the day
(descriptive, pre-registered: research/experiments/E027_slice_calibration.json).

    python -m agent.research.slice_calibration --experiment E027

A development reference for the two descriptive slices the registered 2,000-hour checkpoint reports, built
exactly as the checkpoint builds them (agent/research/live_checkpoint.py: weekend = Saturday/Sunday UTC,
blocks 00-06 / 06-12 / 12-18 / 18-24 UTC). Same walk-forward out-of-sample predictions and the same
calibration table as E026. Fits nothing for use, changes nothing.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.live_checkpoint import HOUR_BLOCKS
from agent.research.regime_calibration import TOLERANCE, group_table
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

DAY_NAMES = ("weekday", "weekend")
BLOCK_NAMES = tuple(f"{a:02d}-{b:02d}" for a, b in HOUR_BLOCKS)


def day_group(index: pd.DatetimeIndex) -> np.ndarray:
    return (index.weekday >= 5).astype(int)


def block_group(index: pd.DatetimeIndex) -> np.ndarray:
    return np.searchsorted([b for _, b in HOUR_BLOCKS], index.hour, side="right")


def run(experiment: str) -> Path:
    from agent.research.feature_count import FULL, evaluate, prepare

    df, spec, folds = prepare()
    oos = evaluate(df, spec, folds, FULL, {})["predictions"].sort_index()
    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "rows": int(len(oos)), "by_period": {}}
    for period in ("exploration", "validation"):
        sub = oos[oos["period"] == period]
        p, y = sub["p"].to_numpy(float), sub["y"].to_numpy(float)
        res["by_period"][period] = {"rows": int(len(sub)),
                                    "weekday_weekend": group_table(p, y, day_group(sub.index), DAY_NAMES),
                                    "hour_block_utc": group_table(p, y, block_group(sub.index), BLOCK_NAMES)}
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "slice_calibration.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "slice_calibration.md").write_text(render(res), encoding="utf-8")
    return out_dir / "slice_calibration.md"


def render(r: dict) -> str:
    L = ["# E027 — calibration by weekday/weekend and hour-of-day block (descriptive)", "",
         f"Generated {r['generated_at'][:16]} UTC · walk-forward out-of-sample predictions, {r['rows']:,} development hours · "
         "slices exactly as the 2,000-hour checkpoint defines them", "",
         f"Hypothesis (pre-registered): in every slice |mean stated − observed| ≤ {TOLERANCE} and the 95% interval contains 0.", ""]
    for period, d in r["by_period"].items():
        L += [f"## {period} ({d['rows']:,} hours)", "",
              "| slice | rows | mean stated | observed | stated − observed [95%] | ECE | H holds |", "|---|---|---|---|---|---|---|"]
        for key in ("weekday_weekend", "hour_block_utc"):
            for name, t in d[key].items():
                L.append(f"| {name} | {t['rows']:,} | {t['mean_stated']:.3f} | {t['observed']:.3f} | "
                         f"{t['stated_minus_observed']:+.3f} [{t['ci95'][0]:+.3f}, {t['ci95'][1]:+.3f}] | {t['ece']:.3f} | "
                         f"{'yes' if t['H_holds'] else 'NO'} |")
        L.append("")
    L += ["*Descriptive. Nothing about the frozen model, its calibration, the live signal or any checkpoint rule changes "
          "because of these numbers (pre-registered).*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E027")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
