"""
The safe-signal-research batch: E036 (MS-A, move-size) and E037 (D1, D2, direction), registered in
research/experiments/E036_ms_a_liquidity_pair.json and E037_direction_d1_d2.json before this code existed.

    python -m agent.research.signal_batch reproduce     # Phase 3: the registered references must reproduce first

PHASE 3 (all this file does so far). Before any candidate is fitted, the references both records name must reproduce
their recorded figures to 1e-9 through the corrected, governed data path (agent/research/snapshots.py: registered
files only, cut at the holdout, never downloaded):
  * move-size: E018's full model (= E019's incumbent = E013's Platt variant), through feature_count.prepare/evaluate,
    the functions E018 and E019 used; and E019's free 24 h EWMA rule, scored exactly as E019 scored it;
  * direction: E032, by running agent/research/direction_probability.run itself (its code unchanged) into
    research/results/E037/reproduction_E032/, then comparing every number of its result with E032's.
The expected figures are read from the committed result files, never retyped. Nothing here fits, scores or even names
a candidate input: the MS-A, D1 and D2 code is added in Phase 4, and only if this gate passes.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

TOLERANCE = 1e-9  # both records: same machine, code and bytes, so the figures must agree to the last digits
RESULTS = Path("research") / "results"
E018_RESULT = RESULTS / "E018" / "feature_count.json"
E019_RESULT = RESULTS / "E019" / "simple_baselines.json"
E032_RESULT = RESULTS / "E032" / "direction_probability.json"
NOT_COMPARED = {"experiment", "generated_at"}  # labels of a run, not results


def compare(expected, got, path: str = "") -> list[str]:
    """Every difference between two result trees: floats beyond TOLERANCE, any other value unequal, keys missing on
    either side. Pure, so tests can prove it catches what it must."""
    if isinstance(expected, dict) and isinstance(got, dict):
        out = []
        for k in sorted(set(expected) | set(got)):
            if k in NOT_COMPARED:
                continue
            if k not in got or k not in expected:
                out.append(f"{path}.{k}: present only in the {'expected' if k in expected else 'reproduced'} result")
                continue
            out += compare(expected[k], got[k], f"{path}.{k}")
        return out
    if isinstance(expected, list) and isinstance(got, list):
        if len(expected) != len(got):
            return [f"{path}: {len(expected)} items expected, {len(got)} reproduced"]
        return [d for i, (a, b) in enumerate(zip(expected, got)) for d in compare(a, b, f"{path}[{i}]")]
    if isinstance(expected, bool) or isinstance(got, bool) or not isinstance(expected, (int, float)) or not isinstance(got, (int, float)):
        return [] if expected == got else [f"{path}: expected {expected!r}, reproduced {got!r}"]
    if isinstance(expected, int) and isinstance(got, int):
        return [] if expected == got else [f"{path}: expected {expected}, reproduced {got}"]
    a, b = float(expected), float(got)
    if np.isnan(a) and np.isnan(b):
        return []
    return [] if abs(a - b) <= TOLERANCE else [f"{path}: expected {a!r}, reproduced {b!r} (difference {b - a:+.3e})"]


def _jsonable(o):
    return json.loads(json.dumps(o, default=str))


def reproduce_move_size() -> dict:
    """E018's full model and E019's EWMA rule, with E018/E019's own functions, on E013's rows."""
    from agent.research.feature_count import FULL, evaluate, prepare
    from agent.research.history import load_bars
    from agent.research.periods import HOLDOUT
    from agent.research.simple_baselines import paired_difference, score, simple_rules

    e018 = json.loads(E018_RESULT.read_text(encoding="utf-8"))
    e019 = json.loads(E019_RESULT.read_text(encoding="utf-8"))
    df, spec, folds = prepare()
    full = evaluate(df, spec, folds, FULL, {})
    oos = full["predictions"]
    bars, _, snapshot = load_bars(end=HOLDOUT.start)
    ewma = simple_rules(bars)["E_ewma_halflife_24h"].reindex(oos.index)

    got_full = {"n_features": full["n_features"], "exploration": full["exploration"], "validation": full["validation"]}
    got_ewma = {}
    for period in ("exploration", "validation"):
        mask = (oos["period"] == period).to_numpy()
        p, y = ewma.to_numpy(float)[mask], oos["y"].to_numpy(float)[mask]
        size = np.abs(oos["fwd_1h"].to_numpy(float))[mask]
        ok = ~np.isnan(p)
        got_ewma[period] = {**score(p[ok], y[ok], size[ok]), "rows_scored": int(ok.sum()), "rows_unavailable": int((~ok).sum())}
    mask = (oos["period"] == "validation").to_numpy()
    p_ewma, p_ref, y = ewma.to_numpy(float)[mask], oos["p"].to_numpy(float)[mask], oos["y"].to_numpy(float)[mask]
    ok = ~np.isnan(p_ewma)
    got = _jsonable({
        "folds": len(folds), "rows_common": int(len(df)), "oos_rows": int(len(oos)), "snapshot": snapshot.name,
        "E018_full": got_full, "E019_ewma": got_ewma,
        "E019_ewma_minus_incumbent_validation": paired_difference(p_ewma[ok], p_ref[ok], y[ok]),
    })
    expected = {"folds": e018["folds"], "rows_common": e018["rows_common"], "oos_rows": e019["oos_rows"], "snapshot": e018["snapshot"],
                "E018_full": e018["ablation"]["full"], "E019_ewma": e019["by_candidate"]["E_ewma_halflife_24h"],
                "E019_ewma_minus_incumbent_validation": e019["verdict"]["paired_brier_difference"]}
    # E019's incumbent IS E018's full model; the copy in E019 must agree as well (one more independent check)
    incumbent = {p: e019["by_candidate"]["G_incumbent"][p] for p in ("exploration", "validation")}
    differences = compare(expected, got) + compare(
        {p: {k: v for k, v in incumbent[p].items() if k in got_full[p]} for p in incumbent},
        {p: _jsonable(got_full[p]) for p in incumbent}, "E019_incumbent")
    return {"track": "move-size (E036's gate)", "reproduces": not differences, "differences": differences,
            "expected": expected, "reproduced": got}


def reproduce_direction() -> dict:
    """E032 by its own unchanged code, written next to E037's results, then compared number by number."""
    from agent.research.direction_probability import run

    md = run("E037/reproduction_E032")
    got = json.loads((md.parent / "direction_probability.json").read_text(encoding="utf-8"))
    expected = json.loads(E032_RESULT.read_text(encoding="utf-8"))
    differences = compare(expected, got)
    return {"track": "direction (E037's gate)", "reproduces": not differences, "differences": differences,
            "reproduction_files": md.parent.as_posix()}


