"""
Guards born from a real mistake (E004, first run): a feature named like the harness's
forward-return column got overwritten by it, producing a perfect "correlation" with the
future. Two independent defences: names are checked up front, and any result too good
to be true stops the run.
"""

import numpy as np
import pandas as pd
import pytest

from agent.research.feature_test import SuspiciousResultError, TRIPWIRE_RHO, check_feature_names
from agent.research.features import REGIME_FEATURES, RESERVED_PREFIXES, VOLATILITY_FEATURES, all_features
from agent.research.labels import forward_returns
from tests.test_point_in_time import synthetic_bars


def test_no_shipped_feature_uses_a_reserved_target_prefix():
    for name in VOLATILITY_FEATURES + REGIME_FEATURES:
        assert not name.startswith(RESERVED_PREFIXES), name


def test_harness_refuses_reserved_or_colliding_names():
    with pytest.raises(ValueError, match="reserved"):
        check_feature_names(["ret_168h"], pd.Index(["close"]))
    with pytest.raises(ValueError, match="reserved"):
        check_feature_names(["fwd_24h"], pd.Index(["close"]))
    with pytest.raises(ValueError, match="collides"):
        check_feature_names(["close"], pd.Index(["close", "signal"]))
    check_feature_names(["trail_ret_168h", "rv_24"], pd.Index(["close", "signal"]))  # fine


def test_trailing_return_is_not_the_forward_return():
    bars = synthetic_bars(2000)
    feats = all_features(bars)
    fwd = forward_returns(bars, 168)
    trailing = feats["trail_ret_168h"].reindex(fwd.index)
    both = pd.concat([trailing, fwd], axis=1).dropna()
    rho = both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())
    assert abs(rho) < TRIPWIRE_RHO  # on a noisy synthetic series these must not be near-identical
    # And the trailing return at t equals the forward return at t-168h (same window, seen from both ends).
    shifted = fwd.shift(168, freq="h")
    aligned = pd.concat([trailing, shifted], axis=1).dropna()
    assert np.allclose(aligned.iloc[:, 0], aligned.iloc[:, 1])


def test_tripwire_is_a_hard_error():
    assert issubclass(SuspiciousResultError, RuntimeError)
    assert 0 < TRIPWIRE_RHO < 1
