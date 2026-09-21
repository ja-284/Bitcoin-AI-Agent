"""
Freeze the research move-size model (E012 features, E013 Platt calibration) into a plain
JSON artefact that the live SHADOW job can evaluate with numpy alone -- no scikit-learn at
run time, no hidden state, every number visible in git.

    python -m agent.research.export_move_size_model --version move_size_1h_v1

What goes in: the six log-transformed + three calendar inputs' standardisation (mean, scale),
the logistic coefficients and intercept, the Platt (a, b), the threshold and horizon, the
exact training/calibration ranges and row counts, data snapshot names, and a fingerprint of
the labels -- enough to re-fit and get the same numbers.

Boundaries (the same as E013's last fold before the sealed holdout):
    fit rows      < calibration start - purge
    calibration   the 90 days ending at holdout start - purge
    purge         = horizon + 24h embargo
Nothing from the holdout, the buffer or the live period is used.
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

from agent.research.model_test import LogisticModel, PlattCalibrator, build_frame
from agent.research.periods import HOLDOUT
from agent.research.walkforward import WalkForwardSpec
from agent.shadow.features import feature_fingerprint

logger = logging.getLogger(__name__)

ARTEFACT_DIR = Path("agent") / "shadow" / "models"

FEATURES = ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168", "trades_rel_24h", "trades_rel_168h", "hour_sin", "hour_cos", "is_weekend"]
LOG_FEATURES = ["tr_mean_14_rel", "rv_24", "rv_168", "vol_ratio_24_168", "trades_rel_24h", "trades_rel_168h"]
THRESHOLD = 0.0025
HORIZON = 1
C = 0.1
CALIB_DAYS = 90
EMBARGO = 24


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def fit(version: str) -> dict:
    df, cols = build_frame(HORIZON, [], FEATURES, "large_move", THRESHOLD)
    assert cols == FEATURES
    for c in LOG_FEATURES:
        df[c] = np.log(df[c].where(df[c] > 0))
    spec = WalkForwardSpec(horizon_hours=HORIZON, calib_days=CALIB_DAYS, embargo_hours=EMBARGO)
    usable = df[FEATURES + ["y"]].dropna()
    calib_end = pd.Timestamp(HOLDOUT.start) - spec.purge
    calib_start = calib_end - pd.Timedelta(days=CALIB_DAYS)
    fit_end = calib_start - spec.purge
    train = usable[usable.index < fit_end]
    calib = usable[(usable.index >= calib_start) & (usable.index < calib_end)]
    if train.index.max() >= fit_end or calib.index.max() >= calib_end or calib.index.max() + spec.purge >= pd.Timestamp(HOLDOUT.start):
        raise RuntimeError("boundary violation while fitting the export model")

    model = LogisticModel(C=C)
    model.fit(train[FEATURES], train["y"].to_numpy(dtype=float))
    cal = PlattCalibrator()
    cal.fit(model.predict_proba(calib[FEATURES]), calib["y"].to_numpy(dtype=float))
    scaler, lr = model.pipe.steps[0][1], model.pipe.steps[1][1]

    import sklearn

    fingerprint = hashlib.sha256(train["y"].to_numpy(dtype=np.int8).tobytes() + calib["y"].to_numpy(dtype=np.int8).tobytes()).hexdigest()[:16]
    return {
        "version": version,
        "kind": "move_size_logistic_platt",
        "description": "P(|return over the next 1h| > 0.25%) -- E012 model, E013 Platt calibration. Uncertainty only; says nothing about direction.",
        "horizon_hours": HORIZON,
        "threshold": THRESHOLD,
        "features": FEATURES,
        "log_features": LOG_FEATURES,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": lr.coef_[0].tolist(),
        "intercept": float(lr.intercept_[0]),
        "platt_a": cal.params()["a"],
        "platt_b": cal.params()["b"],
        "logit_clip": 1e-6,
        "feature_fingerprint": feature_fingerprint(FEATURES),  # identifies the feature DEFINITIONS; checked at load time
        "training": {
            "fit_rows": int(len(train)), "fit_range": [str(train.index.min()), str(train.index.max())],
            "calib_rows": int(len(calib)), "calib_range": [str(calib.index.min()), str(calib.index.max())],
            "purge_hours": int(spec.purge / pd.Timedelta(hours=1)), "C": C, "label_fingerprint_sha256_16": fingerprint,
            "snapshot": df.attrs.get("snapshot"), "holdout_start_never_crossed": str(HOLDOUT.start),
        },
        "provenance": {"experiments": ["E012", "E013"], "created_at": datetime.now(timezone.utc).isoformat(), "git_commit": _git_commit(), "sklearn": sklearn.__version__},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    art = fit(args.version)
    ARTEFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTEFACT_DIR / f"{args.version}.json"
    if path.exists():
        raise SystemExit(f"{path} exists -- a model version is immutable; choose a new version name")
    path.write_text(json.dumps(art, indent=2), encoding="utf-8")
    print(f"wrote {path}: fit {art['training']['fit_rows']} rows to {art['training']['fit_range'][1]}, calib {art['training']['calib_rows']} rows, platt a={art['platt_a']:.4f} b={art['platt_b']:.4f}")
