"""
Research integrity (interim plan, priority F): the weekly monitoring and the registered checkpoint compute
the same quantities with two independent code paths -- `weekly_report.paper_record` (what every report
shows) and `live_checkpoint.core` (what the 500 / 2,000 / 5,000-hour readings will use). If they ever
disagreed, the running record and the checkpoint would tell different stories about the same hours. Synthetic
data only: no prospective outcome is read.
"""

import numpy as np
import pytest

from agent.research import live_checkpoint as lc
from agent.research import weekly_report as wr


def _hours(n, seed):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.1, 0.9, size=n)
    y = (rng.uniform(size=n) < p).astype(float)
    size = np.abs(rng.normal(0, 0.004, size=n)) * (0.5 + p)
    return p, y, size


@pytest.mark.parametrize("n,seed", [(120, 1), (500, 2), (2000, 3)])
def test_the_report_and_the_checkpoint_agree_on_every_point_value(n, seed):
    p, y, size = _hours(n, seed)
    rep, cp = wr.paper_record(p, y, size), lc.core(p, y, size)
    assert cp["brier_rel_gain"] == pytest.approx(rep["brier_rel_gain"], rel=1e-12)
    assert cp["ece"] == pytest.approx(rep["ece"], rel=1e-12)
    assert cp["accuracy"] == pytest.approx(rep["accuracy"], rel=1e-12)
    assert cp["naive_rate"] == pytest.approx(rep["naive_rate"], rel=1e-12)
    assert cp["large_move_share"] == pytest.approx(rep["base_rate_large"], rel=1e-12)
    # two different rank-correlation routes (pandas ranks in the report, scipy-style ranks in the checkpoint)
    assert cp["rho"] == pytest.approx(rep["rank_corr_p_vs_abs_return"], abs=1e-12)
    assert [b["n"] for b in cp["buckets"]] == [b["n"] for b in rep["reliability"]]


def test_both_use_48_hour_blocks_and_the_same_minimum_for_intervals():
    """Same block length, same 4-block minimum: an interval appears in both, or in neither."""
    p, y, size = _hours(191, 4)
    assert "rho_ci95" not in lc.core(p, y, size) and "brier_rel_gain_ci95" not in wr.paper_record(p, y, size)
    p, y, size = _hours(192, 4)
    assert "rho_ci95" in lc.core(p, y, size) and "rank_corr_p_vs_abs_return_ci95" in wr.paper_record(p, y, size)
    assert lc.BLOCK_HOURS == 48


def test_the_checkpoint_keeps_the_registered_resample_count_while_the_report_uses_more():
    """Deliberate and documented (LIVE_EVALUATION.md clarification 9): 500 at checkpoints, 2,000 in reports."""
    import importlib

    assert importlib.reload(lc).N_BOOT == 500 and wr.N_BOOT == 2000
