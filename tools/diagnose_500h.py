"""    python tools/diagnose_500h.py > research/monitoring/diagnosis_500h_2026-10-15.json`n`nMaster plan 2A, descriptive and read-only: where does the 500-hour reading's calibration miss come from?
Exactly the registered first 500 prospective graded hours (live_checkpoint.prospective_graded), the project's own
statistics functions; nothing fitted for use, nothing selected, no rule changed. The 500 hours are also the first
quarter of the 2,000-hour reading's prefix: what is learned here may not be used to fit or choose anything that is
then judged on them."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from agent.database.db import get_connection
from agent.research.block_calibration import calibration_line
from agent.research.live_checkpoint import BLOCK_HOURS, N_BOOT, SEED, prospective_graded
from agent.research.metrics import block_bootstrap, reliability_table
from agent.research.regime_calibration import group_table
from agent.research.slice_calibration import BLOCK_NAMES, block_group

with get_connection() as c:
    c.read_only = True
    cur = c.cursor()
    cur.execute("SELECT * FROM shadow_move_size ORDER BY as_of")
    cols = [d.name for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
first = prospective_graded(rows)[:500]
cp = json.loads(Path("research/monitoring/checkpoint_500h.json").read_text(encoding="utf-8"))
assert first[0]["as_of"].isoformat() == cp["first_hour"] and first[-1]["as_of"].isoformat() == cp["last_hour"]
p = np.array([r["p_calibrated"] for r in first], float)
p_raw = np.array([r["p_raw"] for r in first], float)
y = np.array([1.0 if r["outcome_large"] else 0.0 for r in first])
idx = pd.DatetimeIndex([r["as_of"] for r in first])
out = {"hours": [cp["first_hour"], cp["last_hour"], len(first)]}

# 1. the overall level
pt, lo, hi = block_bootstrap(np.column_stack([p, y]), lambda a: float(a[:, 0].mean() - a[:, 1].mean()),
                             block=BLOCK_HOURS, n_boot=N_BOOT, seed=SEED)
out["overall_stated_minus_observed"] = [round(pt, 4), round(lo, 4), round(hi, 4)]
out["mean_stated_observed"] = [round(float(p.mean()), 4), round(float(y.mean()), 4)]
out["raw_vs_platt_mean"] = [round(float(p_raw.mean()), 4), round(float(p.mean()), 4)]

# 2. over- or under-confidence: the calibration line (slope < 1: too extreme; > 1: too timid)
line = calibration_line(p, y)
est = []
rng = np.random.default_rng(SEED)
n = len(p)
for _ in range(N_BOOT):
    starts = rng.integers(0, n, size=int(np.ceil(n / BLOCK_HOURS)))
    ix = ((starts[:, None] + np.arange(BLOCK_HOURS)[None, :]).ravel() % n)[:n]
    if len(np.unique(y[ix])) == 2:
        l2 = calibration_line(p[ix], y[ix])
        est.append((l2["intercept"], l2["slope"]))
est = np.array(est)
out["calibration_line"] = {"intercept": round(line["intercept"], 3), "slope": round(line["slope"], 3),
                           "slope_ci95": [round(float(np.percentile(est[:, 1], 2.5)), 3), round(float(np.percentile(est[:, 1], 97.5)), 3)],
                           "intercept_ci95": [round(float(np.percentile(est[:, 0], 2.5)), 3), round(float(np.percentile(est[:, 0], 97.5)), 3)]}

# 3. buckets (the checkpoint's own table), and the share of hours in each
buckets, ece, _ = reliability_table(p, y)
out["buckets"] = [{"range": [b.lower, round(b.upper, 1)], "n": b.n, "stated": round(b.mean_predicted, 3), "observed": round(b.observed, 3),
                   "gap": round(b.mean_predicted - b.observed, 3), "ci": [round(b.ci_low, 3), round(b.ci_high, 3)]} for b in buckets]
out["ece"] = round(ece, 4)
out["hours_stated_above_0_5"] = int((p > 0.5).sum())

# 4. by six-hour block (E027's blocks), against E027's development offsets (validation)
blocks = group_table(p, y, block_group(idx), BLOCK_NAMES)
e027_val = {"00-06": 0.022, "06-12": 0.007, "12-18": -0.057, "18-24": 0.013}
out["by_block"] = {k: {"n": v["rows"], "stated_minus_observed": round(v["stated_minus_observed"], 3),
                       "ci95": [round(v["ci95"][0], 3), round(v["ci95"][1], 3)], "e027_validation": e027_val[k]} for k, v in blocks.items()}

# 5. the regime (frozen terciles): all low?
from agent.research.live_checkpoint import TERCILES_PATH, regime_of

cuts = tuple(json.loads(TERCILES_PATH.read_text(encoding="utf-8"))["tercile_cut_points"])
out["regimes"] = dict(pd.Series([regime_of(r, cuts) for r in first]).value_counts())

# 6. week by week (descriptive): does the over-statement persist or wander?
wk = pd.Series(p - y, index=idx).groupby(idx.tz_convert(None).to_period("W")).agg(["mean", "size"])
out["weekly_stated_minus_observed"] = {str(k): [round(float(m), 3), int(s)] for k, (m, s) in wk.iterrows()}
print(json.dumps(out, indent=1, default=str))
