"""
The registered readings of the prospective direction shadow track (E034, research/DIRECTION_TRACK.md v1.1).

    python -m agent.research.direction_checkpoint            # the operational count; computes a reading only when due

Before a reading's size is reached it prints only operational figures (Amendment 1.1: the readings are blind) and
writes nothing. At 1,000 / 3,000 / 6,500 eligible hours it reads EXACTLY the first N eligible rows in time order,
writes research/monitoring/direction_checkpoint_<N>h.md/.json once, and never rewrites them. Only the 6,500-hour
reading applies the verdict rules of section 7; the earlier two give no verdict of any kind.

Read-only: one SELECT on a connection the server holds read-only. It fits nothing and changes nothing.
"""

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODEL_VERSION = "direction_1h_v1"
OUT_DIR = Path("research") / "monitoring"
BLOCK, N_BOOT, SEED = 48, 2000, 33                         # section 5
SESOI = 0.0005                                             # section 7: half of E032's development gains
GUARD_CITL, GUARD_ECE = 0.03, 0.03                         # section 7: the calibration guard
COSTS_ONE_WAY = {"standard": 0.0011, "discounted": 0.00085, "optimistic": 0.0002}  # section 9
BUCKET_WIDTH = 0.02                                        # section 5
OPTIMISTIC_BELOW = 3000                                    # E025 / E033: intervals liberal below this size
READINGS = {
    1000: {"verdict": False, "what": "first look: integrity, plus every registered measure as points with optimistic intervals; NO verdict of any kind"},
    3000: {"verdict": False, "what": "interim look: the same; NO verdict"},
    6500: {"verdict": True, "what": "the verdict: section 7's criteria (IMPROVEMENT / SKILL, BUT MISCALIBRATED / NO IMPROVEMENT / INSUFFICIENT EVIDENCE)"},
}
SQL = "SELECT * FROM shadow_direction ORDER BY as_of"
HOUR = timedelta(hours=1)


# ---------------------------------------------------------------- selection (section 2 and 5)
def is_prospective(r: dict) -> bool:
    """Stored before its outcome candle closed: fetched_at < as_of + 2h and created_at < as_of + 2h."""
    limit = r["as_of"] + (r["horizon_hours"] + 1) * HOUR
    return r["fetched_at"] < limit and r["created_at"] < limit


