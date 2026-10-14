"""
Every route by which code can read sealed-holdout candles (2025-07-01 -> 2026-08-19), reviewed (post-500h plan,
Phase 5, 2026-10-14). The holdout has exactly one way in -- research/history.load_bars(allow_holdout=True,
reason=...), which logs to research/HOLDOUT_ACCESS.log -- and that route is only taken by holdout_eval --unseal.

Until 2026-10-14 the technical backtest (agent/backtest/runner.py) fetched straight from the exchange, past that
guard: E000's warm-up read about 233 holdout-period candles on 2026-09-19 (its scored hours were all in the buffer;
nothing of the holdout was ever scored). These tests prove the bypass is closed, and make any NEW direct fetch of
an arbitrary past window fail until it is reviewed here.
"""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import agent.backtest.runner as runner
from agent.indicators.engine import HISTORY_HOURS
from agent.research.periods import HOLDOUT
from agent.shared.types import PriceBar

H = timedelta(hours=1)
LAST_HOLDOUT_HOUR = HOLDOUT.end - H  # 2026-08-19 23:00


def _utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_the_window_edges_are_exact():
    n = 300
    assert runner.holdout_overlap(HOLDOUT.start - H, n) is None                                   # ends the hour before
    assert runner.holdout_overlap(HOLDOUT.start, n) == (HOLDOUT.start, HOLDOUT.start)             # touches its first hour
    assert runner.holdout_overlap(HOLDOUT.end + (n - 1) * H, n) is None                           # starts at the buffer
    assert runner.holdout_overlap(HOLDOUT.end + (n - 2) * H, n) == (LAST_HOLDOUT_HOUR, LAST_HOLDOUT_HOUR)  # one hour in
    assert runner.holdout_overlap(_utc(2026, 10, 1), 20000) == (HOLDOUT.start, LAST_HOLDOUT_HOUR)  # spans all of it
    assert runner.holdout_overlap(HOLDOUT.end + (n - 1) * H + timedelta(minutes=37), n) is None   # end floored to the hour


def test_it_would_have_refused_e000s_window_and_measures_what_e000_read():
    """E000 (2026-09-19): 30 days + the 250-hour warm-up ending 2026-09-19 16:00 -> 233 holdout candles (audit §18.2)."""
    first, last = runner.holdout_overlap(_utc(2026, 9, 19, 16), 30 * 24 + HISTORY_HOURS)
    assert (first, last) == (_utc(2026, 8, 10, 7), LAST_HOLDOUT_HOUR)
    assert int((last - first) / H) + 1 == 233


class _NoFetch:
    def get_history(self, end, hours):
        raise AssertionError("the exchange must not even be asked for a window that reaches the holdout")


def test_a_backtest_reaching_the_holdout_is_refused_before_anything_is_fetched(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "BinanceProvider", _NoFetch)
    monkeypatch.setattr(runner, "OUTPUT_DIR", tmp_path)
    with pytest.raises(runner.HoldoutRefused, match="sealed-holdout candles"):
        runner.run_backtest(days=60, end=_utc(2026, 10, 14, 13))     # 60 days + warm-up from mid-October
    with pytest.raises(runner.HoldoutRefused):
        runner.run_backtest(days=7, end=_utc(2026, 1, 15))           # an end inside the holdout
    assert not list(tmp_path.iterdir()), "nothing may be written"


def _bars(first: datetime, n: int) -> list[PriceBar]:
    return [PriceBar(as_of=first + i * H, open=100.0 + i % 7, high=101.0 + i % 7, low=99.0 + i % 7, close=100.5 + i % 7,
                     volume=10.0 + i % 5, source="binance") for i in range(n)]


class _Fake:
    def __init__(self, bars):
        self.bars = bars

    def get_history(self, end, hours):
        return self.bars


