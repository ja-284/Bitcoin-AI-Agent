"""
E002: take the scoring system apart. Uses the cached E001 replay (every hour's category
scores) and asks, per category and per horizon:

  - does the category's score, on its own, relate to what the price did next?
    (Spearman rank correlation with the forward return, block-bootstrap interval)
  - what does the relationship look like? (mean forward return by score decile)
  - what happens to the combined system if the category is removed? (ablation)
  - how much do the categories overlap? (correlation between category scores)

Nothing is tuned. Outputs research/results/<experiment>/{results.json, summary.md}.

    python -m agent.research.diagnose --experiment E002
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from agent.decision.decision import decide_signal
from agent.research.evaluate import CLASSES_3, FIXED_BAND, HORIZONS, N_BOOT
from agent.research.history import load_bars
from agent.research.labels import SIGNAL_TO_LABEL, LabelSpec, make_labels
from agent.research.metrics import block_bootstrap, classification_report, signal_edge
from agent.research.periods import HOLDOUT, period_of
from agent.research.regimes import trend_regime
from agent.research.replay import CATEGORIES, replay_cached
from agent.scoring.scorer import NOMINAL_WEIGHTS, SCORING_VERSION
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

TECHNICAL = [c for c in CATEGORIES if c != "news"]


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return float(pd.Series(x).rank().corr(pd.Series(y).rank()))


def _spearman_stat(arr: np.ndarray) -> float:
    return spearman(arr[:, 0], arr[:, 1])


def recombine(df: pd.DataFrame, drop: str | None) -> np.ndarray:
    """The system's overall score recomputed from stored category scores, leaving one out (as combine_scores does)."""
    score = np.zeros(len(df))
    weight = np.zeros(len(df))
    for c in TECHNICAL:
        if c == drop:
            continue
        w = df[f"{c}_weight"].to_numpy(dtype=float)
        score += df[f"{c}_score"].to_numpy(dtype=float) * w
        weight += w
    with np.errstate(invalid="ignore", divide="ignore"):
        overall = np.where(weight > 0, score / weight, 0.0)
    return overall


