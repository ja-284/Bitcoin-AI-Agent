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
                                       "the free EWMA rule's warm-up -- clipped at the buffer's first hour since Amendment A1 "
                                       "(research/LIVE_EVALUATION.md, 2026-10-14), so it no longer reads the holdout (tested below); "
                                       "until then it reached ~71 holdout hours (weekly) and back to ~2026-07-26 (500-hour reading)",
}
LIVE_ONLY_GET_BAR_AT = {"agent/outcome_tracker.py", "agent/shadow/outcomes.py",  # grade live predictions' target hours
                        "agent/direction_shadow/outcomes.py"}  # (2026-10-15, E034) the same, for rows written from 2026-10-15 on


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
    # The stored snapshot (data/btcusdt_1h_2026-09-19.csv) holds the WHOLE holdout period on disk. Only the registry
    # (snapshots.py) and the hand-run downloader's file naming (history.py) may name it, so no new code can read the
    # holdout's candles straight from the file. (The side snapshots klines_extra_btcusdt_1h_* and premium_btcusdt_1h_*
    # are tested below.)
    assert _call_sites(r"(?<!extra_)(?<!premium_)btcusdt_1h_") == {"agent/research/history.py", "agent/research/snapshots.py"}


# ---- Safe signal research, Phase 1 (2026-10-17): the side-data snapshots have ONE governed reader ----
# Until 2026-10-17 each side loader read its whole dated file, the holdout's period included, and downloaded a new file
# when none was found. Now only agent/research/snapshots.py reads them: registered files only, cut at the last
# development cutoff unless the holdout was opened through the logged route, never a download.
SIDE_LOADERS = {"load_klines_extra", "load_funding", "load_premium", "load_macro", "load_onchain", "load_difficulty"}
DOWNLOADERS = {"download_klines_extra", "download_funding", "download_premium", "download_macro", "download_onchain",
               "download_difficulty", "download_snapshot"}
GOVERNED = SIDE_LOADERS | {"load_bars", "read_snapshot_rows", "read_snapshot_frame", "compute_group_features", "build_frame"}


def _callers(names: set[str]) -> dict[str, set[str]]:
    """file -> the names it CALLS (a call, not a definition or a mention) from `names`, over agent/ and run.py."""
    import ast

    out: dict[str, set[str]] = {}
    for f in [*Path("agent").rglob("*.py"), Path("run.py")]:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
                if name in names:
                    out.setdefault(f.as_posix(), set()).add(name)
    return out


def test_side_data_is_read_only_through_the_governed_reader():
    assert _call_sites(r"read_csv\(") == {"agent/research/snapshots.py"}  # no other file parses a CSV
    # every side loader is called from exactly one research route, which passes the candles' own information cutoff
    assert _callers(SIDE_LOADERS) == {"agent/research/feature_test.py": SIDE_LOADERS}
    # the reader itself is called only by the loaders: the side data's four modules, and load_bars for the spot candles
    assert _callers({"read_snapshot_rows", "read_snapshot_frame"}) == {
        "agent/research/snapshots.py": {"read_snapshot_rows"}, "agent/research/history.py": {"read_snapshot_rows"},
        "agent/research/microstructure.py": {"read_snapshot_frame"}, "agent/research/derivatives.py": {"read_snapshot_frame"},
        "agent/research/macro.py": {"read_snapshot_frame"}, "agent/research/onchain.py": {"read_snapshot_frame"}}
    # nothing downloads a replacement: every downloader is run by hand only (the spot loader stopped too, 2026-10-17)
    assert _callers(DOWNLOADERS) == {}


def test_only_the_registry_names_the_side_snapshot_files():
    named = _call_sites(r"(klines_extra|premium)_btcusdt_1h_20|funding_btcusdt_20|onchain_20|difficulty_adjustments_20|macro_20")
    assert named == {"agent/research/snapshots.py"}


def test_live_code_never_reads_a_research_snapshot():
    """The hourly job, both shadow tracks, the reporting layer and every module a workflow runs: none calls a governed
    research loader, so the boundary change cannot touch the live record or a prospective track."""
    live = {f for f in _callers(GOVERNED) if not f.startswith(("agent/research/", "agent/backtest/"))}
    assert live == set(), live
    targets = set()
    for wf in Path(".github/workflows").glob("*.yml"):
        targets |= set(re.findall(r"python -m (agent[\w.]*)", wf.read_text(encoding="utf-8")))
    assert targets and all(not t.startswith("agent.research") for t in targets), targets


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
    import agent.research.history as history

    assert not history.holdout_opened(), "a process starts with the holdout closed; only load_bars(allow_holdout=True) opens it"


