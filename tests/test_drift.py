"""Backend Phase I: drift flags fire on real shifts, stay quiet on development-like data, and never fire on tiny samples."""

from datetime import datetime, timedelta, timezone

import numpy as np

from agent.research.drift import MIN_ROWS, feature_drift, load_reference, missing_and_timing, outcome_drift, probability_drift, report

REF = load_reference()
T0 = datetime(2026, 9, 21, tzinfo=timezone.utc)


def _dev_like(name: str, n: int, rng) -> list[float]:
    """Sample from the development quantiles by linear interpolation of the reference CDF."""
    q = REF["features"][name]["q"]
    Q = REF["quantiles"]
    u = rng.uniform(0.01, 0.99, size=n)
    return list(np.interp(u, Q, q))


def test_development_like_values_are_ok_and_shifted_values_flag():
    rng = np.random.default_rng(0)
    live = {name: _dev_like(name, 500, rng) for name in REF["features"]}
    fd = feature_drift(live, REF)
    assert all(v["status"] == "ok" for v in fd.values()), {k: v["status"] for k, v in fd.items()}
    shifted = dict(live)
    shifted["rv_24"] = [v * 4 for v in live["rv_24"]]  # a four-fold volatility regime
    fd = feature_drift(shifted, REF)
    assert fd["rv_24"]["status"] == "FLAG" and fd["rv_24"]["share_outside_dev_1_99"] > 0.1


def test_small_samples_never_flag():
    rng = np.random.default_rng(1)
    live = {name: [v * 10 for v in _dev_like(name, MIN_ROWS - 1, rng)] for name in REF["features"]}
    assert all(v["status"] == "too few rows to flag" for v in feature_drift(live, REF).values())
    assert probability_drift([0.99] * 10, REF)["status"] == "too few rows to flag"
    assert outcome_drift([True] * 10, REF)["status"] == "too few rows to flag"


def test_probability_and_outcome_drift():
    q = REF["p_calibrated"]["q"]
    rng = np.random.default_rng(2)
    p_ok = list(np.interp(rng.uniform(0.01, 0.99, 400), REF["quantiles"], q))
    assert probability_drift(p_ok, REF)["status"] == "ok"
    assert probability_drift([0.95] * 400, REF)["status"] == "FLAG"
    share = REF["large_move_share"]["validation_2024_2025H1"]
    y_ok = list(rng.uniform(size=400) < share)
    assert outcome_drift(y_ok, REF)["status"] == "ok"
    assert outcome_drift([True] * 400, REF)["status"] == "FLAG"


def test_missing_and_timing_and_full_report():
    rows = []
    for i in range(300):
        rows.append({"as_of": T0 + timedelta(hours=i), "fetched_at": T0 + timedelta(hours=i + 1, minutes=12), "status": "unavailable" if i % 10 == 0 else "ok",
                     "features": {k: v for k, v in zip(REF["features"], [0.008, 0.005, 0.006, 1.0, 1.0, 1.0, 0.0, 1.0, 0.0])}, "p_calibrated": 0.5,
                     "outcome_status": "ok", "outcome_large": bool(i % 2)})
    mt = missing_and_timing(rows, rows)
    assert mt["status"] == "FLAG" and abs(mt["shadow_unavailable_share"] - 0.1) < 1e-9  # 10% blanks is worth a look
    rep = report(rows, rows, REF)
    assert "missing_and_timing" in rep["flags"] and "note" in rep
