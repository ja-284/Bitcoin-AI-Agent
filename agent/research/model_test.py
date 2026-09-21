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
from agent.research.features import CALENDAR_FEATURES, REGIME_FEATURES, VOLATILITY_FEATURES
from agent.research.history import load_bars
from agent.research.labels import LabelSpec, make_labels
from agent.research.macro import MACRO_FEATURES
from agent.research.diagnose import spearman
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
    "macro": MACRO_FEATURES, "onchain": ONCHAIN_FEATURES, "microstructure": MICROSTRUCTURE_FEATURES, "calendar": CALENDAR_FEATURES,
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


# ---------------------------------------------------------------- calibrators (Phase 11)
# A calibrator re-maps a model's stated probabilities using ONLY the fold's purged calibration
# slice. It cannot add information -- only make the numbers honest.
class PlattCalibrator:
    """p -> sigmoid(a * logit(p) + b): two parameters, fitted by unregularised logistic regression."""

    def fit(self, p, y):
        from sklearn.linear_model import LogisticRegression

        self.lr = LogisticRegression(C=1e6, max_iter=2000)
        self.lr.fit(_logit(p).reshape(-1, 1), y)

    def transform(self, p):
        return self.lr.predict_proba(_logit(p).reshape(-1, 1))[:, 1]

    def params(self):
        return {"a": float(self.lr.coef_[0][0]), "b": float(self.lr.intercept_[0])}


class IsotonicCalibrator:
    """Monotone step function through the calibration slice; constant outside the fitted range."""

    def fit(self, p, y):
        from sklearn.isotonic import IsotonicRegression

        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self.iso.fit(np.asarray(p, float), np.asarray(y, float))

    def transform(self, p):
        return self.iso.predict(np.asarray(p, float))


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


CALIBRATORS = {"none": None, "platt": PlattCalibrator, "isotonic": IsotonicCalibrator}


# ---------------------------------------------------------------- data
def groups_for(features: list[str]) -> list[str]:
    """The feature groups that must be computed to supply `features` (category scores need none)."""
    needed = []
    for f in features:
        if f in BASELINE_CATEGORY_SCORES:
            continue
        owners = [g for g, cols in GROUPS.items() if f in cols]
        if not owners:
            raise ValueError(f"unknown feature {f!r}")
        if owners[0] not in needed:
            needed.append(owners[0])
    return needed


def build_frame(horizon: int, groups: list[str], features: list[str] | None = None,
                target: str = "direction", threshold: float | None = None) -> tuple[pd.DataFrame, list[str]]:
    """
    Replay rows (category scores) + the requested feature groups + labels, indexed by
    reference hour. With `features`, only those columns are kept as model inputs (an explicit,
    pre-registered list) and the groups that supply them are computed automatically.

    target = "direction":  y = 1 if the H-hour return is > 0 (UP)
    target = "large_move": y = 1 if |H-hour return| > threshold (a move-SIZE label; the sign
                           is ignored). `threshold` is a fraction, fixed in advance per horizon.
    """
    bars, quality, snapshot = load_bars(end=HOLDOUT.start)
    rows = replay_cached(bars, snapshot)
    df = pd.DataFrame(rows)
    df["as_of"] = pd.to_datetime(df["as_of"])
    df = df.set_index("as_of").sort_index()
    if features:
        groups = groups_for(features)
    feature_cols: list[str] = []
    for g in groups:
        feats = compute_group_features(g, bars)
        for col in GROUPS[g]:
            df[col] = feats[col].reindex(df.index).to_numpy()
            feature_cols.append(col)
    if features:
        feature_cols = list(features)
    lab = make_labels(bars, LabelSpec(horizon, "binary")).set_index("as_of")
    ret = lab["ret"].reindex(df.index)
    df[f"fwd_{horizon}h"] = ret.to_numpy()
    if target == "direction":
        df["y"] = (lab["label"].reindex(df.index) == "UP").astype(float).where(lab["label"].reindex(df.index).notna())
    elif target == "large_move":
        if threshold is None or threshold <= 0:
            raise ValueError("large_move needs a positive threshold")
        df["y"] = (ret.abs() > threshold).astype(float).where(ret.notna())
    else:
        raise ValueError(f"unknown target {target!r}")
    df.attrs["target"] = target
    df.attrs["threshold"] = threshold
    df["period"] = [period_of(t.to_pydatetime()) for t in df.index]
    df["year"] = df.index.year
    df.attrs["snapshot"] = snapshot.name
    return df, feature_cols