def run(experiment: str) -> Path:
    bars, quality, snapshot = load_bars(end=HOLDOUT.start)
    rows = replay_cached(bars, snapshot)
    df = pd.DataFrame(rows)
    df["as_of"] = pd.to_datetime(df["as_of"])
    df["period"] = [period_of(t.to_pydatetime()) for t in df["as_of"]]
    df["year"] = df["as_of"].dt.year
    df["trend_regime"] = trend_regime(rows)
    for h in HORIZONS:
        lab = make_labels(bars, LabelSpec(h, "three_class", "fixed", FIXED_BAND)).set_index("as_of")
        df[f"ret_{h}h"] = lab["ret"].reindex(df["as_of"]).to_numpy()
        df[f"label3_{h}h"] = lab["label"].reindex(df["as_of"]).to_numpy()

    results: dict = {
        "experiment": experiment,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "pipeline_version": PIPELINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "snapshot": snapshot.name,
        "hours": len(df),
        "single_category": {},
        "ablation": {},
        "redundancy": {},
    }

    periods = {"exploration": (df["period"] == "exploration").to_numpy(), "validation": (df["period"] == "validation").to_numpy()}

    # --- redundancy: how much do the category scores move together? (exploration, active rows only)
    expl = df[periods["exploration"]]
    cols = [f"{c}_score" for c in TECHNICAL]
    results["redundancy"] = {
        "pearson": expl[cols].corr(method="pearson").round(3).to_dict(),
        "spearman": expl[cols].corr(method="spearman").round(3).to_dict(),
        "share_of_hours_category_active": {c: float((expl[f"{c}_weight"] > 0).mean()) for c in TECHNICAL},
    }

    # --- single categories
    for c in TECHNICAL:
        score = df[f"{c}_score"].to_numpy(dtype=float)
        active = df[f"{c}_weight"].to_numpy(dtype=float) > 0
        signal = np.array([decide_signal(s) if a else "HOLD" for s, a in zip(score, active)])
        entry: dict = {"signal_mix_exploration": {s: float((signal[periods["exploration"]] == s).mean()) for s in ["BUY", "HOLD", "SELL"]}}
        for h in HORIZONS:
            ret = df[f"ret_{h}h"].to_numpy(dtype=float)
            block = max(48, 2 * h)
            hz: dict = {}
            for pname, pmask in periods.items():
                m = pmask & active & ~np.isnan(ret)
                stacked = np.column_stack([score[m], ret[m]])
                rho, lo, hi = block_bootstrap(stacked, _spearman_stat, block=block, n_boot=N_BOOT, seed=11)
                edge_pt, edge_lo, edge_hi = block_bootstrap(
                    np.column_stack([signal[m], ret[m]]).astype(object),
                    lambda a: signal_edge(a[:, 0], a[:, 1].astype(float)), block=block, n_boot=N_BOOT, seed=12,
                )
                hz[pname] = {"n": int(m.sum()), "spearman": {"point": rho, "ci_low": lo, "ci_high": hi},
                             "edge": {"point": edge_pt, "ci_low": edge_lo, "ci_high": edge_hi}}
                # by trend regime
                hz[pname]["spearman_by_trend_regime"] = {}
                for reg in ["uptrend", "sideways", "downtrend"]:
                    rm = m & (df["trend_regime"].to_numpy() == reg)
                    if rm.sum() > 500:
                        hz[pname]["spearman_by_trend_regime"][reg] = {"n": int(rm.sum()), "spearman": spearman(score[rm], ret[rm])}
            # per-year sign of edge (point estimates only)
            hz["edge_by_year"] = {}
            for year in sorted(df["year"].unique()):
                m = (df["year"].to_numpy() == year) & active & ~np.isnan(ret)
                if m.sum():
                    hz["edge_by_year"][int(year)] = signal_edge(signal[m], ret[m])
            # decile shape (exploration)
            m = periods["exploration"] & active & ~np.isnan(ret)
            if m.sum() > 1000:
                deciles = pd.qcut(pd.Series(score[m]).rank(method="first"), 10, labels=False)
                hz["mean_return_by_score_decile_exploration"] = [float(np.mean(ret[m][deciles == d])) for d in range(10)]
            # pre-registered verdict
            e, v = hz["exploration"]["spearman"], hz["validation"]["spearman"]
            same_sign = np.sign(e["point"]) == np.sign(v["point"]) and e["point"] != 0
            excl = (e["ci_low"] > 0 and v["ci_low"] > 0) or (e["ci_high"] < 0 and v["ci_high"] < 0)
            hz["verdict"] = ("information (positive)" if excl and e["point"] > 0 else "information (NEGATIVE: points the wrong way)" if excl else "no evidence") if same_sign else "no evidence"
            entry[f"{h}h"] = hz
        results["single_category"][c] = entry

    # --- ablation: leave one category out of the combination
    for drop in [None] + TECHNICAL:
        overall = recombine(df, drop)
        signal = np.array([decide_signal(s) for s in overall])
        entry = {}
        for h in HORIZONS:
            ret = df[f"ret_{h}h"].to_numpy(dtype=float)
            labels = df[f"label3_{h}h"].to_numpy()
            hz = {}
            for pname, pmask in periods.items():
                m = pmask & ~np.isnan(ret) & pd.notna(labels)
                pt, lo, hi = block_bootstrap(np.column_stack([signal[m], ret[m]]).astype(object),
                                             lambda a: signal_edge(a[:, 0], a[:, 1].astype(float)),
                                             block=max(48, 2 * h), n_boot=N_BOOT, seed=13)
                rep = classification_report(list(labels[m]), [SIGNAL_TO_LABEL[s] for s in signal[m]], CLASSES_3)
                hz[pname] = {"n": int(m.sum()), "edge": {"point": pt, "ci_low": lo, "ci_high": hi}, "balanced_accuracy": rep.balanced_accuracy,
                             "signal_mix": {s: float((signal[m] == s).mean()) for s in ["BUY", "HOLD", "SELL"]}}
            entry[f"{h}h"] = hz
        results["ablation"]["full_system" if drop is None else f"without_{drop}"] = entry

    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(render(results), encoding="utf-8")
    return out_dir