def test_a_window_after_the_holdout_runs_and_a_provider_that_over_returns_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "OUTPUT_DIR", tmp_path)
    end = _utc(2026, 10, 14, 13)
    n = 24 + HISTORY_HOURS
    assert runner.holdout_overlap(end, n) is None
    monkeypatch.setattr(runner, "BinanceProvider", lambda: _Fake(_bars(end - (n - 1) * H, n)))
    rows, path, _ = runner.run_backtest(days=1, end=end)
    assert len(rows) == 25 and path.exists()
    # second lock: if the exchange ever returned a holdout candle for a safe request, nothing is analysed
    monkeypatch.setattr(runner, "BinanceProvider", lambda: _Fake(_bars(LAST_HOLDOUT_HOUR, n)))
    with pytest.raises(runner.HoldoutRefused, match="returned a sealed-holdout candle"):
        runner.run_backtest(days=1, end=end)


# Every place in agent/ that asks the exchange for an ARBITRARY past window (get_history), with why it cannot read
# the holdout, or where it does, why that is recorded and accepted. A new call site fails this test until reviewed.
REVIEWED_GET_HISTORY = {
    "agent/backtest/runner.py": "refused before the fetch by holdout_overlap() (since 2026-10-14), plus a second check on what came back",
    "agent/research/history.py": "builds the dated snapshot behind load_bars(), which truncates at the holdout unless "
                                 "allow_holdout=True with a written reason (logged to research/HOLDOUT_ACCESS.log)",
    "agent/research/parity.py": "live hours only: from the first live prediction (2026-09-19) minus the 250-hour window, ~2026-09-08",
    "agent/research/weekly_report.py": "live_features: from LIVE.start - 400 h (~2026-09-02), after the holdout. ewma_reference_series: "
                                       "the free EWMA rule's warm-up, which DOES reach into the holdout's last weeks (about 71 hours "
                                       "for the weekly report; for the registered checkpoints it grows with the live span, back to "
                                       "~2026-07-26 at 500 h). Only the rule's values at live hours are used, where holdout candles "
                                       "weigh < 2e-10. Recorded in research/LIVE_EVALUATION.md (500-hour procedure, item 3); left "
                                       "unchanged as registered checkpoint code -- clipping it would be a separate, dated decision",
}
LIVE_ONLY_GET_BAR_AT = {"agent/outcome_tracker.py", "agent/shadow/outcomes.py"}  # grade live predictions' target hours


def _call_sites(pattern: str) -> set[str]:
    out = set()
    for f in Path("agent").rglob("*.py"):
        if "data_providers" in f.parts:
            continue
        if re.search(pattern, f.read_text(encoding="utf-8")):
            out.add(f.as_posix())
    return out


def test_every_direct_fetch_of_a_past_window_is_reviewed():
    assert _call_sites(r"\.get_history\(") == set(REVIEWED_GET_HISTORY)
    assert _call_sites(r"\.get_bar_at\(") == LIVE_ONLY_GET_BAR_AT
    # The stored snapshot (data/btcusdt_1h_2026-09-19.csv) holds the WHOLE holdout period on disk; only the guarded
    # loader may name it, so no new code can read the holdout's candles straight from the file.
    assert _call_sites(r"btcusdt_1h_") == {"agent/research/history.py"}


def _calls_allowing_the_holdout() -> set[str]:
    """Modules with a CALL passing allow_holdout=True (parsed, so a docstring that mentions it does not count)."""
    import ast

    out = set()
    for f in Path("agent").rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and any(k.arg == "allow_holdout" and not (isinstance(k.value, ast.Constant) and k.value.value is False)
                                                  for k in node.keywords):
                out.add(f.as_posix())
    return out


def test_the_only_holdout_route_is_the_logged_one_and_nothing_has_used_it():
    allowing = _calls_allowing_the_holdout()
    assert allowing == {"agent/research/holdout_eval.py"}, allowing
    assert not Path("research/HOLDOUT_ACCESS.log").exists(), "the holdout has been opened -- that must be the user's decision"
