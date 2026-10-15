"""
Freeze E032's direction model and its two references into the JSON artefact the prospective direction track runs
(E034, research/DIRECTION_TRACK.md, section 3). Numpy-only inference, every number visible in git.

    python -m agent.research.export_direction_model --version direction_1h_v1

What goes in: E032's eight inputs' standardisation and logistic coefficients (C = 0.1, no calibration layer); the
same logistic on taker_buy_share_1h alone; the base rate (the share of UP hours in the fitting rows); the scoring
version the category scores came from; every input's values on the fixed synthetic series (the definition guard);
and the exact fitting range, row count and a fingerprint of the labels, enough to re-fit and get the same numbers.

Boundaries: E032's rows (development only: build_frame -> load_bars(end=HOLDOUT.start)), all of them before
HOLDOUT.start - (1h + 24h), the purge the move-size export used. No calibration slice. Nothing from the holdout, the
buffer or the live period.
"""

import argparse
import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.direction_shadow.features import INPUTS, ONE_FEATURE, reference_values
from agent.research.model_test import LogisticModel, build_frame
from agent.research.periods import HOLDOUT
from agent.scoring.scorer import SCORING_VERSION

logger = logging.getLogger(__name__)

ARTEFACT_DIR = Path("agent") / "direction_shadow" / "models"
HORIZON = 1
C = 0.1
EMBARGO = 24
REGISTERED_SCORING_VERSION = "0.2.0"  # the replay that produced E032's category scores


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _parts(model: LogisticModel) -> tuple[list[float], list[float], list[float], float]:
    scaler, lr = model.pipe.steps[0][1], model.pipe.steps[1][1]
    return scaler.mean_.tolist(), scaler.scale_.tolist(), lr.coef_[0].tolist(), float(lr.intercept_[0])


def fit(version: str) -> dict:
    if SCORING_VERSION != REGISTERED_SCORING_VERSION:
        raise RuntimeError(f"scoring {SCORING_VERSION} is running, but the registration names {REGISTERED_SCORING_VERSION}")
    df, _ = build_frame(HORIZON, [], list(INPUTS), "direction")  # load_bars(end=HOLDOUT.start) inside
    usable = df[list(INPUTS) + ["y"]].dropna()  # E032's rows
    purge = pd.Timedelta(hours=HORIZON + EMBARGO)
    fit_end = pd.Timestamp(HOLDOUT.start) - purge
    train = usable[usable.index < fit_end]
    if train.index.max() >= fit_end or train.index.max() + pd.Timedelta(hours=HORIZON + 1) >= pd.Timestamp(HOLDOUT.start):
        raise RuntimeError("boundary violation while fitting the direction artefact")
    y = train["y"].to_numpy(dtype=float)

    model = LogisticModel(C=C)
    model.fit(train[list(INPUTS)], y)
    one = LogisticModel(C=C)
    one.fit(train[[ONE_FEATURE]], y)
    mean, scale, coef, intercept = _parts(model)
    o_mean, o_scale, o_coef, o_intercept = _parts(one)
    base = float(y.mean())

    # the numpy inference the live step runs must reproduce scikit-learn on every fitting row
    X = train[list(INPUTS)].to_numpy(float)
    p_np = 1 / (1 + np.exp(-(((X - np.array(mean)) / np.array(scale)) @ np.array(coef) + intercept)))
    o = train[ONE_FEATURE].to_numpy(float)
    o_np = 1 / (1 + np.exp(-(((o - o_mean[0]) / o_scale[0]) * o_coef[0] + o_intercept)))
    p_sk, o_sk = model.predict_proba(train[list(INPUTS)]), one.predict_proba(train[[ONE_FEATURE]])
    diff = float(max(np.max(np.abs(p_np - p_sk)), np.max(np.abs(o_np - o_sk))))
    if diff > 1e-12:
        raise RuntimeError(f"numpy inference differs from scikit-learn by {diff}")

    import sklearn

    brier = lambda p: float(np.mean((p - y) ** 2))  # noqa: E731
    return {
        "version": version,
        "kind": "direction_logistic_with_references",
        "description": "P(the next 1h candle closes above the reference close). M = E032's eight-input L2 logistic; "
                       "F = the same on taker_buy_share_1h alone; B = the fitting rows' UP share. Research only (E034).",
        "horizon_hours": HORIZON,
        "features": list(INPUTS),
        "scaler_mean": mean, "scaler_scale": scale, "coef": coef, "intercept": intercept,
        "one_feature": ONE_FEATURE,
        "one_mean": o_mean[0], "one_scale": o_scale[0], "one_coef": o_coef[0], "one_intercept": o_intercept,
        "base_rate": base,
        "scoring_version": SCORING_VERSION,
        "feature_reference": reference_values(),  # identifies the input DEFINITIONS; re-checked at load time
        "training": {
            "fit_rows": int(len(train)), "fit_range": [str(train.index.min()), str(train.index.max())],
            "purge_hours": int(purge / pd.Timedelta(hours=1)), "C": C, "calibration": "none (E032's design)",
            "up_share": base,
            "in_sample_brier": {"model": brier(p_sk), "one_feature": brier(o_sk), "base_rate": brier(np.full(len(y), base))},
            "numpy_vs_sklearn_max_abs_diff": diff,
            "label_fingerprint_sha256_16": hashlib.sha256(train["y"].to_numpy(dtype=np.int8).tobytes()).hexdigest()[:16],
            "snapshot": df.attrs.get("snapshot"), "holdout_start_never_crossed": str(HOLDOUT.start),
        },
        "provenance": {"experiments": ["E032", "E034"], "protocol": "research/DIRECTION_TRACK.md v1.0",
                       "created_at": datetime.now(timezone.utc).isoformat(), "git_commit": _git_commit(), "sklearn": sklearn.__version__},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    path = ARTEFACT_DIR / f"{args.version}.json"
    if path.exists():
        raise SystemExit(f"{path} exists -- a model version is immutable; choose a new version name")
    art = fit(args.version)
    ARTEFACT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art, indent=2), encoding="utf-8")
    t = art["training"]
    print(f"wrote {path}: fit {t['fit_rows']} rows {t['fit_range'][0]} -> {t['fit_range'][1]}, UP share {art['base_rate']:.4f}, "
          f"in-sample Brier M {t['in_sample_brier']['model']:.5f} F {t['in_sample_brier']['one_feature']:.5f} B {t['in_sample_brier']['base_rate']:.5f}")
