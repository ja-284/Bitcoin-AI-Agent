"""
E028 (RESEARCH-ONLY, pre-registered): does a second calendar harmonic remove the intraday miscalibration
that E027 found? One variant fixed in advance (research/experiments/E028_second_harmonic.json).

    python -m agent.research.second_harmonic --experiment E028

The incumbent's nine inputs plus sin/cos(4*pi*h/24), everything else identical (frame, rows, folds, model,
Platt). Nothing here touches the live system or the frozen artefact move_size_1h_v1: the extra columns exist
only in this research frame.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from agent.research.metrics import brier_score, reliability_table
from agent.research.regime_calibration import group_table
from agent.research.simple_baselines import paired_difference
from agent.research.slice_calibration import BLOCK_NAMES, block_group
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)
SECOND_HARMONIC = ["hour_sin2", "hour_cos2"]


def add_second_harmonic(df):
    """The variant's two extra columns, from the reference hour of each row (UTC)."""
    out = df.copy()
    angle = 4 * np.pi * out.index.hour.to_numpy() / 24
    out["hour_sin2"], out["hour_cos2"] = np.sin(angle), np.cos(angle)
    return out


def skill(p, y):
    base = brier_score(np.full(len(y), y.mean()), y)
    return 1 - brier_score(p, y) / base


def worst_block_offset(table: dict) -> float:
    return max(abs(t["stated_minus_observed"]) for t in table.values())


def judge(inc_blocks: dict, var_blocks: dict, paired_validation: dict, var_ece: dict) -> dict:
    """The three pre-registered hypotheses, applied exactly as written. Pure."""
    h_a = all(worst_block_offset(var_blocks[p]) <= 0.5 * worst_block_offset(inc_blocks[p]) for p in inc_blocks)
    h_b = paired_validation["ci_high"] >= 0            # incumbent minus variant: not wholly below zero
    h_c = all(v <= 0.03 for v in var_ece.values())
    return {"H_a_mechanism": bool(h_a), "H_b_no_loss": bool(h_b), "H_c_calibration": bool(h_c)}


def run(experiment: str) -> Path:
    from agent.research.feature_count import FULL, evaluate, prepare

    df, spec, folds = prepare()
    df = add_second_harmonic(df)
    inc = evaluate(df, spec, folds, FULL, {})["predictions"].sort_index()
    var = evaluate(df, spec, folds, FULL + SECOND_HARMONIC, {})["predictions"].sort_index()
    assert inc.index.equals(var.index), "the two models must be scored on identical rows"
    res = {"experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
           "rows": int(len(inc)), "by_period": {}}
    inc_blocks, var_blocks, var_ece = {}, {}, {}
    for period in ("exploration", "validation"):
        m = (inc["period"] == period).to_numpy()
        y = inc["y"].to_numpy(float)[m]
        pi, pv = inc["p"].to_numpy(float)[m], var["p"].to_numpy(float)[m]
        groups = block_group(inc.index[m])
        inc_blocks[period] = group_table(pi, y, groups, BLOCK_NAMES)
        var_blocks[period] = group_table(pv, y, groups, BLOCK_NAMES)
        var_ece[period] = reliability_table(pv, y)[1]
        res["by_period"][period] = {
            "rows": int(m.sum()),
            "incumbent": {"skill": skill(pi, y), "ece": reliability_table(pi, y)[1], "blocks": inc_blocks[period],
                          "worst_block_offset": worst_block_offset(inc_blocks[period])},
            "variant": {"skill": skill(pv, y), "ece": var_ece[period], "blocks": var_blocks[period],
                        "worst_block_offset": worst_block_offset(var_blocks[period])},
            "incumbent_minus_variant_brier": paired_difference(pi, pv, y)}
    res["verdict"] = judge(inc_blocks, var_blocks, res["by_period"]["validation"]["incumbent_minus_variant_brier"], var_ece)
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "second_harmonic.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (out_dir / "second_harmonic.md").write_text(render(res), encoding="utf-8")
    return out_dir / "second_harmonic.md"


def render(r: dict) -> str:
    L = ["# E028 — does a second calendar harmonic remove the intraday miscalibration? (research-only)", "",
         f"Generated {r['generated_at'][:16]} UTC · {r['rows']:,} development hours, identical rows for both models · "
         "never adopted into move_size_1h_v1", ""]
    for period, d in r["by_period"].items():
        i, v, pd_ = d["incumbent"], d["variant"], d["incumbent_minus_variant_brier"]
        L += [f"## {period} ({d['rows']:,} hours)", "",
              f"Skill: incumbent {i['skill']:+.4f}, variant {v['skill']:+.4f} · ECE: {i['ece']:.3f} → {v['ece']:.3f} · "
              f"Brier(incumbent) − Brier(variant) {pd_['diff']:+.5f} [{pd_['ci_low']:+.5f}, {pd_['ci_high']:+.5f}] (positive = variant better)", "",
              "| block (UTC) | incumbent stated − observed | variant stated − observed |", "|---|---|---|"]
        for name in BLOCK_NAMES:
            a, b = i["blocks"][name], v["blocks"][name]
            L.append(f"| {name} | {a['stated_minus_observed']:+.3f} [{a['ci95'][0]:+.3f}, {a['ci95'][1]:+.3f}] | "
                     f"{b['stated_minus_observed']:+.3f} [{b['ci95'][0]:+.3f}, {b['ci95'][1]:+.3f}] |")
        L += ["", f"Worst block offset: {i['worst_block_offset']:.3f} → {v['worst_block_offset']:.3f}", ""]
    L += ["## Pre-registered hypotheses", ""] + [f"- {k}: **{'HOLDS' if ok else 'FAILS'}**" for k, ok in r["verdict"].items()]
    L += ["", "*Research-only and hypothesis-generating (the validation period is worn). Whatever the verdict, "
          "move_size_1h_v1 and the live system are unchanged.*"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="E028")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(run(args.experiment))
