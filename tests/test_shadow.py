"""
The shadow record is live code, so it is held to the live standard:

- numpy inference from the frozen artefact equals the research sklearn pipeline + Platt exactly;
- features computed from a 250-candle window equal the research full-series features at the
  same hour (live = research parity for this model);
- a gap inside the window, or a zero-trade candle, yields 'unavailable', never a number;
- the stored row carries what is needed to recompute p, and the cutoff rule holds;
- the committed artefact loads, is internally consistent, and its boundaries never cross the holdout;
- grading uses the tracker's target rule and stores a fraction.
"""

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent.research.features import all_features, bars_to_frame
from agent.research.microstructure import microstructure_features
from agent.research.periods import HOLDOUT
from agent.shadow.features import WINDOW_HOURS, extras_frame, feature_row
from agent.shadow.model import DEFAULT_VERSION, MoveSizeModel, load_model
from agent.shadow.outcomes import grade
from agent.shadow.run import compute
from agent.shared.types import PriceBar

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def _bars(n: int, seed: int = 0, start: datetime = START):
    rng = np.random.default_rng(seed)
    close = 60000 * np.exp(np.cumsum(rng.normal(0, 0.004, size=n)))
    bars, extras = [], []
    for i in range(n):
        c = float(close[i])
        o = float(close[i - 1]) if i else c
        hi, lo = max(o, c) * (1 + abs(rng.normal(0, 0.001))), min(o, c) * (1 - abs(rng.normal(0, 0.001)))
        vol = float(abs(rng.normal(100, 20)))
        t = start + i * HOUR
        bars.append(PriceBar(t, o, hi, lo, c, vol, "binance"))
        extras.append((t, vol, int(abs(rng.normal(5000, 800))), vol * float(rng.uniform(0.3, 0.7))))
    return bars, extras


