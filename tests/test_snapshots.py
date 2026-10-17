"""
The governed reader for the stored research snapshots (agent/research/snapshots.py; master plan "Safe signal
research", Phase 1, 2026-10-17). Before it, the side-data loaders read their whole files -- the holdout's period
included -- and downloaded a replacement whenever a file was missing.

Every test here builds its own synthetic files: no real holdout value is used to construct any test. Only the last
test reads the real snapshots on this machine, and only their development rows (it is skipped where they are absent,
as on GitHub's runners).
"""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
import requests

import agent.research.feature_test as feature_test
import agent.research.history as history
import agent.research.snapshots as snapshots
from agent.research import derivatives, macro, microstructure, onchain
from agent.research.features import bars_to_frame
from agent.research.periods import HOLDOUT
from agent.research.shape import shape_features
from agent.shared.types import PriceBar

H = timedelta(hours=1)
D = timedelta(days=1)
CUT = HOLDOUT.start  # the information cutoff of the last development hour
REAL_REGISTRY = dict(snapshots.REGISTERED)
REAL_DATA_DIR = Path("data")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Each test reads only its own synthetic files, starts with the holdout closed, and can never download."""
    monkeypatch.setattr(snapshots, "DATA_DIR", tmp_path)
    monkeypatch.setattr(snapshots, "REGISTERED", {})
    monkeypatch.setattr(history, "_HOLDOUT_OPENED_FOR", "")

    def no_download(*a, **k):
        raise AssertionError("governed research must never download")

    monkeypatch.setattr(requests, "get", no_download)
    for module, fn in ((microstructure, "download_klines_extra"), (derivatives, "download_funding"), (derivatives, "download_premium"),
                       (macro, "download_macro"), (onchain, "download_onchain"), (onchain, "download_difficulty"),
                       (history, "download_snapshot")):
        monkeypatch.setattr(module, fn, no_download)
    return tmp_path


def _register(tmp: Path, name: str, file: str, header: str, lines: list[str], dev_count: int, time_column: str,
              visible_after: timedelta, tail: bytes = b"") -> bytes:
    """Writes the file (CRLF, as the real snapshots) and registers it with a fingerprint computed HERE, independently:
    the header plus the first `dev_count` lines."""
    body = [(header + "\r\n").encode()] + [(line + "\r\n").encode() for line in lines]
    data = b"".join(body) + tail
    (tmp / file).write_bytes(data)
    snapshots.REGISTERED[name] = snapshots.Snapshot(file, time_column, visible_after, dev_count,
                                                    hashlib.sha256(b"".join(body[: 1 + dev_count])).hexdigest(),
                                                    len(data), hashlib.sha256(data).hexdigest())
    return data


def _hourly(start: datetime, n: int, cols: int) -> list[str]:
    return [f"{(start + i * H).isoformat()}," + ",".join(str(100 + i % 7 + c) for c in range(cols)) for i in range(n)]


def _klines(start: datetime, n: int) -> list[str]:
    return [f"{(start + i * H).isoformat()},{100 + i % 7},{1000 + i},{40 + i % 5}" for i in range(n)]


def _days(start: datetime, n: int) -> list[str]:
    return [f"{start + i * D:%Y-%m-%d} 00:00:00+00:00,{5 + i % 3},{300 + i},{700 + i % 11},{9 + i % 4}" for i in range(n)]


SEALED_TAIL = b"\xff\xfe not UTF-8 and not a row: decoding it would fail\r\n" * 3

# name -> (file, header, development lines, first line NOT visible at the cutoff, time column, rule, loader, last served)
CASES = {
    "klines_extra": ("klines_extra_btcusdt_1h_2026-09-20.csv", "as_of,volume,trades,taker_buy_volume", _klines(CUT - 48 * H, 48),
                     f"{CUT.isoformat()},SEALED,SEALED,SEALED", "as_of", H, microstructure.load_klines_extra, CUT - H),
    "funding": ("funding_btcusdt_2026-09-20.csv", "funding_time,funding_rate",
                [f"{(CUT - (7 - i) * 8 * H).isoformat()},0.000{i + 1}" for i in range(8)],  # the last one settles AT the cutoff
                f"{(CUT + timedelta(milliseconds=7)).isoformat()},SEALED", "funding_time", timedelta(0), derivatives.load_funding, CUT),
    "premium": ("premium_btcusdt_1h_2026-09-20.csv", "as_of,open,high,low,close", _hourly(CUT - 48 * H, 48, 4),
                f"{CUT.isoformat()},SEALED,SEALED,SEALED,SEALED", "as_of", H, derivatives.load_premium, CUT - H),
    "onchain": ("onchain_2026-09-20.csv", "day,hashrate,txcount,addr,fees", _days(CUT - 40 * D, 39),  # day D known at D + 30 h
                f"{CUT - D:%Y-%m-%d} 00:00:00+00:00,SEALED,SEALED,SEALED,SEALED", "day", 30 * H, onchain.load_onchain, CUT - 2 * D),
    "difficulty": ("difficulty_adjustments_2026-09-20.csv", "adjusted_at,height,difficulty,change_factor",
                   [f"{(CUT - 20 * D).isoformat()},100,5.0,1.01", f"{(CUT - 6 * D + 3 * H).isoformat()},200,6.0,0.98",
                    f"{CUT.isoformat()},300,7.0,1.02"],
                   f"{(CUT + timedelta(seconds=1)).isoformat()},SEALED,SEALED,SEALED", "adjusted_at", timedelta(0), onchain.load_difficulty, CUT),
}


@pytest.mark.parametrize("name", list(CASES))
def test_each_loader_serves_exactly_the_rows_visible_at_the_last_development_cutoff_and_reads_no_further(isolated, name):
    file, header, lines, first_sealed, column, rule, loader, last_served = CASES[name]
    _register(isolated, name, file, header, lines + [first_sealed], len(lines), column, rule, tail=SEALED_TAIL)
    got = loader()
    assert len(got) == len(lines) and got.index[-1] == pd.Timestamp(last_served)
    dtypes = got.dtypes if got.ndim == 2 else [got.dtype]
    assert all(pd.api.types.is_numeric_dtype(d) for d in dtypes), "a SEALED value was parsed"
    # The bytes after the first sealed row are not UTF-8: had anything decoded them, the load above would have failed.


def test_a_missing_snapshot_fails_closed_and_nothing_is_downloaded_or_substituted(isolated):
    file, header, lines, *_ = CASES["klines_extra"]
    _register(isolated, "klines_extra", file, header, lines, len(lines), "as_of", H)
    (isolated / file).unlink()
    newer = isolated / "klines_extra_btcusdt_1h_2026-10-17.csv"  # a newer file of the same kind is NOT a substitute
    newer.write_bytes((header + "\r\n" + "\r\n".join(lines) + "\r\n").encode())
    with pytest.raises(snapshots.SnapshotError, match="is missing"):
        microstructure.load_klines_extra()
    assert sorted(p.name for p in isolated.iterdir()) == [newer.name], "nothing may be written"


def test_a_changed_or_unexpected_snapshot_is_refused(isolated):
    file, header, lines, first_sealed, *_ = CASES["klines_extra"]
    data = _register(isolated, "klines_extra", file, header, lines + [first_sealed], len(lines), "as_of", H)
    path = isolated / file
    path.write_bytes(data.replace(b",1001,", b",1002,", 1))  # one development value edited after registration
    with pytest.raises(snapshots.SnapshotError, match="not the registered ones"):
        microstructure.load_klines_extra()
    path.write_bytes(data.replace((lines[10] + "\r\n").encode(), b"", 1))  # one development row dropped
    with pytest.raises(snapshots.SnapshotError, match="not the registered ones"):
        microstructure.load_klines_extra()
    path.write_bytes(data.replace(b"as_of,", b"time,", 1))  # another column layout
    with pytest.raises(snapshots.SnapshotError, match="first column"):
        microstructure.load_klines_extra()
    with pytest.raises(snapshots.SnapshotError, match="not a registered snapshot"):
        snapshots.read_snapshot_rows("an_unregistered_dataset")


def test_rows_out_of_time_order_are_refused(isolated):
    file, header, lines, *_ = CASES["klines_extra"]
    swapped = lines[:5] + [lines[6], lines[5]] + lines[7:]
    _register(isolated, "klines_extra", file, header, swapped, len(swapped), "as_of", H)
    with pytest.raises(snapshots.SnapshotError, match="strictly increasing"):
        microstructure.load_klines_extra()
    _register(isolated, "klines_extra", file, header, lines[:3] + [lines[2]] + lines[3:], len(lines) + 1, "as_of", H)
    with pytest.raises(snapshots.SnapshotError, match="strictly increasing"):  # a duplicated hour
        microstructure.load_klines_extra()


def test_rows_past_the_cutoff_need_the_logged_holdout_route_and_then_the_whole_registered_file(isolated, monkeypatch):
    file, header, lines, *_ = CASES["klines_extra"]
    later = _klines(CUT, 30)
    data = _register(isolated, "klines_extra", file, header, lines + later, len(lines), "as_of", H)
    assert len(microstructure.load_klines_extra(CUT - 10 * H)) == len(lines) - 10   # an earlier cutoff serves less
    with pytest.raises(history.HoldoutAccessError):
        microstructure.load_klines_extra(CUT + H)                                   # one hour past it: refused
    with pytest.raises(ValueError, match="timezone"):
        snapshots.read_snapshot_rows("klines_extra", datetime(2025, 6, 1))
    monkeypatch.setattr(history, "_HOLDOUT_OPENED_FOR", "unit test: synthetic file only")  # as load_bars(allow_holdout=True) sets it
    got = microstructure.load_klines_extra(CUT + 10 * H)
    assert len(got) == len(lines) + 10 and got.index[-1] == pd.Timestamp(CUT + 9 * H)
    (isolated / file).write_bytes(data.replace(later[-1].encode(), later[-1].replace(",4", ",3").encode()))  # a sealed row edited
    assert len(microstructure.load_klines_extra()) == len(lines)                  # the development rows are still the registered ones
    with pytest.raises(snapshots.SnapshotError, match="not the registered one"):
        microstructure.load_klines_extra(CUT + 10 * H)                            # but the whole file no longer is


def test_the_refused_macro_snapshot_is_never_opened(isolated):
    snapshots.REGISTERED["macro"] = REAL_REGISTRY["macro"]  # the real entry; its file does not exist in this directory
    with pytest.raises(snapshots.SnapshotError, match="is refused: its rows are not daily closes"):
        macro.load_macro()
    with pytest.raises(snapshots.SnapshotError, match="refused"):
        feature_test.compute_group_features("macro", _bars(CUT - 48 * H, 48))


def _bars(first: datetime, n: int) -> list[PriceBar]:
    return [PriceBar(as_of=first + i * H, open=100.0 + i % 7, high=102.0 + i % 5, low=98.0 - i % 3, close=100.5 + i % 9,
                     volume=10.0 + i % 4, source="binance") for i in range(n)]


def test_the_cut_cannot_change_any_development_feature(isolated, monkeypatch):
    """Serving only the rows visible at the last development cutoff gives every development hour exactly the feature
    values the whole file gives: each feature's own point-in-time rule never looks past that cutoff."""
    _register(isolated, "klines_extra", *CASES["klines_extra"][:2], _klines(CUT - 300 * H, 400), 300, "as_of", H)
    _register(isolated, "premium", *CASES["premium"][:2], _hourly(CUT - 300 * H, 400, 4), 300, "as_of", H)
    funding = [f"{(CUT - (60 - i) * 8 * H).isoformat()},0.0{i % 9 + 1}" for i in range(70)]  # 61 at or before the cutoff
    _register(isolated, "funding", *CASES["funding"][:2], funding, 61, "funding_time", timedelta(0))
    _register(isolated, "onchain", *CASES["onchain"][:2], _days(CUT - 60 * D, 70), 59, "day", 30 * H)
    adjustments = [f"{(CUT - (60 - 14 * i) * D).isoformat()},{i},{5.0 + i},1.0{i}" for i in range(8)]
    _register(isolated, "difficulty", *CASES["difficulty"][:2], adjustments, 5, "adjusted_at", timedelta(0))
    bars = _bars(CUT - 300 * H, 300)  # development candles: the last one closes at the cutoff
    grid = bars_to_frame(bars).index

    def both(load):
        governed = load()
        monkeypatch.setattr(history, "_HOLDOUT_OPENED_FOR", "unit test: synthetic file only")
        whole = load(CUT + 400 * H)
        monkeypatch.setattr(history, "_HOLDOUT_OPENED_FOR", "")
        assert len(whole) > len(governed)  # the whole file really holds rows past the cutoff
        return governed, whole

    extra, extra_all = both(microstructure.load_klines_extra)
    fund, fund_all = both(derivatives.load_funding)
    prem, prem_all = both(derivatives.load_premium)
    daily, daily_all = both(onchain.load_onchain)
    diff, diff_all = both(onchain.load_difficulty)
    pairs = [
        (microstructure.microstructure_features(grid, extra), microstructure.microstructure_features(grid, extra_all)),
        (shape_features(bars_to_frame(bars), extra), shape_features(bars_to_frame(bars), extra_all)),
        (derivatives.derivatives_features(grid, fund, prem), derivatives.derivatives_features(grid, fund_all, prem_all)),
        (onchain.onchain_features(grid, daily, diff), onchain.onchain_features(grid, daily_all, diff_all)),
    ]
    for governed, whole in pairs:
        pd.testing.assert_frame_equal(governed, whole)
        assert governed.iloc[-1].notna().any(), "the comparison must include real values at the last development hour"