# ---------------------------------------------------------------- evaluation
def evaluate_predictions(preds: pd.DataFrame, df: pd.DataFrame, horizon: int) -> dict:
    """
    For the direction target, "edge" is the mean forward return when the model says UP minus
    when it says DOWN. For the large_move target the quantity that matters is size, so "edge"
    becomes the mean |forward return| when the model says LARGE minus when it says SMALL, and
    a rank correlation between the stated probability and the realised |return| is added.
    """
    joined = preds.join(df[[f"fwd_{horizon}h", "period", "year", "signal"]], how="left")
    out: dict = {"n": int(len(joined)), "target": df.attrs.get("target", "direction"), "threshold": df.attrs.get("threshold")}
    size_target = out["target"] == "large_move"
    y = joined["y"].to_numpy(dtype=float)
    p = joined["p"].to_numpy(dtype=float)
    ret = joined[f"fwd_{horizon}h"].to_numpy(dtype=float)
    if size_target:
        ret = np.abs(ret)  # every "edge" below is then a difference in move size

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
        if size_target:
            pairs = np.column_stack([pp, rr])  # rank correlation: stated probability vs realised |return|
            if with_ci and len(yy) >= 2 * block:
                r_pt, r_lo, r_hi = block_bootstrap(pairs, lambda a: spearman(a[:, 0], a[:, 1]), block=block, n_boot=N_BOOT, seed=31)
            else:
                r_pt, r_lo, r_hi = spearman(pp, rr), float("nan"), float("nan")
            d["rank_corr_p_vs_abs_return"] = {"point": r_pt, "ci_low": r_lo, "ci_high": r_hi}
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


