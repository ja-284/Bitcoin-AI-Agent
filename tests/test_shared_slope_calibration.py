"""E035: the shared-slope block calibrator, its fallback, and isolation. Synthetic only (no real outcome)."""

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from agent.research import block_calibration as bc
from agent.research import shared_slope_calibration as ss
from agent.research.model_test import PlattCalibrator, _logit


def _slice(n=8000, slope=0.9, intercepts=(-0.3, 0.1, 0.4, 0.2), seed=1):
    rng = np.random.default_rng(seed)
    hours = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    p = rng.uniform(0.05, 0.95, n)
    block = ((hours.hour // 6)).to_numpy()
    z = slope * _logit(p) + np.array(intercepts)[block]
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-z))).astype(float)
    return p, y, hours


def test_it_recovers_one_shared_slope_and_four_block_intercepts():
    p, y, hours = _slice()
    c = ss.SharedSlopeBlockCalibrator().fit(p, y, hours)
    params = c.params()
    assert len(params) == 5, "one slope + four intercepts, nothing else"
    assert params["slope"] == pytest.approx(0.9, abs=0.08)
    for name, want in zip(ss.BLOCK_NAMES, (-0.3, 0.1, 0.4, 0.2)):
        assert params[f"intercept_{name}"] == pytest.approx(want, abs=0.15), name


def test_with_equal_intercepts_it_agrees_with_a_single_platt_map():
    p, y, hours = _slice(intercepts=(0.2, 0.2, 0.2, 0.2), seed=2)
    shared = ss.SharedSlopeBlockCalibrator().fit(p, y, hours).transform(p, hours)
    single = PlattCalibrator()
    single.fit(p, y)
    assert np.max(np.abs(shared - single.transform(p))) < 0.03


def test_the_fallback_is_e031s_rule_applied_to_the_whole_fold():
    p, y, hours = _slice(n=2000)
    assert not ss.needs_fallback(y, hours)
    thin = hours.hour // 6 != 2
    assert ss.needs_fallback(y[thin][:-1], hours[thin][:-1]) is True  # a block with no rows at all
    y_one = y.copy()
    y_one[(hours.hour // 6) == 1] = 0.0  # one block with a single class
    assert ss.needs_fallback(y_one, hours) is True
    assert ss.MIN_BLOCK_CALIB_ROWS == bc.MIN_BLOCK_CALIB_ROWS == 100


def test_on_the_fallback_the_fold_uses_its_single_map():
    p, y, hours = _slice(n=2000)
    single = PlattCalibrator()
    single.fit(p, y)
    y_one = y.copy()
    y_one[(hours.hour // 6) == 3] = 1.0
    out, fitted = ss.shared_slope(p, y_one, hours, p[:50], hours[:50], single)
    assert fitted is None and np.array_equal(out, single.transform(p[:50]))


def test_the_hypotheses_and_scores_are_e031s_own_code():
    assert ss.judge is bc.judge and ss.scores is bc.scores and ss.expected_slices is bc.expected_slices


def test_the_study_never_opens_the_holdout_or_reads_a_prospective_record():
    src = Path(ss.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    keywords = {n.arg for n in ast.walk(tree) if isinstance(n, ast.keyword)}
    assert "allow_holdout" not in keywords
    for word in ("shadow_move_size", "shadow_direction", "predictions", "get_connection"):
        assert word not in src, word
