"""E028: the variant's columns, the pre-registered judgement, and isolation from the live system. Synthetic only."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from agent.research import second_harmonic as sh


def test_the_second_harmonic_has_twice_the_daily_frequency():
    idx = pd.DatetimeIndex([datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=h) for h in range(24)])
    out = sh.add_second_harmonic(pd.DataFrame(index=idx))
    assert np.allclose(out["hour_sin2"].to_numpy()[:12], out["hour_sin2"].to_numpy()[12:])  # period 12 hours
    assert np.isclose(out["hour_cos2"].iloc[0], 1.0) and np.isclose(out["hour_cos2"].iloc[3], 0.0, atol=1e-12)


def _blocks(offsets):
    return {n: {"stated_minus_observed": o} for n, o in zip(("00-06", "06-12", "12-18", "18-24"), offsets)}


def test_the_judgement_applies_the_registered_rules():
    inc = {"exploration": _blocks([0.05, 0.0, -0.02, -0.02]), "validation": _blocks([0.02, 0.0, -0.06, 0.01])}
    good = {"exploration": _blocks([0.02, 0.0, -0.01, 0.01]), "validation": _blocks([0.01, 0.0, -0.03, 0.0])}
    v = sh.judge(inc, good, {"ci_high": 0.001}, {"exploration": 0.01, "validation": 0.02})
    assert v == {"H_a_mechanism": True, "H_b_no_loss": True, "H_c_calibration": True}
    half_only_in_one = {"exploration": good["exploration"], "validation": _blocks([0.01, 0.0, -0.04, 0.0])}
    assert not sh.judge(inc, half_only_in_one, {"ci_high": 0.001}, {"exploration": 0.01, "validation": 0.02})["H_a_mechanism"]
    assert not sh.judge(inc, good, {"ci_high": -0.0001}, {"exploration": 0.01, "validation": 0.02})["H_b_no_loss"]
    assert not sh.judge(inc, good, {"ci_high": 0.001}, {"exploration": 0.01, "validation": 0.031})["H_c_calibration"]


def test_the_variant_never_reaches_the_live_system():
    """Research-only: no live module may know the variant's columns or import this module."""
    for path in [*Path("agent/shadow").glob("*.py"), Path("agent/orchestrator.py"), *Path("agent/scoring").glob("*.py")]:
        src = path.read_text(encoding="utf-8")
        assert "hour_sin2" not in src and "second_harmonic" not in src, path
