"""
The safe-signal-research batch (E036, E037), Phase 3: the reference reproduction must be able to FAIL. The comparison
is pure, so these tests prove it reports every kind of difference, and that the expected figures come from the
committed result files rather than from numbers typed into the code.
"""

import ast
import json
from pathlib import Path

import agent.research.signal_batch as sb

SOURCE = Path("agent/research/signal_batch.py").read_text(encoding="utf-8")


def test_identical_results_reproduce_and_labels_of_a_run_are_ignored():
    a = {"experiment": "E032", "generated_at": "x", "rows": 56309, "by": {"brier": 0.2488663145227134, "ok": True, "name": "m"}}
    b = {"experiment": "E037/reproduction_E032", "generated_at": "y", "rows": 56309, "by": {"brier": 0.2488663145227134, "ok": True, "name": "m"}}
    assert sb.compare(a, b) == []


def test_every_kind_of_difference_is_reported():
    base = {"rows": 10, "p": {"brier": 0.25, "ci": [0.1, 0.2], "nan": float("nan"), "flag": True}}
    assert sb.compare(base, json.loads(json.dumps(base))) == []
    cases = [
        {"rows": 11, "p": base["p"]},                                                       # a count off by one
        {"rows": 10, "p": {**base["p"], "brier": 0.25 + 2e-9}},                             # a float just beyond 1e-9
        {"rows": 10, "p": {**base["p"], "ci": [0.1]}},                                      # a list of another length
        {"rows": 10, "p": {k: v for k, v in base["p"].items() if k != "flag"}},             # a key missing
        {"rows": 10, "p": {**base["p"], "extra": 1}},                                       # an unexpected key
        {"rows": 10, "p": {**base["p"], "flag": False}},                                    # a flag flipped
        {"rows": 10, "p": {**base["p"], "nan": 0.3}},                                       # NaN expected, a number reproduced
    ]
    for got in cases:
        assert sb.compare(base, got), got
    assert sb.compare({"x": 0.25}, {"x": 0.25 + 0.5e-9}) == []                              # inside the tolerance
    assert sb.TOLERANCE == 1e-9                                                             # the value both records fixed


def test_the_expected_figures_are_read_from_the_committed_results_never_typed():
    """No reference figure is typed into the code: the only float literals are the registered constants and the
    mechanics of percentiles and bounds."""
    for path in (sb.E018_RESULT, sb.E019_RESULT, sb.E032_RESULT):
        assert path.exists(), path
    floats = {n.value for n in ast.walk(ast.parse(SOURCE)) if isinstance(n, ast.Constant) and isinstance(n.value, float)}
    registered = {1e-9, 0.05, 1.10, 0.03, 0.02, 1.5, 2.0}
    mechanics = {0.0, 1.0, 2.5, 97.5, 1.25, 98.75}
    assert floats <= registered | mechanics, floats - registered - mechanics


def test_no_holdout_route_and_exactly_the_registered_inputs_and_constants():
    assert "load_bars(end=HOLDOUT.start)" in SOURCE and "allow_holdout" not in SOURCE
    assert sb.MS_CANDIDATE == ["amihud_rel_168", "trade_size_rel_24"] and sb.UP_STREAK == "up_streak_6"   # E036, E037
    assert (sb.ALPHA, sb.PRACTICAL_RATIO, sb.ECE_BAR, sb.RHO_TOLERANCE, sb.MIN_POSITIVE_YEARS) == (0.05, 1.10, 0.03, 0.02, 6)
    assert (sb.MS_TRIPWIRE_RATIO, sb.D2_TRIPWIRE_RATIO, sb.YEARS) == (1.5, 2.0, tuple(range(2018, 2026)))
    for record in ("E036_ms_a_liquidity_pair.json", "E037_direction_d1_d2.json"):
        text = Path("research/experiments", record).read_text(encoding="utf-8")
        assert "1.10" in text and "6 of the 8" in text and "seed 31" in text, record


# ---- Phase 4: the registered judging rules, each shown to give both answers ----
def test_the_bootstrap_p_is_the_registered_formula():
    import numpy as np

    assert sb.bootstrap_p(np.full(2000, 0.3)) == 2 / 2001                       # every resample on one side
    assert sb.bootstrap_p(np.r_[np.full(1000, 0.3), np.full(1000, -0.3)]) == 1.0  # balanced: capped at 1
    assert sb.bootstrap_p(np.r_[np.full(1950, 0.3), np.full(50, -0.3)]) == 2 * 51 / 2001


