"""
The pre-registered live checkpoints of the move-size model (research/LIVE_EVALUATION.md), computed
exactly as registered. Prepared 2026-09-23, while no checkpoint was reachable (42 of 500 hours).

    python -m agent.research.live_checkpoint                   # which checkpoint is due; computes it once reached
    python -m agent.research.live_checkpoint --freeze-regimes  # done once (2026-09-23): development terciles

Two clarifications, registered now -- before any checkpoint data exists, so neither can be chosen after
seeing an answer (both also recorded in research/LIVE_EVALUATION.md):

  1. A checkpoint at N hours reads EXACTLY the first N prospective graded hours, in time order -- not
     however many happen to exist on the day someone runs it. Reading "whenever it looks good" is
     optional stopping; a fixed prefix makes the checkpoint reproducible and un-pickable. Hours after
     the N-th belong to the next checkpoint.
  2. Intervals are a 48-hour circular block bootstrap with 500 resamples, as rule 3 says. (The weekly
     report uses 2,000 for steadier endpoints; the checkpoint keeps the registered number.)

The pass rules are imported from E024 (agent/research/checkpoint_power.py), so the checkpoint and the
study of its own error rates cannot drift apart. It reads the live shadow table only, and, for the
volatility-regime split at 5,000 hours, cut points frozen in advance from development data. It never
touches the sealed holdout.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from agent.research.checkpoint_power import E012_SKILL_BAR, e013_passes
from agent.research.diagnose import spearman
from agent.research.metrics import block_bootstrap, brier_score, reliability_table, wilson_interval

logger = logging.getLogger(__name__)

CHECKPOINTS = (500, 2000, 5000)
BLOCK_HOURS, N_BOOT, SEED = 48, 500, 17           # rule 3
E012_ACCURACY_MARGIN, E012_RHO_BAR = 0.05, 0.10   # rule 4, copied from E012
OUT_DIR = Path("research") / "monitoring"
TERCILES_PATH = OUT_DIR / "regime_terciles_v1.json"
HOUR_BLOCKS = ((0, 6), (6, 12), (12, 18), (18, 24))

# research/LIVE_EVALUATION.md, rule 5 and the E024 table: what each checkpoint may conclude, and how often
# the rules fail by chance at that size. Printed with every checkpoint so its result is read for what it is.
REGISTERED = {
    500: {"verdict": None, "what": "first look: skill and calibration points with intervals; NO verdict",
          "chance": "a model as good as on validation passes E012's Brier part 78%, accuracy 59%, rho 100% of the time "
                    "at this size; ECE stays under 0.03 only ~10% of the time -- a high ECE here is not evidence"},
    2000: {"verdict": "E012", "what": "verdict on E012; calibration by bucket with intervals; weekday/weekend and "
                                      "hour-of-day blocks (descriptive)",
           "chance": "a model as good as on validation passes every E012 part in ~98% of 2,000-hour stretches: a fail means something"},
    5000: {"verdict": "E013", "what": "verdict on E013; by month; by volatility regime of the previous 168h "
                                      "(terciles frozen on development data)",
           "chance": "the ECE part is sound; the bucket part fails a perfectly calibrated forecaster 8% of the time and the real "
                     "model in 27% of stretches -- a bucket fail is worse than a one-in-four event, not proof"},
}


def prospective(r: dict) -> bool:
    """Rule 1: the probability was stored before the outcome candle closed."""
    fetched = r.get("fetched_at")
    return fetched is not None and fetched < r["as_of"] + timedelta(hours=int(r.get("horizon_hours") or 1) + 1)


def prospective_graded(rows: list[dict]) -> list[dict]:
    """The rows a checkpoint may count, in time order."""
    ok = [r for r in rows if r.get("status") == "ok" and r.get("outcome_status") == "ok" and prospective(r)]
    return sorted(ok, key=lambda r: r["as_of"])


def due_checkpoint(n_graded: int) -> int | None:
    reached = [c for c in CHECKPOINTS if n_graded >= c]
    return max(reached) if reached else None


def core(p: np.ndarray, y: np.ndarray, size: np.ndarray) -> dict:
    """Skill, ranking and calibration on one set of hours, with the registered intervals where affordable."""
    n = len(p)
    base = float(y.mean())
    b_base = brier_score(np.full(n, base), y)
    gain = 1 - brier_score(p, y) / b_base if b_base > 0 else float("nan")
    acc = float(np.mean((p > 0.5) == (y > 0.5)))
    naive = max(base, 1 - base)
    buckets, ece, _ = reliability_table(p, y)
    ece_ok, buckets_ok, _ = e013_passes(p, y)
    d = {"n": n, "large_move_share": base, "mean_stated_p": float(p.mean()), "brier_rel_gain": gain,
         "accuracy": acc, "accuracy_ci95": list(wilson_interval(int(round(acc * n)), n)), "naive_rate": naive,
         "rho": spearman(p, size), "ece": ece, "e013_ece_ok": ece_ok, "e013_buckets_ok": buckets_ok,
         "buckets": [{"from": b.lower, "to": b.upper, "n": b.n, "stated": b.mean_predicted, "observed": b.observed,
                      "ci95": [b.ci_low, b.ci_high], "counts_for_e013": b.n >= 100,
                      "within_0_05": abs(b.observed - b.mean_predicted) <= 0.05} for b in buckets]}
    if n >= 4 * BLOCK_HOURS:
        stacked = np.column_stack([p, y, size])

        def g(a):
            bb = brier_score(np.full(len(a), a[:, 1].mean()), a[:, 1])
            return 1 - brier_score(a[:, 0], a[:, 1]) / bb if bb > 0 else float("nan")

        for name, fn in (("brier_rel_gain", g), ("rho", lambda a: spearman(a[:, 0], a[:, 2])),
                         ("ece", lambda a: reliability_table(a[:, 0], a[:, 1])[1])):
            _, lo, hi = block_bootstrap(stacked, fn, block=BLOCK_HOURS, n_boot=N_BOOT, seed=SEED)
            d[f"{name}_ci95"] = [lo, hi]
    return d


def e012_verdict(s: dict) -> dict:
    """E012 exactly as registered: all three parts, the rho part including its interval."""
    parts = {"brier_5pct_below_base": s["brier_rel_gain"] >= E012_SKILL_BAR,
             "accuracy_naive_plus_5": s["accuracy"] >= s["naive_rate"] + E012_ACCURACY_MARGIN,
             "rho_ge_0_10_interval_above_0": s["rho"] >= E012_RHO_BAR and "rho_ci95" in s and s["rho_ci95"][0] > 0}
    return {"parts": parts, "pass": all(parts.values())}


def e013_verdict(s: dict) -> dict:
    parts = {"ece_le_0_03": s["e013_ece_ok"], "buckets_100plus_within_0_05": s["e013_buckets_ok"]}
    return {"parts": parts, "pass": all(parts.values())}


def _slice(rows, p, y, size, key) -> dict:
    groups: dict = {}
    for i, r in enumerate(rows):
        groups.setdefault(key(r), []).append(i)
    out = {}
    for name, idx in sorted(groups.items()):
        idx = np.array(idx)
        yy = y[idx]
        bb = brier_score(np.full(len(idx), yy.mean()), yy)
        out[str(name)] = {"n": int(len(idx)), "large_move_share": float(yy.mean()), "mean_stated_p": float(p[idx].mean()),
                          "brier_rel_gain": (1 - brier_score(p[idx], yy) / bb) if bb > 0 else None,
                          "ece": reliability_table(p[idx], yy)[1]}
    return out


def regime_of(r: dict, cuts: tuple[float, float]) -> str:
    rv = (r.get("features") or {}).get("rv_168")
    if rv is None:
        return "unknown"
    return "low" if rv < cuts[0] else "mid" if rv < cuts[1] else "high"


def evaluate(rows: list[dict], checkpoint: int, terciles: tuple[float, float] | None = None,
             ewma_brier: dict | None = None) -> dict:
    """The checkpoint on EXACTLY the first `checkpoint` prospective graded rows (clarification 1)."""
    graded = prospective_graded(rows)
    if len(graded) < checkpoint:
        raise ValueError(f"checkpoint {checkpoint} not reached: {len(graded)} prospective graded hours")
    first = graded[:checkpoint]
    p = np.array([r["p_calibrated"] for r in first], float)
    y = np.array([1.0 if r["outcome_large"] else 0.0 for r in first])
    size = np.abs(np.array([r["outcome_return"] for r in first], float))
    reg = REGISTERED[checkpoint]
    out = {"checkpoint_hours": checkpoint, "first_hour": first[0]["as_of"].isoformat(),
           "last_hour": first[-1]["as_of"].isoformat(), "prospective_graded_available": len(graded),
           "registered": reg, "intervals": f"{BLOCK_HOURS}h circular block bootstrap, {N_BOOT} resamples, seed {SEED}",
           "stats": core(p, y, size), "verdicts": {}}
    if checkpoint >= 2000:
        out["verdicts"]["E012"] = e012_verdict(out["stats"])
        out["slices"] = {"weekday_weekend": _slice(first, p, y, size, lambda r: "weekend" if r["as_of"].weekday() >= 5 else "weekday"),
                         "hour_block_utc": _slice(first, p, y, size, lambda r: next(f"{a:02d}-{b:02d}" for a, b in HOUR_BLOCKS
                                                                                    if a <= r["as_of"].hour < b))}
    if checkpoint >= 5000:
        out["verdicts"]["E013"] = e013_verdict(out["stats"])
        out["slices"]["month"] = _slice(first, p, y, size, lambda r: r["as_of"].strftime("%Y-%m"))
        if terciles is None:
            raise ValueError("the 5,000-hour checkpoint needs the frozen development terciles (--freeze-regimes)")
        out["slices"]["volatility_regime_168h"] = _slice(first, p, y, size, lambda r: regime_of(r, terciles))
    if ewma_brier is not None:
        out["vs_free_ewma_rule"] = ewma_brier
    return out


def freeze_regime_terciles(path: Path = TERCILES_PATH) -> dict:
    """
    Rule 5 wants the 5,000-hour regime split "defined on the development period, not on live data".
    Done once, now, before any live checkpoint exists. The development frame is built by the same
    code as the model's inputs (loaded through load_bars' default, which stops at the holdout), and
    it must first REPRODUCE the frozen reference file's rv_168 quartiles -- proof it is the same
    definition -- before its terciles are written.
    """
    from agent.research.drift import load_reference
    from agent.research.holdout_eval import E012_FEATURES, E012_THRESHOLD_1H
    from agent.research.model_test import build_frame

    if path.exists():
        raise FileExistsError(f"{path} is frozen; it must never be recomputed")
    ref = load_reference()
    df, _ = build_frame(1, [], E012_FEATURES, "large_move", E012_THRESHOLD_1H)
    rv = df["rv_168"].dropna()
    rv = rv[rv.index <= "2025-06-30 23:00:00+00:00"]
    q = ref["quantiles"]
    got = [float(np.quantile(rv, x)) for x in q]
    want = ref["features"]["rv_168"]["q"]
    if not np.allclose(got, want, rtol=1e-9, atol=0):
        raise RuntimeError(f"rv_168 does not reproduce the reference quantiles: {got} vs {want} -- not the same definition")
    cuts = [float(np.quantile(rv, 1 / 3)), float(np.quantile(rv, 2 / 3))]
    doc = {"what": "volatility regime cut points for the 5,000-hour checkpoint (research/LIVE_EVALUATION.md rule 5)",
           "feature": "rv_168 (raw, before log): realised volatility of the previous 168 hours",
           "built_from": f"development period, {rv.index.min().isoformat()} -> {rv.index.max().isoformat()}, n = {len(rv)}",
           "reproduces_reference_quantiles": True, "tercile_cut_points": cuts,
           "frozen_at": datetime.now(timezone.utc).isoformat(),
           "rule": "low < cut 1 <= mid < cut 2 <= high; never recomputed, never fitted to live data"}
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def render(e: dict) -> str:
    s, reg = e["stats"], e["registered"]
    ci = lambda k: (" [%+.3f, %+.3f]" % tuple(s[k + "_ci95"])) if k + "_ci95" in s else ""  # noqa: E731
    L = [f"# Live checkpoint — {e['checkpoint_hours']} prospective hours", "",
         f"Hours {e['first_hour'][:16]} → {e['last_hour'][:16]} UTC — exactly the first {e['checkpoint_hours']} "
         f"prospective graded hours ({e['prospective_graded_available']} available). Intervals: {e['intervals']}.", "",
         f"**What this checkpoint may conclude (registered 2026-09-21):** {reg['what']}.", "",
         f"**How often these rules fail by chance at this size (E024):** {reg['chance']}.", "",
         "| measure | value | registered bar |", "|---|---|---|",
         f"| Brier gain vs the base rate of these hours | {s['brier_rel_gain']:+.3f}{ci('brier_rel_gain')} | ≥ +0.050 (E012) |",
         f"| accuracy (large vs small) | {s['accuracy']:.3f} [{s['accuracy_ci95'][0]:.3f}, {s['accuracy_ci95'][1]:.3f}] | ≥ naive {s['naive_rate']:.3f} + 0.05 (E012) |",
         f"| Spearman ρ(p, move size) | {s['rho']:+.3f}{ci('rho')} | ≥ 0.10, interval above 0 (E012) |",
         f"| ECE | {s['ece']:.3f}{ci('ece')} | ≤ 0.03 (E013) |", "",
         "| stated | observed | 95% interval | n | counts for E013 (n ≥ 100) | within 0.05 |", "|---|---|---|---|---|---|"]
    for b in s["buckets"]:
        L.append(f"| {b['stated']:.2f} | {b['observed']:.2f} | [{b['ci95'][0]:.2f}, {b['ci95'][1]:.2f}] | {b['n']} | "
                 f"{'yes' if b['counts_for_e013'] else 'no'} | {'yes' if b['within_0_05'] else 'NO'} |")
    if not e["verdicts"]:
        L += ["", "**No verdict at this checkpoint — by registration.**"]
    for name, v in e["verdicts"].items():
        L += ["", f"**{name}: {'PASS' if v['pass'] else 'FAIL'}** — " + ", ".join(f"{k}: {'yes' if ok else 'no'}" for k, ok in v["parts"].items())]
    for title, sl in (e.get("slices") or {}).items():
        L += ["", f"### {title} (descriptive — never a basis for switching models)", "", "| group | n | large-move share | mean stated p | Brier gain | ECE |", "|---|---|---|---|---|---|"]
        for g, d in sl.items():
            gain = "n/a" if d["brier_rel_gain"] is None else f"{d['brier_rel_gain']:+.3f}"
            L.append(f"| {g} | {d['n']} | {d['large_move_share']:.3f} | {d['mean_stated_p']:.3f} | {gain} | {d['ece']:.3f} |")
    if "vs_free_ewma_rule" in e:
        L += ["", "### Against the free 24h-EWMA rule (E019, pre-committed)", "", "```", json.dumps(e["vs_free_ewma_rule"], indent=1, default=str), "```"]
    L += ["", "*Nothing about the model changes because of these numbers (rule 2). A failure demotes the deliverable in every "
          "report; it never touches the live signal (rule 6).*"]
    return "\n".join(L) + "\n"


def main() -> int:
    from agent.research.weekly_report import _against_ewma, ewma_reference_series, fetch_shadow_rows

    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze-regimes", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.freeze_regimes:
        print(json.dumps(freeze_regime_terciles(), indent=2))
        return 0
    rows = fetch_shadow_rows()
    graded = prospective_graded(rows)
    cp = due_checkpoint(len(graded))
    if cp is None:
        print(f"No checkpoint reached: {len(graded)} of {CHECKPOINTS[0]} prospective graded hours "
              f"(about {(CHECKPOINTS[0] - len(graded)) / 24:.0f} more days at one hour per hour).")
        return 0
    stem = OUT_DIR / f"checkpoint_{cp}h"
    if stem.with_suffix(".md").exists():
        print(f"Checkpoint {cp} already computed: {stem.with_suffix('.md')} (it reads a fixed prefix; re-running changes nothing)")
        return 0
    terciles = tuple(json.loads(TERCILES_PATH.read_text(encoding="utf-8"))["tercile_cut_points"]) if TERCILES_PATH.exists() else None
    first = graded[:cp]
    now = datetime.now(timezone.utc)
    p = np.array([r["p_calibrated"] for r in first], float)
    y = np.array([1.0 if r["outcome_large"] else 0.0 for r in first])
    size = np.abs(np.array([r["outcome_return"] for r in first], float))
    lookback = int((now - first[0]["as_of"]).total_seconds() // 3600) + 800  # back to the first hour, plus warm-up
    vs = _against_ewma(first, p, y, size, ewma_reference_series(now, lookback_hours=lookback))
    e = evaluate(rows, cp, terciles, vs)
    stem.with_suffix(".json").write_text(json.dumps(e, indent=2, default=str), encoding="utf-8")
    stem.with_suffix(".md").write_text(render(e), encoding="utf-8")
    print(stem.with_suffix(".md"))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
