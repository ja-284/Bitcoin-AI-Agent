"""
Walk-forward model tests on the real development data (Phases 6 verification and 9).

Assembles one hourly frame: the E001 replay (baseline signals), every research feature
group, and the labels for one horizon; then runs a chosen model through the walk-forward
framework and evaluates the concatenated out-of-sample predictions with the same metrics
used everywhere else (accuracy vs naive rate, Brier, log loss, reliability, edge with
block-bootstrap intervals), overall, per period and per year.

Models:
  memorise    control: label lookup by timestamp (must score exactly chance)
  last_label  control: carries the last training label forward (must not beat the naive rate)
  base_rate   control: predicts the training prior
  logistic    L2-regularised logistic regression (Phase 9), standardised inside each fold

    python -m agent.research.model_test --experiment E010 --model memorise --horizon 24
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research.derivatives import DERIVATIVES_FEATURES
from agent.research.evaluate import N_BOOT
from agent.research.feature_test import GROUPS, compute_group_features
from agent.research.features import REGIME_FEATURES, VOLATILITY_FEATURES
from agent.research.history import load_bars
from agent.research.labels import LabelSpec, make_labels
from agent.research.macro import MACRO_FEATURES
from agent.research.metrics import block_bootstrap, brier_score, log_loss, reliability_table, signal_edge
from agent.research.microstructure import MICROSTRUCTURE_FEATURES
from agent.research.onchain import ONCHAIN_FEATURES
from agent.research.periods import HOLDOUT, period_of
from agent.research.replay import replay_cached
from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward
from agent.scoring.scorer import SCORING_VERSION
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)

ALL_FEATURE_GROUPS = {
    "volatility": VOLATILITY_FEATURES, "regime": REGIME_FEATURES, "derivatives": DERIVATIVES_FEATURES,
    "macro": MACRO_FEATURES, "onchain": ONCHAIN_FEATURES, "microstructure": MICROSTRUCTURE_FEATURES,
}
BASELINE_CATEGORY_SCORES = ["trend_score", "momentum_score", "volume_score", "chart_pattern_score"]


# ---------------------------------------------------------------- models
class MemoriseModel:
    def fit(self, X, y):
        self.table = dict(zip(X.index, y))

    def predict_proba(self, X):
        return np.array([self.table.get(t, 0.5) for t in X.index])


class LastLabelModel:
    def fit(self, X, y):
        self.last = float(y[-1])

    def predict_proba(self, X):
        return np.full(len(X), self.last)


class BaseRateModel:
    def fit(self, X, y):
        self.p = float(np.mean(y))

    def predict_proba(self, X):
        return np.full(len(X), self.p)


class LogisticModel:
    """Standardisation fitted on training rows only; L2 penalty fixed in advance (C=0.1)."""

    def __init__(self, C: float = 0.1):
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        self.pipe = make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000))

    def fit(self, X, y):
        self.pipe.fit(X.to_numpy(dtype=float), y)

    def predict_proba(self, X):
        return self.pipe.predict_proba(X.to_numpy(dtype=float))[:, 1]

    def coefficients(self, names):
        lr = self.pipe.steps[-1][1]
        return dict(zip(names, lr.coef_[0].round(4).tolist()))


MODELS = {"memorise": MemoriseModel, "last_label": LastLabelModel, "base_rate": BaseRateModel, "logistic": LogisticModel}


# ---------------------------------------------------------------- data
def build_frame(horizon: int, groups: list[str]) -> tuple[pd.DataFrame, list[str]]:
    bars, quality, snapshot = load_bars(end=HOLDOUT.start)
    rows = replay_cached(bars, snapshot)
    df = pd.DataFrame(rows)
    df["as_of"] = pd.to_datetime(df["as_of"])
    df = df.set_index("as_of").sort_index()
    feature_cols: list[str] = []
    for g in groups:
        feats = compute_group_features(g, bars)
        for col in GROUPS[g]:
            df[col] = feats[col].reindex(df.index).to_numpy()
            feature_cols.append(col)
    lab = make_labels(bars, LabelSpec(horizon, "binary")).set_index("as_of")
    df[f"fwd_{horizon}h"] = lab["ret"].reindex(df.index).to_numpy()
    df["y"] = (lab["label"].reindex(df.index) == "UP").astype(float).where(lab["label"].reindex(df.index).notna())
    df["period"] = [period_of(t.to_pydatetime()) for t in df.index]
    df["year"] = df.index.year
    df.attrs["snapshot"] = snapshot.name
    return df, feature_cols


# ---------------------------------------------------------------- evaluation
def evaluate_predictions(preds: pd.DataFrame, df: pd.DataFrame, horizon: int) -> dict:
    joined = preds.join(df[[f"fwd_{horizon}h", "period", "year", "signal"]], how="left")
    out: dict = {"n": int(len(joined))}
    y = joined["y"].to_numpy(dtype=float)
    p = joined["p"].to_numpy(dtype=float)
    ret = joined[f"fwd_{horizon}h"].to_numpy(dtype=float)

    def stats(mask: np.ndarray, with_ci: bool) -> dict:
        yy, pp, rr = y[mask], p[mask], ret[mask]
        if len(yy) == 0:
            return {"n": 0}
        pred_up = pp > 0.5
        acted = pp != 0.5
        acc = float(np.mean(pred_up[acted] == (yy[acted] > 0.5))) if acted.any() else float("nan")
        base = float(np.mean(yy))
        naive = max(base, 1 - base)
        sig = np.where(pp > 0.5, "BUY", np.where(pp < 0.5, "SELL", "HOLD"))
        d = {
            "n": int(len(yy)), "base_rate_up": base, "naive_rate": naive, "acted_share": float(acted.mean()),
            "acted_accuracy": acc, "brier": brier_score(pp, yy), "log_loss": log_loss(pp, yy),
            "brier_base_rate": brier_score(np.full(len(yy), base), yy),
        }
        block = max(48, 2 * horizon)
        stacked = np.column_stack([sig, rr]).astype(object)
        if with_ci and len(yy) >= 2 * block:
            pt, lo, hi = block_bootstrap(stacked, lambda a: signal_edge(a[:, 0], a[:, 1].astype(float)), block=block, n_boot=N_BOOT, seed=31)
        else:
            pt, lo, hi = signal_edge(sig, rr), float("nan"), float("nan")
        d["edge"] = {"point": pt, "ci_low": lo, "ci_high": hi}
        buckets, ece, mce = reliability_table(pp, yy)
        d["reliability"] = [b.__dict__ | {"enough_rows": b.reliable} for b in buckets]
        d["ece"] = ece
        return d

    out["overall"] = stats(np.ones(len(y), bool), True)
    for per in ("exploration", "validation"):
        out[per] = stats((joined["period"] == per).to_numpy(), True)
    out["by_year"] = {int(yr): stats((joined["year"] == yr).to_numpy(), False) for yr in sorted(joined["year"].unique())}
    # baseline (scoring 0.1.0) on exactly the same rows, for a like-for-like reference
    sig_b = joined["signal"].to_numpy()
    acted_b = sig_b != "HOLD"
    out["baseline_0_1_0_same_rows"] = {
        "acted_share": float(acted_b.mean()),
        "acted_accuracy": float(np.mean((sig_b[acted_b] == "BUY") == (y[acted_b] > 0.5))) if acted_b.any() else float("nan"),
        "edge": signal_edge(sig_b, ret),
    }
    return out


def run(experiment: str, model_name: str, horizon: int, groups: list[str], scheme: str, calib_days: int, C: float) -> Path:
    df, feature_cols = build_frame(horizon, groups)
    spec = WalkForwardSpec(horizon_hours=horizon, scheme=scheme, min_train_days=365, test_block_days=90, embargo_hours=24, calib_days=calib_days)
    if model_name == "logistic":
        make_model = lambda: LogisticModel(C=C)  # noqa: E731
        cols = feature_cols
    else:
        make_model = MODELS[model_name]
        cols = feature_cols or BASELINE_CATEGORY_SCORES  # controls ignore features; something must be present
    folds = make_folds(df.index, spec)
    preds, diag = run_walk_forward(df, cols, "y", make_model, spec, folds=folds)
    results = {
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
        "scoring_version": SCORING_VERSION, "snapshot": df.attrs["snapshot"], "model": model_name, "horizon": horizon, "groups": groups,
        "features": cols, "spec": spec.__dict__, "folds": len(folds), "fold_diagnostics": diag,
        "evaluation": evaluate_predictions(preds, df, horizon),
    }
    if model_name == "logistic":
        last = make_model()
        train = df[feature_cols + ["y"]].dropna()
        train = train[train.index < folds[-1].train_end]
        last.fit(train[feature_cols], train["y"].to_numpy(dtype=float))
        results["coefficients_last_fold_training"] = last.coefficients(feature_cols)
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{model_name}_{scheme}_{horizon}h"
    (out_dir / f"{tag}.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    preds.to_csv(out_dir / f"{tag}_oos_predictions.csv")
    (out_dir / f"{tag}.md").write_text(render(results), encoding="utf-8")
    return out_dir / f"{tag}.md"


def _fmt(d: dict) -> str:
    if d.get("n", 0) == 0:
        return "n=0"
    e = d["edge"]
    ci = f"[{e['ci_low'] * 100:+.2f}, {e['ci_high'] * 100:+.2f}]" if not np.isnan(e["ci_low"]) else ""
    return (f"n={d['n']} acted={d['acted_share']:.2f} acc={d['acted_accuracy']:.3f} naive={d['naive_rate']:.3f} "
            f"brier={d['brier']:.4f} (base {d['brier_base_rate']:.4f}) ece={d['ece']:.3f} edge={e['point'] * 100:+.2f}% {ci}")


def render(res: dict) -> str:
    ev = res["evaluation"]
    L = [f"# {res['experiment']} — {res['model']} · {res['spec']['scheme']} · {res['horizon']}h", "",
         f"pipeline {res['pipeline_version']} / scoring {res['scoring_version']} · snapshot {res['snapshot']} · {res['folds']} folds · features: {len(res['features'])} ({', '.join(res['groups']) or 'none'})", "",
         f"- overall:     {_fmt(ev['overall'])}", f"- exploration: {_fmt(ev['exploration'])}", f"- validation:  {_fmt(ev['validation'])}", "",
         "Per year (acted accuracy / naive / edge %):"]
    for yr, d in ev["by_year"].items():
        if d.get("n"):
            L.append(f"- {yr}: {d['acted_accuracy']:.3f} / {d['naive_rate']:.3f} / {d['edge']['point'] * 100:+.2f}")
    b = ev["baseline_0_1_0_same_rows"]
    L += ["", f"Baseline scoring 0.1.0 on the same rows: acted={b['acted_share']:.2f} acc={b['acted_accuracy']:.3f} edge={b['edge'] * 100:+.2f}%", ""]
    if "coefficients_last_fold_training" in res:
        L += ["Coefficients (standardised features, last fold's training range):", ""]
        for k, v in sorted(res["coefficients_last_fold_training"].items(), key=lambda kv: -abs(kv[1])):
            L.append(f"- {k}: {v:+.4f}")
    L += ["", "Fold gaps (hours between last fitted row and test start): " + ", ".join(str(int(d["gap_hours_between_last_fit_row_and_test_start"])) for d in res["fold_diagnostics"][:6]) + " ..."]
    return "\n".join(L)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True)
    parser.add_argument("--model", required=True, choices=list(MODELS))
    parser.add_argument("--horizon", type=int, default=24)
    parser.add_argument("--groups", default="", help="comma-separated feature groups; empty = none")
    parser.add_argument("--scheme", default="expanding", choices=["expanding", "rolling"])
    parser.add_argument("--calib-days", type=int, default=0)
    parser.add_argument("--C", type=float, default=0.1)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    groups = [g for g in args.groups.split(",") if g]
    path = run(args.experiment, args.model, args.horizon, groups, args.scheme, args.calib_days, args.C)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(path.read_text(encoding="utf-8"))