def test_holm_steps_down_within_a_family():
    both = sb.holm({"D1": 0.01, "D2": 0.04})
    assert both["D1"]["p_holm"] == 0.02 and both["D1"]["rejected"] and both["D2"]["p_holm"] == 0.04 and both["D2"]["rejected"]
    neither = sb.holm({"D1": 0.03, "D2": 0.04})
    assert neither["D1"]["p_holm"] == 0.06 and not neither["D1"]["rejected"] and not neither["D2"]["rejected"]
    assert sb.holm({"MS-A": 0.049})["MS-A"] == {"p": 0.049, "p_holm": 0.049, "rejected": True}  # a family of one


def test_the_practical_threshold_is_ten_percent_more_skill_in_brier_terms():
    assert abs(sb.practical_threshold(0.0983, 0.2494) - 0.10 * 0.0983 * 0.2494) < 1e-15
    assert sb.practical_threshold(-0.001, 0.25) == 0.0


def _j(diff=0.003, ci=(0.002, 0.004), expl=0.001, years=None, p=0.001, threshold=0.0025, calibration=True, rho=True, **kw):
    years = years if years is not None else {str(y): 0.001 for y in range(2018, 2026)}
    return sb.judge({"diff": diff, "ci95": list(ci)}, {"diff": expl}, years, p, threshold, "ci95", calibration, rho, **kw)


def test_judge_supported_only_when_every_registered_criterion_holds():
    assert _j()["verdict"] == "SUPPORTED"
    assert _j(p=0.06)["verdict"] == "INCONCLUSIVE"                                   # S1: not significant
    assert _j(diff=0.002, ci=(0.0005, 0.0035))["verdict"] == "INCONCLUSIVE"            # S2: below the bar, interval reaches it
    assert _j(expl=-0.0001)["verdict"] == "INCONCLUSIVE"                               # S3: exploration disagrees
    five = {str(y): (0.001 if y < 2023 else -0.001) for y in range(2018, 2026)}
    assert _j(years=five)["verdict"] == "INCONCLUSIVE" and _j(years=five)["criteria"]["S5_years_positive"] == 5   # S5
    assert _j(rho=False)["verdict"] == "INCONCLUSIVE"                                  # S6 (E036 only)
    assert "S6_ranking_not_worse" not in _j(rho=None)["criteria"]                      # E037 has no S6


def test_judge_not_supported_when_the_bar_is_excluded_or_calibration_fails():
    assert _j(diff=0.0004, ci=(-0.0002, 0.0010), p=0.3)["verdict"] == "NOT_SUPPORTED"  # upper bound below the bar
    assert _j(diff=0.0004, ci=(0.0001, 0.0010), p=0.01)["verdict"] == "NOT_SUPPORTED"  # significant but practically nothing
    assert _j(calibration=False)["verdict"] == "NOT_SUPPORTED"                         # everything else fine: disqualified
    j = _j(diff=0.0004, ci=(-0.0002, 0.0010), p=0.3)
    assert j["upper_bound_below_threshold"] and not j["criteria"]["S1_difference_positive_and_significant"]


def test_a_non_positive_smaller_skill_reads_s2_as_the_larger_skill_being_positive():
    j = _j(threshold=0.0, small_skill_not_positive=True, large_skill_positive=False)
    assert not j["criteria"]["S2_practical"] and j["verdict"] != "SUPPORTED"
    assert _j(threshold=0.0, small_skill_not_positive=True, large_skill_positive=True)["criteria"]["S2_practical"]


def test_year_differences_are_brier_without_minus_brier_with_per_calendar_year():
    import numpy as np
    import pandas as pd

    idx = pd.DatetimeIndex(["2019-03-01", "2019-04-01", "2024-02-01"], tz="UTC")
    y = np.array([1.0, 0.0, 1.0])
    out = sb.year_differences(idx, np.array([0.5, 0.5, 0.5]), np.array([0.9, 0.1, 0.4]), y)
    assert set(out) == {"2019", "2024"}
    assert abs(out["2019"] - (0.25 - 0.01)) < 1e-12 and abs(out["2024"] - (0.25 - 0.36)) < 1e-12