def render(r: dict) -> str:
    L = [f"# {r['experiment']}: Phase 3 reference reproduction", "",
         f"Generated {r['generated_at'][:16]} UTC. Tolerance {TOLERANCE:g} absolute on every float, exact on every count "
         "and label. Expected figures are read from the committed result files.", "",
         f"**{'REPRODUCES' if r['reproduces'] else 'DOES NOT REPRODUCE: the track stops here'}** ({r['track']})", ""]
    if r["differences"]:
        L += ["Differences:", ""] + [f"- `{d}`" for d in r["differences"]]
    if "reproduced" in r:
        g = r["reproduced"]
        v, e = g["E018_full"]["validation"], g["E018_full"]["exploration"]
        L += ["| figure | reproduced |", "|---|---|",
              f"| folds · frame rows · out-of-sample rows | {g['folds']} · {g['rows_common']:,} · {g['oos_rows']:,} |",
              f"| reference validation Brier · skill · ECE · rho | {v['brier']!r} · {v['skill']!r} · {v['ece']!r} · {v['rho_p_vs_abs_return']!r} |",
              f"| reference exploration Brier · skill | {e['brier']!r} · {e['skill']!r} |",
              f"| EWMA rule validation Brier · skill | {g['E019_ewma']['validation']['brier']!r} · {g['E019_ewma']['validation']['skill']!r} |",
              f"| EWMA minus reference, validation (paired, 2,000 resamples) | {g['E019_ewma_minus_incumbent_validation']['diff']!r} "
              f"[{g['E019_ewma_minus_incumbent_validation']['ci_low']!r}, {g['E019_ewma_minus_incumbent_validation']['ci_high']!r}] |"]
    else:
        L += [f"E032's own code was re-run into `{r['reproduction_files']}/`; every number of its result was compared with "
              "`research/results/E032/direction_probability.json`."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["reproduce"])
    parser.parse_args(argv)
    now = datetime.now(timezone.utc).isoformat()
    ok = True
    for experiment, fn in (("E036", reproduce_move_size), ("E037", reproduce_direction)):
        r = {"experiment": experiment, "generated_at": now, **fn()}
        out = RESULTS / experiment
        out.mkdir(parents=True, exist_ok=True)
        (out / "reproduction.json").write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
        (out / "reproduction.md").write_text(render(r), encoding="utf-8")
        print(f"{experiment}: {'REPRODUCES' if r['reproduces'] else 'DOES NOT REPRODUCE'} ({len(r['differences'])} differences)")
        ok = ok and r["reproduces"]
    return 0 if ok else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
