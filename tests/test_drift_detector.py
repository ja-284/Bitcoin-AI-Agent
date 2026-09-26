"""E029: the CUSUM, the registered h rule, the injection and the judgement. Synthetic only; no live data."""

from pathlib import Path

import numpy as np

from agent.research import drift_detector as dd


def test_no_alarm_without_an_offset_and_a_timed_alarm_with_one():
    assert dd.cusum(np.zeros(1000), 0.025, 1.0) == []
    # +0.1 per hour, allowance 0.025: the sum passes 1.0 on the 14th hour (0.075 * 14 = 1.05), then resets
    alarms = dd.cusum(np.full(30, 0.1), 0.025, 1.0)
    assert alarms == [(13, 1), (27, 1)]
    assert dd.cusum(np.full(30, -0.1), 0.025, 1.0) == [(13, -1), (27, -1)]


def test_the_h_rule_returns_the_smallest_grid_value_that_meets_the_target():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.3, 0.6, 5000)
    chosen = dd.choose_h(p, target=2.0, sims=3, seed=1)
    assert chosen["control_alarms_per_1000"] <= 2.0
    if chosen["h"] > dd.H_GRID_START:           # one step lower must fail the target, with the same simulations
        again = np.random.default_rng(1)
        controls = [p - (again.random(len(p)) < p) for _ in range(3)]
        lower = chosen["h"] - dd.H_GRID_STEP
        assert np.mean([dd.alarms_per_1000(r, dd.K, lower) for r in controls]) > 2.0


def test_the_injection_changes_only_the_statement_after_the_change_point():
    p = np.full(3000, 0.4)
    y = np.zeros(3000)
    y[::5] = 1.0                                 # exactly 20% observed, far below 0.4: every window alarms early
    w = dd.window_delays(p, y, 0.025, 5.0, 0.10, window=3000, step=500, change=500)[0]
    assert w["pre_change_alarms"] > 0 and w["delay"] is not None
    calibrated = np.where(np.arange(3000) % 5 < 2, 1.0, 0.0)          # 40% observed = stated before the change
    w = dd.window_delays(p, calibrated, 0.025, 5.0, 0.10, window=3000, step=500, change=500)[0]
    assert w["pre_change_alarms"] == 0 and 0 < w["delay"] < 200      # +0.10 over: ~5 / 0.075 = 67 hours


def test_the_judgement_applies_the_registered_rules():
    def s(median, within2000):
        return {"median_delay": median, "detected_within": {"2000": within2000}}
    real = {"+0.10": s(300, 1.0), "+0.05": s(700, 0.95)}
    ctrl = {"+0.05": s(650, 0.96)}
    assert dd.judge(0.3, real, ctrl) == {"H_a_false_alarms": True, "H_b_detection": True, "H_c_real_like_control": True}
    assert not dd.judge(0.41, real, ctrl)["H_a_false_alarms"]
    assert not dd.judge(0.3, {**real, "+0.10": s(501, 1.0)}, ctrl)["H_b_detection"]
    assert not dd.judge(0.3, {**real, "+0.05": s(700, 0.89)}, ctrl)["H_b_detection"]
    assert not dd.judge(0.3, real, {"+0.05": s(500, 0.96)})["H_c_real_like_control"]      # 700/500 = +40%
    assert not dd.judge(0.3, {**real, "+0.05": s(np.inf, 0.95)}, ctrl)["H_c_real_like_control"]


def test_the_detector_never_reaches_the_live_system():
    """Research-only: nothing in the live or shadow path may import it."""
    for path in [*Path("agent/shadow").glob("*.py"), Path("agent/orchestrator.py"), *Path("agent/scoring").glob("*.py"),
                 *Path("agent/api").glob("*.py"), Path("agent/research/live_checkpoint.py"), Path("agent/research/weekly_report.py")]:
        assert "drift_detector" not in path.read_text(encoding="utf-8"), path
