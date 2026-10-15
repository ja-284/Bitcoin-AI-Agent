"""
The frozen direction artefact: load a versioned JSON file and evaluate it with numpy only.

It is produced once by agent/research/export_direction_model.py and never edited (research/DIRECTION_TRACK.md,
section 3). It holds three probabilities of UP over the next hour, all computed on the same inputs:
  p_model        E032's eight-input L2 logistic (standardised inputs, no calibration layer)
  p_one_feature  the same logistic on taker_buy_share_1h alone
  p_base         a constant, the share of UP hours in the fitting rows
"""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from agent.shadow.model import ModelVersionError, compare_reference_values

MODEL_DIR = Path(__file__).parent / "models"
DEFAULT_VERSION = "direction_1h_v1"


def canonical_sha256(text: str) -> str:
    """sha256 of the artefact's canonical JSON, so line endings and key order do not matter."""
    return hashlib.sha256(json.dumps(json.loads(text), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _logistic(x: np.ndarray, mean: np.ndarray, scale: np.ndarray, coef: np.ndarray, intercept: float) -> float:
    z = float(np.dot(coef, (x - mean) / scale) + intercept)
    return 1.0 / (1.0 + math.exp(-z))


@dataclass(frozen=True)
class DirectionModel:
    version: str
    horizon_hours: int
    features: tuple[str, ...]
    scaler_mean: np.ndarray
    scaler_scale: np.ndarray
    coef: np.ndarray
    intercept: float
    one_feature: str
    one_mean: float
    one_scale: float
    one_coef: float
    one_intercept: float
    base_rate: float
    scoring_version: str
    sha256: str
    training: dict
    provenance: dict

    def predict(self, row: dict) -> tuple[float, float, float] | None:
        """(p_model, p_one_feature, p_base) for one hour's raw inputs, or None if any input is missing."""
        x = []
        for name in self.features:
            v = row.get(name)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return None
            x.append(float(v))
        x = np.asarray(x)
        p_model = _logistic(x, self.scaler_mean, self.scaler_scale, self.coef, self.intercept)
        one = x[self.features.index(self.one_feature)]
        p_one = _logistic(np.array([one]), np.array([self.one_mean]), np.array([self.one_scale]), np.array([self.one_coef]), self.one_intercept)
        return p_model, p_one, self.base_rate


def load_model(version: str = DEFAULT_VERSION, verify_features: bool = True) -> DirectionModel:
    path = MODEL_DIR / f"{version}.json"
    text = path.read_text(encoding="utf-8")
    d = json.loads(text)
    if d["version"] != version:
        raise ValueError(f"artefact {path} declares version {d['version']!r}, expected {version!r}")
    n = len(d["features"])
    if not (len(d["scaler_mean"]) == len(d["scaler_scale"]) == len(d["coef"]) == n) or d["one_feature"] not in d["features"]:
        raise ValueError(f"artefact {path} is inconsistent")
    if not 0.0 < float(d["base_rate"]) < 1.0:
        raise ValueError(f"artefact {path}: base rate {d['base_rate']} is not a probability")
    if verify_features:
        from agent.direction_shadow.features import reference_values  # local import: pulls in pandas and the scoring code

        stored = d.get("feature_reference")
        if not stored:
            raise ModelVersionError(f"artefact {version} carries no feature reference values; refusing to run it blind")
        problems = compare_reference_values(stored, reference_values())
        if problems:
            raise ModelVersionError(
                f"input definitions changed since {version} was fitted: " + "; ".join(problems[:4])
                + " -- export a new model version instead of running old coefficients on new inputs"
            )
    return DirectionModel(
        version=d["version"], horizon_hours=int(d["horizon_hours"]), features=tuple(d["features"]),
        scaler_mean=np.asarray(d["scaler_mean"], float), scaler_scale=np.asarray(d["scaler_scale"], float),
        coef=np.asarray(d["coef"], float), intercept=float(d["intercept"]),
        one_feature=d["one_feature"], one_mean=float(d["one_mean"]), one_scale=float(d["one_scale"]),
        one_coef=float(d["one_coef"]), one_intercept=float(d["one_intercept"]), base_rate=float(d["base_rate"]),
        scoring_version=d["scoring_version"], sha256=canonical_sha256(text),
        training=d.get("training", {}), provenance=d.get("provenance", {}),
    )
