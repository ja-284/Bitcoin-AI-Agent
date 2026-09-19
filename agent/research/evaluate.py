"""
Baseline evaluation (research brief Parts E/F, regimes from D): scoring 0.1.0 replayed
over the development periods, judged against explicit labels at several horizons and
against trivial reference systems, with block-bootstrap uncertainty, per period, per
year and per market regime. Never touches the sealed holdout (the loader truncates).

    python -m agent.research.evaluate --experiment E001

Writes research/results/<experiment>/results.json and summary.md.
"""

import argparse
import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research import baselines
from agent.research.history import load_bars
from agent.research.labels import DOWN, NEUTRAL, SIGNAL_TO_LABEL, UP, LabelSpec, make_labels
from agent.research.metrics import block_bootstrap, brier_score, classification_report, log_loss, reliability_table, signal_edge
from agent.research.periods import EXPLORATION, HOLDOUT, VALIDATION, period_of
from agent.research.regimes import trend_regime, volatility_regime
from agent.research.replay import replay_cached
from agent.scoring.scorer import SCORING_VERSION
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

HORIZONS = [1, 6, 24, 72, 168]
FIXED_BAND = 0.005
VOL_MULTIPLIER = 0.5
N_BOOT = 500
LABEL_TO_SIGNAL = {UP: "BUY", DOWN: "SELL", NEUTRAL: "HOLD"}
CLASSES_3 = [UP, NEUTRAL, DOWN]


def label_specs() -> list[LabelSpec]:
    specs = []
    for h in HORIZONS:
        specs.append(LabelSpec(h, "binary"))
        specs.append(LabelSpec(h, "three_class", "fixed", FIXED_BAND))
        specs.append(LabelSpec(h, "three_class", "vol_scaled", VOL_MULTIPLIER))
    return specs


def build_frame(bars, rows) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["as_of"] = pd.to_datetime(df["as_of"])
    df["period"] = [period_of(t.to_pydatetime()) for t in df["as_of"]]
    df["year"] = df["as_of"].dt.year
    df["trend_regime"] = trend_regime(rows)
    vol, cuts = volatility_regime(rows)
    df["vol_regime"] = vol
    df.attrs["vol_cuts"] = cuts
    for spec in label_specs():
        lab = make_labels(bars, spec).set_index("as_of")
        df[f"ret_{spec.horizon_hours}h"] = lab["ret"].reindex(df["as_of"]).to_numpy()
        df[f"label_{spec.name}"] = lab["label"].reindex(df["as_of"]).to_numpy()
    return df


def baseline_signals(df: pd.DataFrame, rows) -> dict[str, np.ndarray]:
    exploration = df["period"] == "exploration"
    mix = baselines.signal_mix(list(df.loc[exploration, "signal"]))
    return {
        "system": df["signal"].to_numpy(),
        "always_hold": np.array(baselines.always("HOLD", rows)),
        "random_mix": np.array(baselines.random_signals(rows, mix, seed=1)),
        "momentum_24h": np.array(baselines.momentum_rule(rows, 24)),
        "ma_200h": np.array(baselines.moving_average_rule(rows)),
    }


def majority_signal(df: pd.DataFrame, spec: LabelSpec) -> str:
    labels = df.loc[df["period"] == "exploration", f"label_{spec.name}"].dropna()
    return LABEL_TO_SIGNAL[Counter(labels).most_common(1)[0][0]] if len(labels) else "HOLD"