def _sklearn_reference(model: MoveSizeModel, row: dict) -> float:
    """Rebuild the research pipeline from the artefact's numbers with sklearn objects and score the same row."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    sc = StandardScaler()
    sc.mean_, sc.scale_, sc.var_, sc.n_features_in_ = model.scaler_mean, model.scaler_scale, model.scaler_scale**2, len(model.features)
    lr = LogisticRegression()
    lr.coef_, lr.intercept_, lr.classes_ = model.coef.reshape(1, -1), np.array([model.intercept]), np.array([0.0, 1.0])
    x = np.array([[math.log(row[f]) if f in model.log_features else row[f] for f in model.features]])
    p_raw = lr.predict_proba(sc.transform(x))[0, 1]
    p_c = np.clip(p_raw, model.logit_clip, 1 - model.logit_clip)
    return 1 / (1 + math.exp(-(model.platt_a * math.log(p_c / (1 - p_c)) + model.platt_b)))


def test_artefact_loads_and_never_crossed_the_holdout():
    m = load_model(DEFAULT_VERSION)
    assert m.version == DEFAULT_VERSION and m.horizon_hours == 1 and m.threshold == 0.0025
    assert len(m.features) == 9 and len(m.coef) == 9
    calib_last = pd.Timestamp(m.training["calib_range"][1])
    assert calib_last + pd.Timedelta(hours=m.training["purge_hours"]) < pd.Timestamp(HOLDOUT.start)
    assert pd.Timestamp(m.training["fit_range"][1]) < pd.Timestamp(m.training["calib_range"][0])
    raw = json.loads((Path("agent/shadow/models") / f"{DEFAULT_VERSION}.json").read_text(encoding="utf-8"))
    assert raw["provenance"]["experiments"] == ["E012", "E013"]


def test_numpy_inference_matches_sklearn_pipeline():
    m = load_model(DEFAULT_VERSION)
    rng = np.random.default_rng(4)
    for _ in range(50):
        row = {"tr_mean_14_rel": float(rng.uniform(0.001, 0.03)), "rv_24": float(rng.uniform(0.001, 0.03)), "rv_168": float(rng.uniform(0.002, 0.02)),
               "vol_ratio_24_168": float(rng.uniform(0.3, 3)), "trades_rel_24h": float(rng.uniform(0.2, 4)), "trades_rel_168h": float(rng.uniform(0.2, 4)),
               "hour_sin": float(rng.uniform(-1, 1)), "hour_cos": float(rng.uniform(-1, 1)), "is_weekend": float(rng.integers(0, 2))}
        p_raw, p_cal = m.predict(row)
        assert 0 < p_raw < 1 and 0 < p_cal < 1
        assert p_cal == pytest.approx(_sklearn_reference(m, row), abs=1e-12)


def test_model_refuses_missing_or_nonpositive_inputs():
    m = load_model(DEFAULT_VERSION)
    good = {f: 0.5 for f in m.features}
    assert m.predict(good) is not None
    assert m.predict({**good, "rv_24": float("nan")}) is None
    assert m.predict({**good, "trades_rel_24h": 0.0}) is None  # a zero-trade candle is not an observation
    assert m.predict({k: v for k, v in good.items() if k != "hour_sin"}) is None


def test_window_features_equal_full_series_features():
    """Live = research for this model: the last row of a 250-candle window equals the full-series value."""
    bars, extras = _bars(2000, seed=1)
    m = load_model(DEFAULT_VERSION)
    full = pd.concat([all_features(bars), microstructure_features(bars_to_frame(bars).index, extras_frame(extras))], axis=1)
    for end in (400, 1234, 2000):
        window_bars, window_extras = bars[end - WINDOW_HOURS:end], extras[end - WINDOW_HOURS:end]
        values, reason = feature_row(window_bars, extras_frame(window_extras), m.features)
        assert reason is None
        ref = pd.Timestamp(window_bars[-1].as_of)
        for f in m.features:
            assert values[f] == pytest.approx(float(full.loc[ref, f]), rel=1e-12, abs=1e-15), f


def test_gap_inside_window_makes_the_hour_unavailable():
    bars, extras = _bars(WINDOW_HOURS + 10, seed=2)
    m = load_model(DEFAULT_VERSION)
    # a gap 100 hours before the reference hour sits inside the 168h windows -> those inputs are blank
    del bars[-100]
    del extras[-100]
    row = compute(m, bars, extras, bars[-1].as_of + HOUR + timedelta(minutes=12))
    assert row["status"] == "unavailable" and "rv_168" in row["status_reason"] and "gap" in row["status_reason"]
    assert row["p_calibrated"] is None and row["p_raw"] is None


def test_compute_row_is_reproducible_and_respects_the_cutoff():
    bars, extras = _bars(WINDOW_HOURS, seed=3)
    m = load_model(DEFAULT_VERSION)
    fetched = bars[-1].as_of + HOUR + timedelta(minutes=12)
    row = compute(m, bars, extras, fetched)
    assert row["status"] == "ok" and row["cutoff_at"] == row["as_of"] + HOUR and row["fetched_at"] >= row["cutoff_at"]
    assert row["reference_close"] == bars[-1].close and row["model_version"] == DEFAULT_VERSION and row["threshold"] == 0.0025
    # the stored raw features alone reproduce p exactly
    assert m.predict(row["features"]) == (row["p_raw"], row["p_calibrated"])
    with pytest.raises(RuntimeError, match="before the reference candle closed"):
        compute(m, bars, extras, bars[-1].as_of + timedelta(minutes=30))


def test_grade_stores_a_fraction_and_applies_the_threshold():
    ret, large = grade(100.0, 100.3, 0.0025)
    assert ret == pytest.approx(0.003) and large is True
    ret, large = grade(100.0, 99.8, 0.0025)
    assert ret == pytest.approx(-0.002) and large is False


# A model version is immutable. Any edit to the artefact must come with a new version name
# AND a deliberate update of this pin -- both visible in git. (Backend Phase E/G)
ARTEFACT_SHA256 = {"move_size_1h_v1": "8a80d203917c6fbaf8c18f6576cb470cf7147a3c398da711a6b4a84f006d703f"}  # of the canonical JSON (line endings do not matter)


def test_frozen_artefacts_are_unchanged():
    import hashlib

    for version, expected in ARTEFACT_SHA256.items():
        text = (Path("agent/shadow/models") / f"{version}.json").read_text(encoding="utf-8")
        digest = hashlib.sha256(json.dumps(json.loads(text), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert digest == expected, f"{version} was edited in place -- create a new version instead"
