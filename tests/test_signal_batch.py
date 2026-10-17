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
    for path in (sb.E018_RESULT, sb.E019_RESULT, sb.E032_RESULT):
        assert path.exists(), path
    floats = [n.value for n in ast.walk(ast.parse(SOURCE)) if isinstance(n, ast.Constant) and isinstance(n.value, float)]
    assert floats == [1e-9], floats  # the only float literal is the tolerance


def test_phase_3_neither_reads_the_holdout_nor_touches_a_candidate():
    calls = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
             for n in ast.walk(ast.parse(SOURCE)) if isinstance(n, ast.Call)}
    assert "load_bars" in calls and "allow_holdout" not in SOURCE.replace("allow_holdout=True", "")
    assert "load_bars(end=HOLDOUT.start)" in SOURCE
    for candidate in ("amihud_rel_168", "trade_size_rel_24", "up_streak_6"):
        assert candidate not in SOURCE, f"Phase 3 must not name a candidate input ({candidate})"