def eligible(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(eligible rows in time order, rows that fail the prospective rule)."""
    mine = [r for r in rows if r["model_version"] == MODEL_VERSION]
    late = [r for r in mine if not is_prospective(r)]
    ok = [r for r in mine if r["status"] == "ok" and r["outcome_status"] == "ok" and is_prospective(r)]
    return sorted(ok, key=lambda r: r["as_of"]), late


def operational(rows: list[dict], now: datetime) -> dict:
    """Amendment 1.1: the only figures shown before a reading. Counts, never an outcome-based figure."""
    mine = [r for r in rows if r["model_version"] == MODEL_VERSION]
    ok, late = eligible(rows)
    status = {}
    for r in mine:
        status[r["status"]] = status.get(r["status"], 0) + 1
    first = min((r["as_of"] for r in mine), default=None)
    expected = 0 if first is None else int((now.replace(minute=0, second=0, microsecond=0) - HOUR - first) / HOUR) + 1
    return {"rows": len(mine), "first_hour": None if first is None else first.isoformat(), "expected_hours_since_first": expected,
            "status_counts": status, "eligible_graded": len(ok), "not_prospective": len(late),
            "pending_outcome": sum(1 for r in mine if r["status"] == "ok" and r["outcome_status"] is None),
            "outcome_unavailable": sum(1 for r in mine if r["outcome_status"] == "unavailable"),
            "live_close_mismatches": sum(1 for r in mine if r["live_close_match"] is False),
            "live_scores_mismatches": sum(1 for r in mine if r["live_scores_match"] is False),
            "next_reading": next((n for n in READINGS if len(ok) < n), None)}


# ---------------------------------------------------------------- statistics (section 5)
def boot(values: np.ndarray, stat) -> tuple[float, float, float]:
    from agent.research.metrics import block_bootstrap_estimates

    point, est = block_bootstrap_estimates(values, stat, block=BLOCK, n_boot=N_BOOT, seed=SEED)
    est = est[np.isfinite(est)]
    if len(est) == 0:
        return point, float("nan"), float("nan")
    return point, float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))


def auc(p: np.ndarray, y: np.ndarray) -> float:
    """Area under the ROC curve (Mann-Whitney, ties shared); NaN if one class is absent."""
    from scipy.stats import rankdata

    pos, n_pos = y > 0.5, int((y > 0.5).sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = rankdata(p)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def ll_terms(p: np.ndarray, y: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    q = np.clip(p, eps, 1 - eps)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def interval(point_lo_hi) -> dict:
    point, lo, hi = point_lo_hi
    return {"point": point, "ci95": [lo, hi]}


def calibration(p: np.ndarray, y: np.ndarray) -> dict:
    from agent.research.block_calibration import calibration_line
    from agent.research.metrics import reliability_table

    lo_edge = math.floor(p.min() / BUCKET_WIDTH) * BUCKET_WIDTH
    hi_edge = math.ceil(p.max() / BUCKET_WIDTH) * BUCKET_WIDTH
    edges = [round(lo_edge + i * BUCKET_WIDTH, 10) for i in range(int(round((hi_edge - lo_edge) / BUCKET_WIDTH)) + 1)]
    if len(edges) < 2:
        edges = [lo_edge, lo_edge + BUCKET_WIDTH]
    edges[-1] += 1e-9  # the largest stated probability belongs to the last bucket
    buckets, ece, _ = reliability_table(p, y, edges)
    line = calibration_line(p, y)
    pairs = np.column_stack([p, y])

    def line_part(k):
        def f(a):
            if len(np.unique(a[:, 1])) < 2:
                return float("nan")
            return calibration_line(a[:, 0], a[:, 1])[k]
        return f

    return {"stated_minus_observed": interval(boot(pairs, lambda a: float(a[:, 0].mean() - a[:, 1].mean()))),
            "ece": ece,
            "buckets": [{"range": [b.lower, b.upper], "n": b.n, "stated": b.mean_predicted, "observed": b.observed,
                         "wilson95": [b.ci_low, b.ci_high]} for b in buckets],
            "calibration_intercept": interval((line["intercept"], *boot(pairs, line_part("intercept"))[1:])),
            "calibration_slope": interval((line["slope"], *boot(pairs, line_part("slope"))[1:]))}


def economics(p: np.ndarray, entry: np.ndarray, close: np.ndarray) -> dict:
    """Section 9: each traded hour is one round trip from price_at_prediction to the target close. Descriptive only."""
    have = np.isfinite(entry) & (entry > 0)
    r = np.where(have, close / np.where(have, entry, 1.0) - 1, np.nan)[have]
    q = p[have]
    out = {"hours_with_an_entry_price": int(have.sum()), "hours_without": int((~have).sum()),
           "buy_and_hold_mean_per_hour": interval(boot(r, lambda a: float(a.mean()))) if len(r) else None, "rules": {}}
    for rule in ("long_flat", "sign"):
        pos = (q > 0.5).astype(float) if rule == "long_flat" else np.sign(q - 0.5)
        traded = pos != 0
        gross = pos[traded] * r[traded]
        entry_ = {"traded_hours": int(traded.sum()),
                  "gross_mean_per_traded_hour": interval(boot(gross, lambda a: float(a.mean()))) if len(gross) else None,
                  "by_cost": {}}
        for name, c in COSTS_ONE_WAY.items():
            net = gross - 2 * c
            entry_["by_cost"][name] = {"one_way": c, "break_even_gross_per_trade": 2 * c,
                                       "net_mean_per_traded_hour": interval(boot(net, lambda a: float(a.mean()))) if len(net) else None}
        out["rules"][rule] = entry_
    return out


def compute(rows: list[dict], n: int, model=None) -> dict:
    """Every registered measure on exactly `rows` (the first n eligible). Pure apart from loading the artefact."""
    from agent.direction_shadow.model import load_model
    from agent.research.diagnose import spearman
    from agent.research.live_checkpoint import TERCILES_PATH

    assert len(rows) == n
    model = model or load_model(MODEL_VERSION)
    pm = np.array([r["p_model"] for r in rows], float)
    pf = np.array([r["p_one_feature"] for r in rows], float)
    pb = np.array([r["p_base"] for r in rows], float)
    y = np.array([1.0 if r["outcome_up"] else 0.0 for r in rows])
    ret = np.array([r["outcome_return"] for r in rows], float)
    probs = {"model": pm, "one_feature": pf, "base_rate": pb}

    # integrity
    recomputed = [model.predict(r["features"]) for r in rows]
    worst = max(max(abs(a - b) for a, b in zip(rec, (r["p_model"], r["p_one_feature"], r["p_base"]))) for rec, r in zip(recomputed, rows))
    integrity = {"probabilities_recompute_from_stored_inputs_max_abs_diff": worst,
                 "artefact_sha256_all_rows": sorted({r["artefact_sha256"] for r in rows}), "artefact_sha256_now": model.sha256,
                 "live_close_mismatches": sum(1 for r in rows if r["live_close_match"] is False),
                 "live_scores_mismatches": sum(1 for r in rows if r["live_scores_match"] is False)}

    loss = {k: {"brier": float(np.mean((v - y) ** 2)), "log_loss": float(ll_terms(v, y).mean())} for k, v in probs.items()}
    for k in ("model", "one_feature"):
        loss[k]["brier_skill_vs_base_rate"] = 1 - loss[k]["brier"] / loss["base_rate"]["brier"]
    pairs = {"base_minus_model": ("base_rate", "model"), "one_feature_minus_model": ("one_feature", "model"),
             "base_minus_one_feature": ("base_rate", "one_feature")}
    paired = {}
    for name, (ref, ch) in pairs.items():
        d_brier = (probs[ref] - y) ** 2 - (probs[ch] - y) ** 2
        d_ll = ll_terms(probs[ref], y) - ll_terms(probs[ch], y)
        paired[name] = {"brier": interval(boot(d_brier, lambda a: float(a.mean()))),
                        "log_loss": interval(boot(d_ll, lambda a: float(a.mean())))}
    disc = {}
    for k in ("model", "one_feature"):
        pv = np.column_stack([probs[k], y, ret])
        disc[k] = {"auc": interval(boot(pv, lambda a: auc(a[:, 0], a[:, 1]))),
                   "spearman_p_vs_return": interval(boot(pv, lambda a: spearman(a[:, 0], a[:, 2])))}
    up_share = float(y.mean())
    classification = {"accuracy_at_0_5": {k: float(np.mean((probs[k] > 0.5) == (y > 0.5))) for k in ("model", "one_feature")},
                      "majority_share": max(up_share, 1 - up_share), "observed_up_share": up_share}

    # slices (descriptive)
    hours = np.array([r["as_of"].hour for r in rows])
    blocks = {}
    for lo in (0, 6, 12, 18):
        m = (hours >= lo) & (hours < lo + 6)
        if m.any():
            blocks[f"{lo:02d}-{lo + 6:02d}"] = {"rows": int(m.sum()), "stated_minus_observed": float(pm[m].mean() - y[m].mean()),
                                                "base_minus_model_brier": float(np.mean((pb[m] - y[m]) ** 2 - (pm[m] - y[m]) ** 2))}
    cuts = json.loads(TERCILES_PATH.read_text(encoding="utf-8"))["tercile_cut_points"]
    rv = np.array([np.nan if r["regime_rv_168"] is None else r["regime_rv_168"] for r in rows], float)
    regime = np.where(np.isnan(rv), "unknown", np.where(rv < cuts[0], "low", np.where(rv < cuts[1], "mid", "high")))
    regimes = {g: {"rows": int((regime == g).sum()), "stated_minus_observed": float(pm[regime == g].mean() - y[regime == g].mean()),
                   "base_minus_model_brier": float(np.mean((pb[regime == g] - y[regime == g]) ** 2 - (pm[regime == g] - y[regime == g]) ** 2))}
               for g in ("low", "mid", "high", "unknown") if (regime == g).any()}
    weeks = {}
    for i, r in enumerate(rows):
        wk = r["as_of"].strftime("%G-W%V")
        weeks.setdefault(wk, []).append(i)
    weekly = {wk: {"rows": len(ix), "base_minus_model_brier": float(np.mean((pb[ix] - y[ix]) ** 2 - (pm[ix] - y[ix]) ** 2))}
              for wk, ix in weeks.items()}

    entry = np.array([np.nan if r["price_at_prediction"] is None else r["price_at_prediction"] for r in rows], float)
    close = np.array([r["outcome_close"] for r in rows], float)
    econ = {"model": economics(pm, entry, close), "one_feature": economics(pf, entry, close)}
    return {"integrity": integrity, "loss": loss, "paired_differences": paired, "discrimination": disc,
            "calibration": {"model": calibration(pm, y), "one_feature": calibration(pf, y)},
            "classification_descriptive": classification,
            "slices_descriptive": {"six_hour_blocks": blocks, "regime": regimes, "weekly": weekly},
            "economics_descriptive": econ}


# ---------------------------------------------------------------- the verdict (section 7), at 6,500 only
def rule(diff: dict, calib: dict | None) -> str:
    lo, hi = diff["ci95"]
    if lo > 0:
        if calib is None:
            return "IMPROVEMENT"
        ok = abs(calib["stated_minus_observed"]["point"]) <= GUARD_CITL and calib["ece"] <= GUARD_ECE
        return "IMPROVEMENT" if ok else "SKILL, BUT MISCALIBRATED"
    if hi < SESOI:
        return "NO IMPROVEMENT (worse than the reference)" if hi < 0 else "NO IMPROVEMENT"
    return "INSUFFICIENT EVIDENCE"


def verdict(stats: dict) -> dict:
    pd_ = stats["paired_differences"]
    useful = False
    primary = rule(pd_["base_minus_model"]["brier"], stats["calibration"]["model"])
    if primary == "IMPROVEMENT":
        lf = stats["economics_descriptive"]["model"]["rules"]["long_flat"]
        net = lf["by_cost"]["standard"]["net_mean_per_traded_hour"]
        bh = stats["economics_descriptive"]["model"]["buy_and_hold_mean_per_hour"]
        useful = bool(net and bh and net["ci95"][0] > 0 and net["point"] > bh["point"])
    return {"primary_model_vs_base_rate": primary,
            "secondary_model_vs_one_feature": rule(pd_["one_feature_minus_model"]["brier"], stats["calibration"]["model"]),
            "secondary_one_feature_vs_base_rate": rule(pd_["base_minus_one_feature"]["brier"], stats["calibration"]["one_feature"]),
            "economically_useful": useful}


# ---------------------------------------------------------------- reading and writing
def read_rows() -> list[dict]:
    from agent.database.db import get_connection

    with get_connection() as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(SQL)
            cols = [d.name for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def reading(rows: list[dict], n: int, now: datetime) -> dict:
    ok, late = eligible(rows)
    if len(ok) < n:
        raise RuntimeError(f"only {len(ok)} eligible hours; the {n}-hour reading is not due")
    first = ok[:n]
    stats = compute(first, n)
    out = {"track": "E034 direction shadow track", "protocol": "research/DIRECTION_TRACK.md v1.1", "reading_hours": n,
           "computed_at": now.isoformat(), "first_hour": first[0]["as_of"].isoformat(), "last_hour": first[-1]["as_of"].isoformat(),
           "eligible_available": len(ok), "not_prospective_excluded": len(late), "registered": READINGS[n],
           "intervals": f"48h circular block bootstrap, {N_BOOT} resamples, seed {SEED}"
                        + ("; OPTIMISTIC at this size (E025, E033)" if n < OPTIMISTIC_BELOW else ""),
           "stats": stats, "verdict": verdict(stats) if READINGS[n]["verdict"] else None}
    return out


def write_once(doc: dict) -> Path:
    n = doc["reading_hours"]
    base = OUT_DIR / f"direction_checkpoint_{n}h"
    md, js = base.with_suffix(".md"), base.with_suffix(".json")
    if md.exists() or js.exists():
        raise FileExistsError(f"{base}.* exists; a reading is written once and never rewritten")
    js.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    md.write_text(render(doc), encoding="utf-8")
    return md


def render(doc: dict) -> str:
    s = doc["stats"]
    f = lambda d, k=5: (f"{d['point']:+.{k}f} [{d['ci95'][0]:+.{k}f}, {d['ci95'][1]:+.{k}f}]") if d else "n/a"  # noqa: E731
    pdif = s["paired_differences"]
    L = [f"# Direction shadow track: the {doc['reading_hours']:,}-hour reading", "",
         f"Hours {doc['first_hour'][:16]} → {doc['last_hour'][:16]} UTC: exactly the first {doc['reading_hours']:,} eligible hours "
         f"({doc['eligible_available']:,} available; {doc['not_prospective_excluded']} excluded by the prospective rule). "
         f"Intervals: {doc['intervals']}.", "",
         f"**What this reading may conclude (registered 2026-10-15):** {doc['registered']['what']}.", "",
         "## Integrity", "",
         f"- probabilities recomputed from the stored inputs: max difference {s['integrity']['probabilities_recompute_from_stored_inputs_max_abs_diff']:.2e}",
         f"- artefact sha256 in the rows: {', '.join(x[:12] for x in s['integrity']['artefact_sha256_all_rows'])}; now {s['integrity']['artefact_sha256_now'][:12]}",
         f"- live cross-check mismatches: close {s['integrity']['live_close_mismatches']}, category scores {s['integrity']['live_scores_mismatches']}", "",
         "## Probabilistic loss (primary: base rate − model, Brier)", "",
         "| | model | one feature | base rate |", "|---|---|---|---|",
         f"| Brier | {s['loss']['model']['brier']:.5f} | {s['loss']['one_feature']['brier']:.5f} | {s['loss']['base_rate']['brier']:.5f} |",
         f"| log loss | {s['loss']['model']['log_loss']:.5f} | {s['loss']['one_feature']['log_loss']:.5f} | {s['loss']['base_rate']['log_loss']:.5f} |",
         f"| Brier skill vs the base rate | {s['loss']['model']['brier_skill_vs_base_rate']:+.5f} | {s['loss']['one_feature']['brier_skill_vs_base_rate']:+.5f} | — |", "",
         f"- **Brier(base) − Brier(model): {f(pdif['base_minus_model']['brier'])}** (positive = the model is better)",
         f"- Brier(one feature) − Brier(model): {f(pdif['one_feature_minus_model']['brier'])}",
         f"- Brier(base) − Brier(one feature): {f(pdif['base_minus_one_feature']['brier'])}",
         f"- log loss, base − model: {f(pdif['base_minus_model']['log_loss'])}", "",
         "## Discrimination and calibration", "",
         f"- AUC: model {f(s['discrimination']['model']['auc'], 3)}, one feature {f(s['discrimination']['one_feature']['auc'], 3)}",
         f"- Spearman ρ(p, 1h return): model {f(s['discrimination']['model']['spearman_p_vs_return'], 3)}, "
         f"one feature {f(s['discrimination']['one_feature']['spearman_p_vs_return'], 3)}",
         f"- model: stated − observed {f(s['calibration']['model']['stated_minus_observed'], 3)}, ECE {s['calibration']['model']['ece']:.3f}, "
         f"slope {f(s['calibration']['model']['calibration_slope'], 2)}",
         f"- accuracy at 0.5 (descriptive): model {s['classification_descriptive']['accuracy_at_0_5']['model']:.3f}, "
         f"one feature {s['classification_descriptive']['accuracy_at_0_5']['one_feature']:.3f}, majority {s['classification_descriptive']['majority_share']:.3f}", ""]
    econ = s["economics_descriptive"]["model"]
    L += ["## Economics (descriptive only, never a criterion)", "",
          f"Hours with an entry price: {econ['hours_with_an_entry_price']:,} (without: {econ['hours_without']}). "
          f"Buy-and-hold mean per hour: {f(econ['buy_and_hold_mean_per_hour'], 5)}.", "",
          "| rule (model) | traded hours | gross per traded hour | net, standard 0.11% | net, discounted 0.085% | net, optimistic 0.02% |",
          "|---|---|---|---|---|---|"]
    for rname, rr in econ["rules"].items():
        L.append(f"| {rname} | {rr['traded_hours']:,} | {f(rr['gross_mean_per_traded_hour'])} | "
                 + " | ".join(f(rr["by_cost"][c]["net_mean_per_traded_hour"]) for c in ("standard", "discounted", "optimistic")) + " |")
    L += [""]
    if doc["verdict"]:
        v = doc["verdict"]
        L += ["## Verdict (section 7)", "", f"- **Primary, model vs base rate: {v['primary_model_vs_base_rate']}**",
              f"- secondary, model vs one feature: {v['secondary_model_vs_one_feature']}",
              f"- secondary, one feature vs base rate: {v['secondary_one_feature_vs_base_rate']}",
              f"- economically useful: {'yes' if v['economically_useful'] else 'not shown to be economically useful'}", ""]
    else:
        L += ["**No verdict, by registration.**", ""]
    L += ["*Research only. Nothing here changes the BUY/HOLD/SELL signal, move_size_1h_v1, its checkpoints or the holdout, "
          "and nothing is combined with the move-size track.*"]
    return "\n".join(L) + "\n"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.parse_args()
    now = datetime.now(timezone.utc)
    rows = read_rows()
    op = operational(rows, now)
    print(json.dumps({"operational (Amendment 1.1: counts only)": op}, indent=1, default=str))
    ok, _ = eligible(rows)
    for n in READINGS:
        if len(ok) >= n and not (OUT_DIR / f"direction_checkpoint_{n}h.json").exists():
            path = write_once(reading(rows, n, now))
            print(f"the {n}-hour reading was due and is written: {path}")
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
