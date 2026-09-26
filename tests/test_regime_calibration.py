"""
E026 (agent/research/regime_calibration.py): the regime split uses the checkpoint's own rule, and the
per-regime calibration table recognises a calibrated forecaster and an over-predicting one. Synthetic only.
"""

import numpy as np

from agent.research import live_checkpoint as lc
from agent.research import regime_calibration as rc


def test_the_regime_rule_is_the_checkpoints():
    cuts = (0.004759, 0.006966)
    values = np.array([0.001, 0.004759, 0.0069, 0.006966, 0.02])
    names = [rc.REGIMES[k] for k in rc.assign(values, cuts)]
    assert names == [lc.regime_of({"features": {"rv_168": v}}, cuts) for v in values]


def _world(n, over_in_low, seed=0):
    rng = np.random.default_rng(seed)
    regime = rng.integers(0, 3, size=n)
    p = rng.uniform(0.2, 0.7, size=n)
    truth = np.where(regime == 0, np.clip(p - over_in_low, 0, 1), p)   # the forecaster over-states in the low regime
    y = (rng.uniform(size=n) < truth).astype(float)
    return p, y, regime


def test_a_calibrated_forecaster_passes_in_every_regime():
    t = rc.regime_table(*_world(6000, over_in_low=0.0))
    assert all(t[r]["H_holds"] for r in rc.REGIMES), t


def test_over_prediction_in_the_calm_regime_is_detected_there_and_only_there():
    t = rc.regime_table(*_world(6000, over_in_low=0.10))
    assert not t["low"]["H_holds"] and t["low"]["stated_minus_observed"] > 0.05
    assert t["mid"]["H_holds"] and t["high"]["H_holds"]
    assert t["low"]["ci95"][0] > 0, "the interval must exclude zero for a clear offset"


def test_the_study_reads_no_prospective_outcome_and_no_holdout():
    from pathlib import Path

    src = Path("agent/research/regime_calibration.py").read_text(encoding="utf-8")
    for forbidden in ("allow_holdout", "shadow_move_size", "prediction_outcomes", "fetch_shadow_rows"):
        assert forbidden not in src, forbidden
