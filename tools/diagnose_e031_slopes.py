"""    python tools/diagnose_e031_slopes.py > research/results/E031/block_slopes_by_fold.json`n`nMaster plan 2B, development data only, descriptive: why did E031's block maps hurt the confident tail?
Per fold: the single Platt map's slope vs the four block maps' slopes, fitted exactly as E031 fitted them."""
import json

import numpy as np

import agent.research.block_calibration as bc
from agent.research.feature_count import FULL, C, prepare
from agent.research.model_test import LogisticModel, PlattCalibrator
from agent.research.slice_calibration import BLOCK_NAMES, block_group
from agent.research.walkforward import run_walk_forward

df, spec, folds = prepare()
recs = []


def mk():
    recs.append(bc.RecordingPlatt())
    return recs[-1]


run_walk_forward(df, list(FULL), "y", lambda: LogisticModel(C=C), spec, folds=folds, make_calibrator=mk)
slices = bc.expected_slices(df, list(FULL), "y", folds)
single_a, block_a, block_n, block_b = [], {k: [] for k in BLOCK_NAMES}, {k: [] for k in BLOCK_NAMES}, {k: [] for k in BLOCK_NAMES}
for rec, (ch, _) in zip(recs, slices):
    single_a.append(float(rec.platt.lr.coef_[0][0]))
    g = block_group(ch)
    for k, name in enumerate(BLOCK_NAMES):
        m = g == k
        c = PlattCalibrator()
        c.fit(rec.calib_p[m], rec.calib_y[m])
        block_a[name].append(float(c.lr.coef_[0][0]))
        block_b[name].append(float(c.lr.intercept_[0]))
        block_n[name].append(int(m.sum()))
sa = np.array(single_a)
out = {"folds": len(sa), "single_map_slope": {"mean": round(sa.mean(), 3), "sd_across_folds": round(sa.std(ddof=1), 3)},
       "block_map_slope": {k: {"mean": round(float(np.mean(v)), 3), "sd_across_folds": round(float(np.std(v, ddof=1)), 3),
                               "min": round(min(v), 3), "max": round(max(v), 3), "folds_above_single": int(sum(1 for a, s in zip(v, sa) if a > s)),
                               "mean_calib_rows": round(float(np.mean(block_n[k])))} for k, v in block_a.items()},
       "block_map_intercept": {k: round(float(np.mean(v)), 3) for k, v in block_b.items()}}
allb = np.concatenate([np.array(v) - sa for v in block_a.values()])
out["block_minus_single_slope"] = {"mean": round(float(allb.mean()), 3), "sd": round(float(allb.std(ddof=1)), 3),
                                   "share_steeper": round(float((allb > 0).mean()), 3)}
print(json.dumps(out, indent=1))