def evaluate_slice(df: pd.DataFrame, mask: np.ndarray, signals: dict[str, np.ndarray], spec: LabelSpec, with_ci: bool) -> dict:
    h = spec.horizon_hours
    labels = df[f"label_{spec.name}"].to_numpy()
    rets = df[f"ret_{h}h"].to_numpy(dtype=float)
    valid = mask & pd.notna(labels) & ~np.isnan(rets)
    out: dict = {"n": int(valid.sum())}
    if out["n"] == 0:
        return out
    y = labels[valid]
    r = rets[valid]
    block = max(48, 2 * h)

    all_systems = dict(signals)
    all_systems[f"majority"] = np.array([majority_signal(df, spec)] * len(df))
    for name, sig in all_systems.items():
        s = sig[valid]
        entry: dict = {}
        if spec.kind == "three_class":
            entry["classification"] = classification_report(list(y), [SIGNAL_TO_LABEL[x] for x in s], CLASSES_3).to_dict()
        else:
            acted = s != "HOLD"
            entry["coverage"] = float(acted.mean())
            if acted.sum():
                entry["acted_accuracy"] = float(np.mean([SIGNAL_TO_LABEL[x] == t for x, t in zip(s[acted], y[acted])]))
                entry["acted_n"] = int(acted.sum())
        edge_stat = lambda arr: signal_edge(arr[:, 0], arr[:, 1].astype(float))  # noqa: E731
        stacked = np.column_stack([s, r]).astype(object)
        if with_ci:
            point, lo, hi = block_bootstrap(stacked, edge_stat, block=block, n_boot=N_BOOT, seed=7)
        else:
            point, lo, hi = signal_edge(s, r), float("nan"), float("nan")
        entry["edge"] = {"point": point, "ci_low": lo, "ci_high": hi}
        entry["mean_return_by_signal"] = {
            sig_name: {"n": int((s == sig_name).sum()), "mean": float(r[s == sig_name].mean()) if (s == sig_name).any() else None}
            for sig_name in ["BUY", "HOLD", "SELL"]
        }
        out[name] = entry
    out["buy_and_hold_mean_return"] = float(r.mean())
    out["label_distribution"] = {c: float((y == c).mean()) for c in (CLASSES_3 if spec.kind == "three_class" else [UP, DOWN])}
    return out


def confidence_reliability(df: pd.DataFrame, mask: np.ndarray, h: int) -> dict:
    """Does the confidence heuristic behave like a probability that the signal's direction is right?"""
    labels = df[f"label_binary_{h}h"].to_numpy()
    sig = df["signal"].to_numpy()
    conf = df["confidence"].to_numpy(dtype=float)
    score = df["overall_score"].to_numpy(dtype=float)
    valid = mask & pd.notna(labels)
    acted = valid & (sig != "HOLD")
    out: dict = {"acted_n": int(acted.sum())}
    if acted.sum():
        hit = np.array([SIGNAL_TO_LABEL[s] == t for s, t in zip(sig[acted], labels[acted])], dtype=float)
        buckets, ece, mce = reliability_table(conf[acted], hit, edges=[0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0 + 1e-9])
        out["reliability"] = [b.__dict__ | {"reliable": b.reliable} for b in buckets]
        out["ece"] = ece
        out["mce"] = mce
        out["hit_rate"] = float(hit.mean())
    if valid.sum():
        y_up = (labels[valid] == UP).astype(float)
        base_rate = float(y_up.mean())
        out["candidate_probabilities"] = {
            "constant_0.5": {"brier": brier_score(np.full(valid.sum(), 0.5), y_up), "log_loss": log_loss(np.full(valid.sum(), 0.5), y_up)},
            "base_rate_of_slice": {"p": base_rate, "brier": brier_score(np.full(valid.sum(), base_rate), y_up), "log_loss": log_loss(np.full(valid.sum(), base_rate), y_up)},
            "naive_0.5_plus_half_score": {"brier": brier_score(0.5 + score[valid] / 2, y_up), "log_loss": log_loss(0.5 + score[valid] / 2, y_up)},
        }
    return out


def run(experiment: str, processes: int | None) -> Path:
    bars, quality, snapshot = load_bars(end=HOLDOUT.start)
    logger.info("Loaded %d candles from %s (%d gaps, %d missing hours)", quality.count, snapshot.name, len(quality.gaps), quality.missing_hours)
    rows = replay_cached(bars, snapshot, processes=processes)
    df = build_frame(bars, rows)
    signals = baseline_signals(df, rows)

    results: dict = {
        "experiment": experiment,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "pipeline_version": PIPELINE_VERSION,
        "scoring_version": SCORING_VERSION,
        "snapshot": snapshot.name,
        "candles": quality.summary(),
        "replay_hours": len(df),
        "vol_regime_cuts": df.attrs["vol_cuts"],
        "signal_mix": {p: baselines.signal_mix(list(df.loc[df["period"] == p, "signal"])) for p in ["exploration", "validation"]},
        "by_spec": {},
        "confidence": {},
    }

    slices: dict[str, np.ndarray] = {
        "exploration": (df["period"] == "exploration").to_numpy(),
        "validation": (df["period"] == "validation").to_numpy(),
    }
    for year in sorted(df["year"].unique()):
        slices[f"year_{year}"] = (df["year"] == year).to_numpy()
    for p in ["exploration", "validation"]:
        for reg in ["uptrend", "sideways", "downtrend"]:
            slices[f"{p}_trend_{reg}"] = ((df["period"] == p) & (df["trend_regime"] == reg)).to_numpy()
        for reg in ["low", "mid", "high"]:
            slices[f"{p}_vol_{reg}"] = ((df["period"] == p) & (df["vol_regime"] == reg)).to_numpy()

    for spec in label_specs():
        logger.info("Evaluating %s", spec.name)
        results["by_spec"][spec.name] = {
            name: evaluate_slice(df, mask, signals, spec, with_ci=name in ("exploration", "validation") or name.startswith("year_"))
            for name, mask in slices.items()
        }
    for h in HORIZONS:
        results["confidence"][f"{h}h"] = {p: confidence_reliability(df, slices[p], h) for p in ["exploration", "validation"]}

    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_summary(results), encoding="utf-8")
    return out_dir