# ---- Amendment A1 (research/LIVE_EVALUATION.md, 2026-10-14): the free EWMA rule's warm-up never reads the holdout ----
FIRST_SHADOW_HOUR = _utc(2026, 9, 21, 17)


def _checkpoint_lookback(now: datetime) -> int:
    """What agent/research/live_checkpoint.main passes (registered code, unchanged): the live span plus 800 h."""
    return int((now - FIRST_SHADOW_HOUR).total_seconds() // 3600) + 800


@pytest.mark.parametrize("now, lookback", [
    (_utc(2026, 10, 13, 19, 33), None),     # the 500-hour reading's moment (it ran under the old warm-up; never recomputed)
    (_utc(2026, 12, 14, 12), None),         # the expected 2,000-hour reading
    (_utc(2027, 5, 1), None),               # the 5,000-hour reading, roughly
    (_utc(2026, 10, 20, 9), 800),           # a weekly report
])
def test_the_ewma_window_starts_no_earlier_than_the_buffer(now, lookback):
    import agent.research.weekly_report as wr

    end = now.replace(minute=0, second=0, microsecond=0) - H
    hours = wr.ewma_fetch_hours(end, _checkpoint_lookback(now) if lookback is None else lookback)
    first = end - (hours - 1) * H
    assert first == HOLDOUT.end, first          # clipped exactly at the buffer's first hour: as much warm-up as is allowed
    assert runner.holdout_overlap(end, hours) is None


def test_a_short_window_is_left_alone_and_an_invalid_one_is_refused():
    import agent.research.weekly_report as wr

    end = _utc(2026, 10, 14, 13)
    assert wr.ewma_fetch_hours(end, -10_000) < int((end - HOLDOUT.end) / H) + 1   # nothing to clip: the old window, unchanged
    assert wr.ewma_fetch_hours(HOLDOUT.end, 800) == 1                            # the buffer's very first hour, alone
    with pytest.raises(ValueError, match="sealed holdout"):
        wr.ewma_fetch_hours(LAST_HOLDOUT_HOUR, 800)                              # a window ending inside the holdout


def test_the_ewma_reference_asks_only_for_allowed_candles_and_refuses_a_holdout_candle(monkeypatch):
    import agent.data_providers.binance as binance
    import agent.research.weekly_report as wr

    asked = {}

    class _Recording:
        def get_history(self, end, hours):
            asked.update(end=end, hours=hours)
            return _bars(end - (hours - 1) * H, hours)

    monkeypatch.setattr(binance, "BinanceProvider", _Recording)
    now = _utc(2026, 12, 14, 12)
    series = wr.ewma_reference_series(now, lookback_hours=_checkpoint_lookback(now))
    assert asked["end"] - (asked["hours"] - 1) * H == HOLDOUT.end and series.index.min() >= HOLDOUT.end

    class _OverReturning:
        def get_history(self, end, hours):
            return _bars(LAST_HOLDOUT_HOUR, hours)

    monkeypatch.setattr(binance, "BinanceProvider", _OverReturning)
    with pytest.raises(RuntimeError, match="sealed-holdout candle"):
        wr.ewma_reference_series(now)


def test_dropping_the_holdout_warm_up_moves_the_rule_by_at_most_the_stated_bound():
    """A1's bound, checked with the rule's own code on synthetic candles: at every hour >= 785 h after the buffer's
    first hour (the first shadow hour is 785 h after it), clipping the warm-up there moves the value by <= 2 * 2^(-785/24)."""
    import numpy as np

    from agent.research.simple_baselines import simple_rules

    rng = np.random.default_rng(1)
    start = _utc(2026, 4, 1)
    n = int((_utc(2026, 11, 1) - start) / H)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
    bars = [PriceBar(as_of=start + i * H, open=float(c), high=float(c), low=float(c), close=float(c), volume=1.0, source="binance")
            for i, c in enumerate(close)]
    full = simple_rules(bars)["E_ewma_halflife_24h"]
    clipped = simple_rules([b for b in bars if b.as_of >= HOLDOUT.end])["E_ewma_halflife_24h"]
    judged = full.index[full.index >= HOLDOUT.end + 785 * H]
    diff = (full.reindex(judged) - clipped.reindex(judged)).abs()
    assert len(judged) > 900 and diff.notna().all()
    assert diff.max() <= 2 * 2 ** (-785 / 24), diff.max()