def run(experiment: str, model_name: str, horizon: int, groups: list[str], scheme: str, calib_days: int, C: float,
        features: list[str] | None = None, tag: str | None = None, target: str = "direction", threshold: float | None = None,
        log_features: list[str] | None = None, calibrator: str = "none") -> Path:
    if calibrator != "none" and not calib_days:
        raise ValueError("a calibrator needs a calibration slice (--calib-days > 0)")
    df, feature_cols = build_frame(horizon, groups, features, target, threshold)
    for c in log_features or []:  # heavy-tailed positive inputs enter on a log scale (declared per experiment)
        bad = int((df[c].dropna() <= 0).sum())
        if bad:  # a ratio of exactly 0 (e.g. a candle with no trades) is not a real observation -> missing
            logger.warning("%s: %d non-positive values treated as missing before log-transform", c, bad)
        df[c] = np.log(df[c].where(df[c] > 0))
    spec = WalkForwardSpec(horizon_hours=horizon, scheme=scheme, min_train_days=365, test_block_days=90, embargo_hours=24, calib_days=calib_days)
    fitted: list[LogisticModel] = []
    if model_name == "logistic":
        def make_model():
            m = LogisticModel(C=C)
            fitted.append(m)  # every per-fold model is kept so coefficient signs can be checked across time
            return m
        cols = feature_cols
    else:
        make_model = MODELS[model_name]
        cols = feature_cols or BASELINE_CATEGORY_SCORES  # controls ignore features; something must be present
    # Folds are laid over the hours where every input exists (sources such as funding start late);
    # the hourly grid itself is unchanged, so the first test block simply starts later.
    fold_index = df[cols + ["y"]].dropna().index
    folds = make_folds(fold_index, spec)
    calibrators: list = []
    make_calibrator = None
    if CALIBRATORS[calibrator] is not None:
        def make_calibrator():
            c = CALIBRATORS[calibrator]()
            calibrators.append(c)
            return c
    preds, diag = run_walk_forward(df, cols, "y", make_model, spec, folds=folds, make_calibrator=make_calibrator)
    results = {
        "experiment": experiment, "generated_at": datetime.now(timezone.utc).isoformat(), "pipeline_version": PIPELINE_VERSION,
        "scoring_version": SCORING_VERSION, "snapshot": df.attrs["snapshot"], "model": model_name, "horizon": horizon, "groups": groups,
        "features": cols, "log_features": log_features or [], "target": target, "threshold": threshold, "calibrator": calibrator,
        "spec": spec.__dict__, "folds": len(folds), "fold_diagnostics": diag,
        "evaluation": evaluate_predictions(preds, df, horizon),
    }
    if calibrator == "platt":
        results["platt_params_per_fold"] = [c.params() for c in calibrators]
    if model_name == "logistic":
        per_fold = [m.coefficients(cols) for m in fitted]
        results["coefficients_per_fold"] = per_fold
        results["coefficients_last_fold_training"] = per_fold[-1]
        # sign stability: share of folds in which each coefficient has the same sign as its median
        results["coefficient_sign_agreement"] = {
            c: float(np.mean([np.sign(pf[c]) == np.sign(np.median([q[c] for q in per_fold])) for pf in per_fold])) for c in cols
        }
    out_dir = Path("research") / "results" / experiment
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = tag or f"{model_name}_{scheme}_{horizon}h"
    (out_dir / f"{tag}.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    preds.to_csv(out_dir / f"{tag}_oos_predictions.csv")
    (out_dir / f"{tag}.md").write_text(render(results), encoding="utf-8")
    return out_dir / f"{tag}.md"


def _fmt(d: dict) -> str:
    if d.get("n", 0) == 0:
        return "n=0"
    e = d["edge"]
    ci = f"[{e['ci_low'] * 100:+.2f}, {e['ci_high'] * 100:+.2f}]" if not np.isnan(e["ci_low"]) else ""
    s = (f"n={d['n']} acted={d['acted_share']:.2f} acc={d['acted_accuracy']:.3f} naive={d['naive_rate']:.3f} "
         f"brier={d['brier']:.4f} (base {d['brier_base_rate']:.4f}) ece={d['ece']:.3f} edge={e['point'] * 100:+.2f}% {ci}")
    if "rank_corr_p_vs_abs_return" in d:
        r = d["rank_corr_p_vs_abs_return"]
        rci = f"[{r['ci_low']:+.3f}, {r['ci_high']:+.3f}]" if not np.isnan(r["ci_low"]) else ""
        s += f" rho(p,|ret|)={r['point']:+.3f} {rci}"
    return s


def render(res: dict) -> str:
    ev = res["evaluation"]
    tgt = res.get("target", "direction")
    tgt_s = "direction (UP/DOWN)" if tgt == "direction" else f"large move (|return| > {res['threshold'] * 100:.2f}%)"
    cal = res.get("calibrator", "none")
    L = [f"# {res['experiment']} — {res['model']} · {res['spec']['scheme']} · {res['horizon']}h · target: {tgt_s} · calibrator: {cal}", "",
         f"pipeline {res['pipeline_version']} / scoring {res['scoring_version']} · snapshot {res['snapshot']} · {res['folds']} folds · features: {len(res['features'])} ({', '.join(res['groups']) or 'none'})", "",
         f"- overall:     {_fmt(ev['overall'])}", f"- exploration: {_fmt(ev['exploration'])}", f"- validation:  {_fmt(ev['validation'])}", "",
         "Per year (acted accuracy / naive / edge %):"]
    for yr, d in ev["by_year"].items():
        if d.get("n"):
            L.append(f"- {yr}: {d['acted_accuracy']:.3f} / {d['naive_rate']:.3f} / {d['edge']['point'] * 100:+.2f}")
    b = ev["baseline_0_1_0_same_rows"]
    L += ["", f"Baseline scoring 0.1.0 on the same rows: acted={b['acted_share']:.2f} acc={b['acted_accuracy']:.3f} edge={b['edge'] * 100:+.2f}%", ""]
    if "coefficients_last_fold_training" in res:
        L += ["Coefficients (standardised features, last fold's training range; sign agreement across folds):", ""]
        agree = res.get("coefficient_sign_agreement", {})
        for k, v in sorted(res["coefficients_last_fold_training"].items(), key=lambda kv: -abs(kv[1])):
            L.append(f"- {k}: {v:+.4f}  (same sign in {agree.get(k, float('nan')):.0%} of folds)")
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
    parser.add_argument("--features", default="", help="comma-separated explicit feature list (overrides --groups)")
    parser.add_argument("--tag", default="", help="output file stem (default: model_scheme_horizon)")
    parser.add_argument("--target", default="direction", choices=["direction", "large_move"])
    parser.add_argument("--threshold", type=float, default=None, help="large_move: |return| threshold as a fraction, e.g. 0.005")
    parser.add_argument("--log-features", default="", help="comma-separated inputs to log-transform before standardising")
    parser.add_argument("--calibrator", default="none", choices=list(CALIBRATORS), help="re-map probabilities on the purged calibration slice")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    groups = [g for g in args.groups.split(",") if g]
    features = [f for f in args.features.split(",") if f] or None
    log_features = [f for f in args.log_features.split(",") if f] or None
    path = run(args.experiment, args.model, args.horizon, groups, args.scheme, args.calib_days, args.C, features, args.tag or None,
               args.target, args.threshold, log_features, args.calibrator)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(path.read_text(encoding="utf-8"))
