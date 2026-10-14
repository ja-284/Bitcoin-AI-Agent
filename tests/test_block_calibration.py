"""
E031 (research-only): the time-of-day-conditional calibration, on synthetic data (no database, no candles).
Pins what the registration (61db93d) fixed: the model is untouched, only the calibration layer differs; each
block's map is fitted on that block's rows of the SAME calibration slice; the fallback rule; the fold alignment
with the shared walk-forward runner; the four hypotheses as written; and the data boundary.
"""

from pathlib import Path

import numpy as np
import pandas as pd

import agent.research.block_calibration as bc
from agent.research.model_test import PlattCalibrator
from agent.research.walkforward import WalkForwardSpec, make_folds, run_walk_forward

RNG = np.random.default_rng(31)


def _hours(n: int, start="2024-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="h", tz="UTC")


def _offset_by_block(hours: pd.DatetimeIndex, p_true: np.ndarray) -> np.ndarray:
    """A model whose stated probability is too high at night (00-06) and too low in the US session (12-18)."""
    shift = np.where(hours.hour < 6, 0.12, np.where((hours.hour >= 12) & (hours.hour < 18), -0.12, 0.0))
    return np.clip(p_true + shift, 0.02, 0.98)


def test_block_maps_remove_a_planted_block_offset_that_one_map_cannot():
    calib_h, test_h = _hours(2160), _hours(2160, "2024-04-01")
    pc, pt = RNG.uniform(0.15, 0.6, 2160), RNG.uniform(0.15, 0.6, 2160)
    yc, yt = (RNG.uniform(size=2160) < pc).astype(float), (RNG.uniform(size=2160) < pt).astype(float)
    sc, st = _offset_by_block(calib_h, pc), _offset_by_block(test_h, pt)
    single = PlattCalibrator()
    single.fit(sc, yc)
    p_var, used = bc.block_platt(sc, yc, calib_h, st, test_h, single)
    p_inc = single.transform(st)
    blocks = bc.block_group(test_h)
    worst = lambda p: max(abs(p[blocks == k].mean() - yt[blocks == k].mean()) for k in range(4))  # noqa: E731
    assert used == [] and worst(p_var) < 0.5 * worst(p_inc)


def test_a_thin_or_one_class_block_falls_back_to_the_folds_single_map():
    calib_h = _hours(800)  # ~200 rows per block, except the two made thin below
    keep = ~((calib_h.hour >= 6) & (calib_h.hour < 12))  # the 06-12 block has no calibration rows at all
    calib_h = calib_h[keep]
    pc = RNG.uniform(0.2, 0.6, len(calib_h))
    yc = (RNG.uniform(size=len(calib_h)) < pc).astype(float)
    yc[(calib_h.hour >= 12) & (calib_h.hour < 18)] = 0.0  # one class only in 12-18
    test_h = _hours(96, "2024-03-01")
    pt = RNG.uniform(0.2, 0.6, 96)
    single = PlattCalibrator()
    single.fit(pc, yc)
    p, used = bc.block_platt(pc, yc, calib_h, pt, test_h, single)
    assert sorted(used) == ["06-12", "12-18"]
    m = ((test_h.hour >= 6) & (test_h.hour < 18))
    np.testing.assert_allclose(p[m], single.transform(pt[m]))  # exactly the single map where it fell back
    assert len(p) == 96 and np.all((p > 0) & (p < 1))


def test_the_recorded_folds_line_up_with_the_shared_runner():
    """run() pairs each recorded calibrator with expected_slices(); that pairing must match run_walk_forward."""
    idx = _hours(24 * 900, "2021-01-01")
    df = pd.DataFrame({"x": RNG.normal(size=len(idx))}, index=idx)
    df["y"] = (RNG.uniform(size=len(idx)) < 1 / (1 + np.exp(-df["x"]))).astype(float)
    df.loc[df.index[5000:5100], "x"] = np.nan  # holes must be skipped identically
    spec = WalkForwardSpec(horizon_hours=1, min_train_days=365, test_block_days=90, embargo_hours=24, calib_days=90)
    folds = make_folds(df.index, spec)
    recs = []

    def make_cal():
        recs.append(bc.RecordingPlatt())
        return recs[-1]

    from agent.research.model_test import LogisticModel

    run_walk_forward(df, ["x"], "y", lambda: LogisticModel(C=0.1), spec, folds=folds, make_calibrator=make_cal)
    slices = bc.expected_slices(df, ["x"], "y", folds)
    assert len(slices) == len(recs) > 3
    for rec, (ch, th) in zip(recs, slices):
        assert len(rec.calib_p) == len(ch) and len(rec.test_p) == len(th)


def test_the_recording_calibrator_is_the_incumbent_platt_unchanged():
    p, y = RNG.uniform(0.1, 0.7, 500), (RNG.uniform(size=500) < 0.4).astype(float)
    rec, ref = bc.RecordingPlatt(), PlattCalibrator()
    rec.fit(p, y)
    ref.fit(p, y)
    q = RNG.uniform(0.1, 0.7, 50)
    np.testing.assert_array_equal(rec.transform(q), ref.transform(q))
    np.testing.assert_array_equal(rec.calib_p, p) and np.testing.assert_array_equal(rec.test_p, q)


def test_the_calibration_line_of_a_calibrated_forecast_is_near_zero_and_one():
    p = RNG.uniform(0.05, 0.95, 20000)
    y = (RNG.uniform(size=20000) < p).astype(float)
    line = bc.calibration_line(p, y)
    assert abs(line["intercept"]) < 0.08 and abs(line["slope"] - 1) < 0.08


def _result(inc_worst, var_worst, ci_high, var_ece, buckets_ok, rho_inc, rho_var):
    period = lambda iw, vw, ve: {"incumbent": {"worst_block_offset": iw, "ece": 0.01, "rho": rho_inc, "e013_buckets_ok": True},  # noqa: E731
                                 "variant": {"worst_block_offset": vw, "ece": ve, "rho": rho_var, "e013_buckets_ok": buckets_ok}}
    r = {"by_period": {"exploration": period(inc_worst[0], var_worst[0], var_ece[0]),
                       "validation": period(inc_worst[1], var_worst[1], var_ece[1])}}
    r["by_period"]["validation"]["incumbent_minus_variant_brier"] = {"ci_high": ci_high}
    return r


def test_the_four_hypotheses_are_applied_exactly_as_registered():
    ok = bc.judge(_result((0.047, 0.057), (0.020, 0.028), 0.0001, (0.010, 0.020), True, 0.36, 0.355))
    assert all(ok.values())
    assert not bc.judge(_result((0.047, 0.057), (0.020, 0.030), 0.0001, (0.01, 0.02), True, 0.36, 0.36))["H_a_removes_the_offsets"]  # 0.030 > half of 0.057
    assert not bc.judge(_result((0.047, 0.057), (0.02, 0.02), -0.0001, (0.01, 0.02), True, 0.36, 0.36))["H_b_no_skill_loss"]
    assert not bc.judge(_result((0.047, 0.057), (0.02, 0.02), 0.0, (0.031, 0.02), True, 0.36, 0.36))["H_c_calibration"]
    assert not bc.judge(_result((0.047, 0.057), (0.02, 0.02), 0.0, (0.01, 0.02), False, 0.36, 0.36))["H_c_calibration"]
    assert not bc.judge(_result((0.047, 0.057), (0.02, 0.02), 0.0, (0.01, 0.02), True, 0.36, 0.335))["H_d_ranking"]
    assert bc.MIN_BLOCK_CALIB_ROWS == 100 and bc.RANKING_TOLERANCE == 0.02


def test_development_data_only_and_nothing_live():
    src = Path("agent/research/block_calibration.py").read_text(encoding="utf-8")
    assert "load_bars(end=HOLDOUT.start)" in src and "allow_holdout" not in src
    for forbidden in ("agent.shadow", "agent.database", "agent.reporting", "move_size_1h_v1.json", "shadow_move_size"):
        assert forbidden not in src, forbidden