def _fmt_pct(x):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:+.2f}%"


def render_summary(res: dict) -> str:
    lines = [f"# {res['experiment']} — corrected baseline vs trivial baselines", "",
             f"pipeline {res['pipeline_version']} / scoring {res['scoring_version']} · snapshot {res['snapshot']} · {res['replay_hours']} hours · technical-only (news absent)", "",
             f"Signal mix — exploration: {res['signal_mix']['exploration']} · validation: {res['signal_mix']['validation']}", ""]
    for h in HORIZONS:
        spec3 = f"three_class_{h}h_fixed_{FIXED_BAND:g}"
        lines.append(f"## Horizon {h}h")
        lines.append("")
        lines.append("| system | period | n | edge BUY−SELL [95% CI] | bal. acc (3-class, ±0.5%) | acted acc (binary) | coverage |")
        lines.append("|---|---|---|---|---|---|---|")
        for period in ["exploration", "validation"]:
            s3 = res["by_spec"][spec3][period]
            s2 = res["by_spec"][f"binary_{h}h"][period]
            for name in ["system", "always_hold", "majority", "random_mix", "momentum_24h", "ma_200h"]:
                e = s3.get(name, {})
                b = s2.get(name, {})
                edge = e.get("edge", {})
                ci = f"{_fmt_pct(edge.get('point'))} [{_fmt_pct(edge.get('ci_low'))}, {_fmt_pct(edge.get('ci_high'))}]" if edge else "n/a"
                ba = e.get("classification", {}).get("balanced_accuracy")
                lines.append(f"| {name} | {period} | {s3.get('n', 0)} | {ci} | {ba:.3f} | {b.get('acted_accuracy', float('nan')):.3f} | {b.get('coverage', float('nan')):.2f} |"
                             if ba is not None else f"| {name} | {period} | {s3.get('n', 0)} | {ci} | n/a | n/a | n/a |")
            lines.append(f"| buy-and-hold mean {h}h return | {period} | {s3.get('n', 0)} | {_fmt_pct(s3.get('buy_and_hold_mean_return'))} | | | |")
        lines.append("")
        lines.append("Per year (system edge, point [CI]):")
        yrs = [k for k in res["by_spec"][spec3] if k.startswith("year_")]
        lines.append(" · ".join(f"{k[5:]}: {_fmt_pct(res['by_spec'][spec3][k].get('system', {}).get('edge', {}).get('point'))}" for k in yrs))
        lines.append("")
        conf = res["confidence"][f"{h}h"]
        for period in ["exploration", "validation"]:
            c = conf[period]
            if "reliability" in c:
                lines.append(f"Confidence as a probability ({period}, acted hours n={c['acted_n']}, hit rate {c['hit_rate']:.3f}, ECE {c['ece']:.3f}):")
                lines.append("| stated conf. | n | observed hit rate | 95% interval |")
                lines.append("|---|---|---|---|")
                for bkt in c["reliability"]:
                    flag = "" if bkt["reliable"] else " (too few)"
                    lines.append(f"| {bkt['lower']:.2f}–{bkt['upper']:.2f} (avg {bkt['mean_predicted']:.2f}) | {bkt['n']} | {bkt['observed']:.3f} | [{bkt['ci_low']:.3f}, {bkt['ci_high']:.3f}]{flag} |")
                cp = c["candidate_probabilities"]
                lines.append(f"Brier — constant 0.5: {cp['constant_0.5']['brier']:.4f} · base rate {cp['base_rate_of_slice']['p']:.3f}: {cp['base_rate_of_slice']['brier']:.4f} · naive 0.5+score/2: {cp['naive_0.5_plus_half_score']['brier']:.4f}")
                lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--processes", type=int, default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    out = run(args.experiment, args.processes)
    print(f"Results written to {out}")
    print((out / "summary.md").read_text(encoding="utf-8"))