@pytest.mark.parametrize("group", ["derivatives", "onchain", "microstructure", "shape", "macro"])
def test_research_routes_ask_for_side_data_up_to_the_candles_own_cutoff(monkeypatch, group):
    asked = []

    def recorder(until):
        asked.append(until)
        raise LookupError("recorded")

    for fn in ("load_funding", "load_premium", "load_macro", "load_onchain", "load_difficulty", "load_klines_extra"):
        monkeypatch.setattr(feature_test, fn, recorder)
    for last_hour in (CUT - H, CUT - 25 * H):
        with pytest.raises(LookupError):
            feature_test.compute_group_features(group, _bars(last_hour - 47 * H, 48))
        assert asked[-1] == last_hour + H


def test_candles_reaching_into_the_holdout_get_no_side_data_unless_it_was_opened(isolated):
    _register(isolated, "klines_extra", *CASES["klines_extra"][:2], _klines(CUT - 48 * H, 60), 48, "as_of", H)
    with pytest.raises(history.HoldoutAccessError):
        feature_test.compute_group_features("microstructure", _bars(CUT - 40 * H, 45))  # four holdout candles
    assert len(feature_test.compute_group_features("microstructure", _bars(CUT - 40 * H, 40))) == 40


def test_the_spot_candles_stop_at_the_holdouts_first_candle_and_are_never_downloaded_or_substituted(isolated):
    lines = [f"{(CUT - (48 - i) * H).isoformat()},100,102,99,{100.5 + 0.5 * (i % 3)},{1 + i % 4}" for i in range(48)]
    _register(isolated, "spot", "btcusdt_1h_2026-09-19.csv", "as_of,open,high,low,close,volume", lines + [f"{CUT.isoformat()},SEALED,SEALED,SEALED,SEALED,SEALED"],
              48, "as_of", H, tail=SEALED_TAIL)
    bars, quality, path = history.load_bars()
    assert len(bars) == 48 and bars[-1].as_of == CUT - H and path == isolated / "btcusdt_1h_2026-09-19.csv"
    assert len(history.load_bars(end=HOLDOUT.end)[0]) == 48  # asking for more is cut at the holdout, and still reads no further
    path.unlink()
    (isolated / "btcusdt_1h_2026-10-17.csv").write_bytes(("as_of,open,high,low,close,volume\r\n" + "\r\n".join(lines) + "\r\n").encode())
    with pytest.raises(snapshots.SnapshotError, match="is missing"):
        history.load_bars()


