"""
Compare two baseline evaluations produced by agent/research/evaluate.py under the SAME
pre-registered criterion -- written for E001 (scoring 0.1.0) against E017 (scoring 0.2.0).

    python -m agent.research.compare_baselines --old E001 --new E017

It re-applies E001's criterion to both result files rather than trusting either summary:
  (a) edge (mean return after BUY minus after SELL) positive with a bootstrap interval
      excluding zero in BOTH periods, AND
  (b) three-class balanced accuracy (fixed 0.5% band) above EVERY trivial baseline in both.
A horizon counts as "information present" only if both hold, and the verdicts are printed
side by side so a changed conclusion is impossible to miss or to soften.

Reads only committed result JSON -- no database, no network, no holdout.
"""

import argparse
import json
import sys
from pathlib import Path

HORIZONS = [1, 6, 24, 72, 168]


def load(experiment: str) -> dict:
    return json.loads((Path("research") / "results" / experiment / "results.json").read_text(encoding="utf-8"))


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.3f}"


def verdicts(res: dict) -> dict:
    """E001's criterion, applied to a results file. Returns {horizon: (part_a, part_b)}."""
    out = {}
    for h in HORIZONS:
        binary = res["by_spec"][f"binary_{h}h"]
        edges = [binary[p]["system"]["edge"] for p in ("exploration", "validation")]
        part_a = all(e["ci_low"] > 0 for e in edges)

        three = res["by_spec"][f"three_class_{h}h_fixed_0.005"]
        part_b = True
        for period in ("exploration", "validation"):
            block = three[period]
            system = block["system"]["classification"]["balanced_accuracy"]
            others = [v["classification"]["balanced_accuracy"] for k, v in block.items()
                      if isinstance(v, dict) and "classification" in v and k != "system"]
            part_b = part_b and bool(others) and system > max(others)
        out[h] = (part_a, part_b)
    return out


def main(old_name: str, new_name: str) -> None:
    old, new = load(old_name), load(new_name)
    print(f"{old_name}: scoring {old['scoring_version']}, pipeline {old['pipeline_version']}, {old['replay_hours']} hours")
    print(f"{new_name}: scoring {new['scoring_version']}, pipeline {new['pipeline_version']}, {new['replay_hours']} hours")
    print(f"signal mix {old_name}: {old['signal_mix']}")
    print(f"signal mix {new_name}: {new['signal_mix']}")

    print("\n=== criterion (a): edge after BUY minus after SELL, both periods, interval excluding zero ===")
    for h in HORIZONS:
        parts = []
        for res, name in ((old, old_name), (new, new_name)):
            for period in ("exploration", "validation"):
                e = res["by_spec"][f"binary_{h}h"][period]["system"]["edge"]
                parts.append(f"{name} {period[:4]} {_pct(e['point'])}% [{_pct(e['ci_low'])},{_pct(e['ci_high'])}]")
        print(f"  {h:>4}h  " + "  |  ".join(parts))

    print("\n=== criterion (b): three-class balanced accuracy vs the best trivial baseline ===")
    for h in HORIZONS:
        parts = []
        for res, name in ((old, old_name), (new, new_name)):
            for period in ("exploration", "validation"):
                block = res["by_spec"][f"three_class_{h}h_fixed_0.005"][period]
                system = block["system"]["classification"]["balanced_accuracy"]
                best = max(v["classification"]["balanced_accuracy"] for k, v in block.items()
                           if isinstance(v, dict) and "classification" in v and k != "system")
                parts.append(f"{name} {period[:4]} {system:.3f} vs {best:.3f}")
        print(f"  {h:>4}h  " + "  |  ".join(parts))

    print("\n=== verdict per horizon under the same criterion ===")
    vo, vn = verdicts(old), verdicts(new)
    changed = []
    for h in HORIZONS:
        passed_old, passed_new = all(vo[h]), all(vn[h])
        if passed_old != passed_new:
            changed.append(h)
        print(f"  {h:>4}h  {old_name}: {'INFORMATION PRESENT' if passed_old else 'no evidence'}"
              f"   ->   {new_name}: {'INFORMATION PRESENT' if passed_new else 'no evidence'}"
              f"{'   <-- CHANGED' if passed_old != passed_new else ''}")

    print("\n=== acted-direction accuracy, system vs the majority baseline ===")
    for h in HORIZONS:
        parts = []
        for res, name in ((old, old_name), (new, new_name)):
            for period in ("exploration", "validation"):
                b = res["by_spec"][f"binary_{h}h"][period]
                parts.append(f"{name} {period[:4]} {b['system'].get('acted_accuracy', float('nan')):.3f} "
                             f"(acted {b['system'].get('coverage', 0):.0%}) vs majority {b['majority'].get('acted_accuracy', float('nan')):.3f}")
        print(f"  {h:>4}h  " + "  |  ".join(parts))

    print("\n=== stated confidence vs realised hit rate ===")
    for res, name in ((old, old_name), (new, new_name)):
        for h in ("1h", "24h"):
            for period in ("exploration", "validation"):
                c = res["confidence"].get(h, {}).get(period, {})
                if c.get("acted_n"):
                    print(f"  {name} {h:>3} {period:<11} ECE {c['ece']:.3f}, hit rate {c['hit_rate']:.3f}, acted n={c['acted_n']}")

    print("\nCONCLUSION CHANGED AT:", changed if changed else "no horizon -- the two versions reach the same verdict everywhere")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", default="E001")
    parser.add_argument("--new", default="E017")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(args.old, args.new)
