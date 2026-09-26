"""E027: the slices are the checkpoint's own slices, built the same way. Synthetic timestamps only."""

from datetime import datetime, timedelta, timezone

import pandas as pd

from agent.research import live_checkpoint as lc
from agent.research import slice_calibration as sc


def _index(n=24 * 9):
    start = datetime(2026, 9, 21, tzinfo=timezone.utc)  # a Monday
    return pd.DatetimeIndex([start + timedelta(hours=i) for i in range(n)])


def test_the_day_split_matches_the_checkpoints_rule():
    idx = _index()
    ours = [sc.DAY_NAMES[k] for k in sc.day_group(idx)]
    theirs = ["weekend" if t.weekday() >= 5 else "weekday" for t in idx]
    assert ours == theirs and ours.count("weekend") == 48


def test_the_hour_blocks_match_the_checkpoints_labels():
    idx = _index()
    ours = [sc.BLOCK_NAMES[k] for k in sc.block_group(idx)]
    theirs = [next(f"{a:02d}-{b:02d}" for a, b in lc.HOUR_BLOCKS if a <= t.hour < b) for t in idx]
    assert ours == theirs and set(ours) == {"00-06", "06-12", "12-18", "18-24"}


def test_the_calibration_table_is_e026s():
    from agent.research import regime_calibration as rc

    assert sc.group_table is rc.group_table
