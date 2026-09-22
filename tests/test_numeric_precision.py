"""
Numeric precision of the research record.

Found on 2026-09-22 while checking an E016 claim: pandas' DEFAULT CSV float parser is not
bit-exact. Reading the replay cache with it loses up to ~7e-12 on a price-level value, which is
harmless for any conclusion but is enough to make two identical computations look different --
and it did: an apparent 1.46e-11 "difference" between scoring 0.1.0 and 0.2.0 on clean hours was
entirely the reader, the true difference being zero.

So the rule is: numbers written by this project must come back exactly. Either read with the csv
module (what read_replay does) or pass float_precision="round_trip".
"""

import csv
from pathlib import Path

import pandas as pd
import pytest

from agent.research.replay import read_replay, write_replay

AWKWARD = [
    49179.656173065796,  # a real sma_long value from the replay
    84.20685611933961,  # a real RSI value
    1 / 3,
    0.1 + 0.2,
    1.2345678901234567e-8,
    -0.0000000000000001,
    1e300,
]


def _row(value: float) -> dict:
    return {
        "as_of": "2026-01-01T00:00:00+00:00", "cutoff_at": "2026-01-01T01:00:00+00:00", "close": value,
        "window_missing_hours": 0, "overall_score": value / 1e6, "signal": "HOLD", "confidence": 0.5,
        "agreement": 0.5, "completeness": 1.0, "trend_independent": False, "ind_sma_long": value,
    }


def test_the_projects_own_reader_round_trips_exactly(tmp_path: Path):
    rows = [_row(v) for v in AWKWARD]
    path = tmp_path / "replay_test.csv"
    write_replay(rows, path)
    back = read_replay(path)
    assert len(back) == len(rows)
    for original, restored in zip(rows, back):
        assert restored["close"] == original["close"], "a value did not survive the write/read cycle"
        assert restored["ind_sma_long"] == original["ind_sma_long"]
        assert restored["trend_independent"] is False


def test_pandas_default_parser_is_not_exact_and_round_trip_is(tmp_path: Path):
    """The reason the rule exists -- if pandas ever fixes this, the test says so rather than rotting."""
    path = tmp_path / "values.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["v"])
        w.writeheader()
        w.writerows([{"v": v} for v in AWKWARD])
    exact = pd.read_csv(path, float_precision="round_trip")["v"].tolist()
    assert exact == AWKWARD, "float_precision='round_trip' must be exact"
    default = pd.read_csv(path)["v"].tolist()
    if default != AWKWARD:
        worst = max(abs(a - b) / max(abs(a), 1e-300) for a, b in zip(AWKWARD, default))
        assert worst < 1e-10  # small, but not zero: exactly why the loaders pass round_trip


def test_every_research_loader_reads_exactly():
    """Any CSV loader in agent/research must be bit-exact, by using round_trip or the csv module."""
    import inspect

    from agent.research import derivatives, macro, microstructure, onchain, replay

    for module in (derivatives, macro, microstructure, onchain):
        source = inspect.getsource(module)
        for line in source.splitlines():
            if "read_csv(" in line:
                assert 'float_precision="round_trip"' in line, f"{module.__name__}: {line.strip()}"
    assert "csv.DictReader" in inspect.getsource(replay.read_replay)