def _ci(d: dict, pct: bool) -> str:
    f = (lambda x: f"{x * 100:+.2f}%") if pct else (lambda x: f"{x:+.3f}")
    return f"{f(d['point'])} [{f(d['ci_low'])}, {f(d['ci_high'])}]"


def render(res: dict) -> str:
    L = [f"# {res['experiment']} — category diagnosis and ablation", "",
         f"pipeline {res['pipeline_version']} / scoring {res['scoring_version']} · {res['hours']} hours · technical-only", "",
         "## Single categories: rank correlation of score with forward return (Spearman, block-bootstrap 95% CI)", "",
         "| category | horizon | exploration ρ [CI] | validation ρ [CI] | verdict | edge expl. | edge valid. |", "|---|---|---|---|---|---|---|"]
    for c, entry in res["single_category"].items():
        for h in HORIZONS:
            hz = entry[f"{h}h"]
            L.append(f"| {c} | {h}h | {_ci(hz['exploration']['spearman'], False)} | {_ci(hz['validation']['spearman'], False)} | {hz['verdict']} | {_ci(hz['exploration']['edge'], True)} | {_ci(hz['validation']['edge'], True)} |")
    L += ["", "Per-year sign of each category's edge at 24h (BUY−SELL, %):", ""]
    for c, entry in res["single_category"].items():
        yrs = entry["24h"]["edge_by_year"]
        L.append(f"- {c}: " + " · ".join(f"{y}: {v * 100:+.2f}" for y, v in yrs.items()))
    L += ["", "Mean 24h return by score decile (exploration; decile 1 = most bearish score, 10 = most bullish):", ""]
    for c, entry in res["single_category"].items():
        dec = entry["24h"].get("mean_return_by_score_decile_exploration")
        if dec:
            L.append(f"- {c}: " + " ".join(f"{v * 100:+.2f}" for v in dec))
    L += ["", "## Ablation: leave one category out (edge BUY−SELL, %; balanced accuracy, 3-class ±0.5%)", "",
          "| variant | horizon | expl. edge [CI] | expl. bal.acc | valid. edge [CI] | valid. bal.acc | valid. mix BUY/HOLD/SELL |", "|---|---|---|---|---|---|---|"]
    for variant, entry in res["ablation"].items():
        for h in [6, 24, 168]:
            hz = entry[f"{h}h"]
            mix = hz["validation"]["signal_mix"]
            L.append(f"| {variant} | {h}h | {_ci(hz['exploration']['edge'], True)} | {hz['exploration']['balanced_accuracy']:.3f} | {_ci(hz['validation']['edge'], True)} | {hz['validation']['balanced_accuracy']:.3f} | {mix['BUY']:.2f}/{mix['HOLD']:.2f}/{mix['SELL']:.2f} |")
    L += ["", "## Redundancy: correlation between category scores (exploration)", ""]
    pear = res["redundancy"]["pearson"]
    names = list(pear.keys())
    L.append("| | " + " | ".join(n.replace("_score", "") for n in names) + " |")
    L.append("|---|" + "---|" * len(names))
    for a in names:
        L.append(f"| {a.replace('_score', '')} | " + " | ".join(f"{pear[a][b]:+.2f}" for b in names) + " |")
    L.append("")
    L.append("Share of hours each category had data: " + ", ".join(f"{c}: {v:.2f}" for c, v in res["redundancy"]["share_of_hours_category_active"].items()))
    return "\n".join(L)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = run(args.experiment)
    print((out / "summary.md").read_text(encoding="utf-8"))
