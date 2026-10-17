"""
The sealed holdout must be unreachable by accident, and the period definitions in code
must match the ones documented for humans.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import agent.research.history as history
import agent.research.snapshots as snapshots
from agent.research.baselines import momentum_rule, moving_average_rule, random_signals, signal_mix
from agent.research.periods import BUFFER, EXPLORATION, HOLDOUT, LIVE, VALIDATION, period_of
from agent.shared.types import PriceBar


def test_periods_are_contiguous_and_match_the_documented_split():
    assert EXPLORATION.end == VALIDATION.start == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert VALIDATION.end == HOLDOUT.start == datetime(2025, 7, 1, tzinfo=timezone.utc)
    assert HOLDOUT.end == BUFFER.start == datetime(2026, 8, 20, tzinfo=timezone.utc)
    assert BUFFER.end == LIVE.start
    assert period_of(datetime(2025, 12, 1, tzinfo=timezone.utc)) == "holdout"
    assert period_of(datetime(2017, 1, 1, tzinfo=timezone.utc)) == "before_data"


def _fake_snapshot(tmp_path: Path, monkeypatch) -> Path:
    """A synthetic spot snapshot straddling the holdout's start, registered (in this test only) as the governed one."""
    start = datetime(2025, 6, 29, tzinfo=timezone.utc)
    path = tmp_path / "btcusdt_1h_2026-09-19.csv"
    lines = ["as_of,open,high,low,close,volume"]
    for i in range(96):  # 2025-06-29 00:00 .. 2025-07-02 23:00 -- straddles the holdout start
        t = start + timedelta(hours=i)
        lines.append(f"{t.isoformat()},100,101,99,100,1")
    data = ("\n".join(lines) + "\n").encode()
    path.write_bytes(data)
    development = ("\n".join(lines[:49]) + "\n").encode()  # the header and the 48 candles before the holdout
    monkeypatch.setattr(snapshots, "DATA_DIR", tmp_path)
    monkeypatch.setattr(snapshots, "REGISTERED", {"spot": snapshots.Snapshot(
        path.name, "as_of", timedelta(hours=1), 48, hashlib.sha256(development).hexdigest(), len(data), hashlib.sha256(data).hexdigest())})
    return path


def test_loader_truncates_at_the_holdout_by_default(tmp_path, monkeypatch):
    path = _fake_snapshot(tmp_path, monkeypatch)
    bars, report, snapshot = history.load_bars()
    assert bars[-1].as_of < HOLDOUT.start
    assert len(bars) == 48
    assert snapshot == path
    assert len(history.load_bars(end=HOLDOUT.end)[0]) == 48  # asking past the holdout's start still stops there


def test_holdout_access_requires_a_reason_and_is_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "HOLDOUT_LOG", tmp_path / "HOLDOUT_ACCESS.log")
    monkeypatch.setattr(history, "_HOLDOUT_OPENED_FOR", "")  # restored afterwards: the opening must not outlive this test
    _fake_snapshot(tmp_path, monkeypatch)
    with pytest.raises(history.HoldoutAccessError):
        history.load_bars(allow_holdout=True)
    assert not history.holdout_opened() and not (tmp_path / "HOLDOUT_ACCESS.log").exists()
    history.load_bars()
    assert not history.holdout_opened(), "only the logged route opens the holdout"
    bars, _, _ = history.load_bars(allow_holdout=True, reason="unit test only")
    assert bars[-1].as_of >= HOLDOUT.start
    assert "unit test only" in (tmp_path / "HOLDOUT_ACCESS.log").read_text(encoding="utf-8")
    assert history.holdout_opened()  # the side-data reader may now serve the holdout's rows (agent/research/snapshots.py)


def _rows(closes, sma=None):
    start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    return [{"as_of": (start + timedelta(hours=i)).isoformat(), "close": c, "ind_sma_long": sma} for i, c in enumerate(closes)]


def test_momentum_and_ma_rules_use_only_past_information():
    rows = _rows([100] * 24 + [110, 90], sma=100)
    assert momentum_rule(rows, 24)[:24] == ["HOLD"] * 24  # nothing 24h earlier yet
    assert momentum_rule(rows, 24)[24:] == ["BUY", "SELL"]
    assert moving_average_rule(rows)[24:] == ["BUY", "SELL"]


def test_random_signals_follow_the_requested_mix():
    mix = {"BUY": 0.5, "HOLD": 0.3, "SELL": 0.2}
    sig = random_signals([{}] * 10000, mix, seed=3)
    got = signal_mix(sig)
    assert abs(got["BUY"] - 0.5) < 0.03 and abs(got["SELL"] - 0.2) < 0.03