def test_the_registered_rules_are_each_modules_own_point_in_time_rules():
    assert REAL_REGISTRY["macro"].visible_after == timedelta(hours=macro.AVAILABLE_AT_UTC_HOUR)
    assert REAL_REGISTRY["onchain"].visible_after == onchain.KNOWN_AFTER
    assert REAL_REGISTRY["klines_extra"].visible_after == REAL_REGISTRY["premium"].visible_after == H  # a candle closes 1 h after it opens
    assert REAL_REGISTRY["spot"].visible_after == H
    assert REAL_REGISTRY["funding"].visible_after == REAL_REGISTRY["difficulty"].visible_after == timedelta(0)  # known when stamped
    assert set(REAL_REGISTRY) == {"spot", "klines_extra", "funding", "premium", "onchain", "difficulty", "macro"}
    assert [n for n, s in REAL_REGISTRY.items() if s.refused] == ["macro"]
    assert snapshots.DEVELOPMENT_CUTOFF == HOLDOUT.start


def test_the_live_tracks_need_no_research_snapshot():
    """With no registered snapshot, no data directory and no network, both frozen models still load and verify their
    input definitions: the live inputs never come from the research snapshots."""
    from agent.direction_shadow.model import load_model as load_direction
    from agent.shadow.model import load_model as load_move_size

    load_move_size("move_size_1h_v1", verify_features=True)
    load_direction("direction_1h_v1", verify_features=True)


@pytest.mark.skipif(not (REAL_DATA_DIR / REAL_REGISTRY["klines_extra"].file).exists(), reason="the research snapshots exist only on the research machine")
def test_the_real_snapshots_on_this_machine_are_the_registered_ones_and_loading_never_changes_them(monkeypatch):
    """Development rows only: their count and sha256, plus each file's size and modification time (no byte past the
    last development row is read here)."""
    monkeypatch.setattr(snapshots, "DATA_DIR", REAL_DATA_DIR)
    monkeypatch.setattr(snapshots, "REGISTERED", REAL_REGISTRY)
    for name, snap in REAL_REGISTRY.items():
        path = REAL_DATA_DIR / snap.file
        before = path.stat()
        assert before.st_size == snap.file_bytes, name
        if not snap.refused:
            assert snapshots.read_snapshot_rows(name).count(b"\n") == snap.development_rows + 1, name
        after = path.stat()
        assert (after.st_size, after.st_mtime_ns) == (before.st_size, before.st_mtime_ns), name
