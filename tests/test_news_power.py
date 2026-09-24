"""
E025 planning (agent/research/news_power.py): the formulas, the gap handling, the simulation's
calibration, and -- most important -- that it never reads an outcome, so the eventual news test
stays clean. No database.
"""

import ast
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from agent.research import news_power as npw

SOURCE = Path("agent/research/news_power.py").read_text(encoding="utf-8")


def test_the_study_never_reads_an_outcome_or_a_return():
    """The whole point: planning must not look at news against outcomes, or the later test is spent."""
    sql = npw.NEWS_SQL.lower()
    for word in ("outcome", "pct_change", "return", "close_price"):
        assert word not in sql, word
    tree = ast.parse(SOURCE)
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    for forbidden in ("fetch_rows", "fetch_shadow_rows", "predictions_awaiting_outcome", "make_labels", "load_bars"):
        assert forbidden not in imported, forbidden
    executed = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"]
    assert len(executed) == 1, "exactly one query, NEWS_SQL"


def test_a_one_hour_target_is_not_inflated_by_a_persistent_predictor():
    """Bartlett: with serially independent next-hour returns, the predictor's own persistence does not matter."""
    persistent = np.array([0.95 ** k for k in range(48)])
    assert npw.vif(persistent, 1) == 1.0


def test_overlapping_targets_inflate_the_variance():
    persistent = np.array([0.9 ** k for k in range(48)])
    independent = np.zeros(48)
    independent[0] = 1.0
    assert npw.vif(independent, 24) == pytest.approx(1.0)
    assert npw.vif(persistent, 6) > 3 and npw.vif(persistent, 24) > npw.vif(persistent, 6)


def test_the_detectable_effect_and_the_hours_needed_are_inverses():
    assert npw.mde(500, 1.0) == pytest.approx((1.959964 + 0.841621) / math.sqrt(500))
    n = npw.hours_needed(0.05, 1.0)
    assert npw.mde(n, 1.0) <= 0.05 < npw.mde(n - 1, 1.0)


def test_segments_never_bridge_a_gap():
    t0 = datetime(2026, 9, 20, tzinfo=timezone.utc)
    rows = [(t0 + timedelta(hours=h), float(h)) for h in (0, 1, 2, 5, 6)]
    assert [list(s) for s in npw.segments(rows)] == [[0.0, 1.0, 2.0], [5.0, 6.0]]


def test_pooled_acf_recovers_a_known_structure():
    rng = np.random.default_rng(3)
    x = np.zeros(4000)
    for t in range(1, 4000):
        x[t] = 0.8 * x[t - 1] + rng.standard_normal()
    acf, pairs = npw.pooled_acf([x[:2000], x[2000:]], 6)
    assert acf[0] == pytest.approx(1.0) and acf[1] == pytest.approx(0.8, abs=0.03) and acf[6] == pytest.approx(0.8 ** 6, abs=0.05)
    assert pairs[1] == 3998  # one pair lost per segment, none across the boundary


def test_the_simulated_test_detects_a_large_effect_and_rarely_a_null_one():
    strong = npw.simulate(400, 1, 0.3, 0.9, reps=20, boot=100, seed=1)
    null = npw.simulate(400, 1, 0.0, 0.9, reps=40, boot=100, seed=2)
    assert strong >= 0.9
    assert null <= 0.2
