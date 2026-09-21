"""
Frozen move-size model: load a versioned JSON artefact and evaluate it with numpy only.

The artefact is produced once by agent/research/export_move_size_model.py and never edited.
Inference reproduces the research pipeline exactly: log-transform the declared inputs,
standardise with the stored mean/scale, logistic regression, then Platt scaling on the
(clipped) logit -- the same clip the research calibrator used.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_DIR = Path(__file__).parent / "models"
DEFAULT_VERSION = "move_size_1h_v1"


@dataclass(frozen=True)
class MoveSizeModel:
    version: str
    horizon_hours: int
    threshold: float
    features: tuple[str, ...]
    log_features: tuple[str, ...]
    scaler_mean: np.ndarray
    scaler_scale: np.ndarray
    coef: np.ndarray
    intercept: float
    platt_a: float
    platt_b: float
    logit_clip: float
    training: dict
    provenance: dict

    def transform(self, row: dict) -> np.ndarray | None:
        """Raw feature values -> standardised vector, or None if any input is missing/non-positive where a log is needed."""
        x = []
        for name in self.features:
            v = row.get(name)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return None
            v = float(v)
            if name in self.log_features:
                if v <= 0:
                    return None  # a ratio of exactly 0 (no trades) is not a real observation -- research rule
                v = math.log(v)
            x.append(v)
        return (np.asarray(x) - self.scaler_mean) / self.scaler_scale

    def predict(self, row: dict) -> tuple[float, float] | None:
        """(raw probability, calibrated probability) for one hour's raw feature values, or None if unavailable."""
        x = self.transform(row)
        if x is None:
            return None
        z = float(np.dot(self.coef, x) + self.intercept)
        p_raw = 1.0 / (1.0 + math.exp(-z))
        p_c = min(max(p_raw, self.logit_clip), 1 - self.logit_clip)
        logit = math.log(p_c / (1 - p_c))
        p_cal = 1.0 / (1.0 + math.exp(-(self.platt_a * logit + self.platt_b)))
        return p_raw, p_cal


class ModelVersionError(RuntimeError):
    """The artefact and the running code disagree about what the features mean."""


def load_model(version: str = DEFAULT_VERSION, verify_features: bool = True) -> MoveSizeModel:
    path = MODEL_DIR / f"{version}.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    if d["version"] != version:
        raise ValueError(f"artefact {path} declares version {d['version']!r}, expected {version!r}")
    n = len(d["features"])
    if not (len(d["scaler_mean"]) == len(d["scaler_scale"]) == len(d["coef"]) == n):
        raise ValueError(f"artefact {path} is inconsistent (feature count {n})")
    if verify_features:
        from agent.shadow.features import feature_fingerprint  # local import: features pulls in pandas

        expected = d.get("feature_fingerprint")
        if not expected:
            raise ModelVersionError(f"artefact {version} carries no feature fingerprint; refusing to run it blind")
        current = feature_fingerprint(d["features"])
        if current != expected:
            raise ModelVersionError(
                f"feature definitions changed since {version} was fitted (fingerprint {current[:12]} != {expected[:12]}); "
                "export a new model version instead of running old coefficients on new features"
            )
    return MoveSizeModel(
        version=d["version"], horizon_hours=int(d["horizon_hours"]), threshold=float(d["threshold"]),
        features=tuple(d["features"]), log_features=tuple(d["log_features"]),
        scaler_mean=np.asarray(d["scaler_mean"], float), scaler_scale=np.asarray(d["scaler_scale"], float),
        coef=np.asarray(d["coef"], float), intercept=float(d["intercept"]),
        platt_a=float(d["platt_a"]), platt_b=float(d["platt_b"]), logit_clip=float(d.get("logit_clip", 1e-6)),
        training=d.get("training", {}), provenance=d.get("provenance", {}),
    )
