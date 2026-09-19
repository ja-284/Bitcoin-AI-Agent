"""
Provider failure behaviour: an exception OR invalid data from the primary provider
must trigger the fallback; if every provider fails, the run must fail loudly rather
than continue on nothing.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import agent.data_providers.market_data as md
from agent.shared.types import PriceBar

START = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _bars(n: int, source: str) -> list[PriceBar]:
    return [PriceBar(START + timedelta(hours=i), 100.0, 101.0, 99.0, 100.5, 5.0, source) for i in range(n)]


class Provider:
    def __init__(self, name, bars=None, error=None):
        self.name, self.bars, self.error = name, bars, error
        self.calls = 0

    def get_hourly_bars(self, count):
        self.calls += 1
        if self.error:
            raise self.error
        return self.bars


def test_primary_exception_falls_back(monkeypatch):
    primary = Provider("primary", error=ConnectionError("down"))
    backup = Provider("backup", bars=_bars(10, "backup"))
    monkeypatch.setattr(md, "_PROVIDERS", [primary, backup])
    market = md.get_market_data(10)
    assert market.provider == "backup" and primary.calls == 1 and backup.calls == 1


def test_primary_invalid_data_falls_back(monkeypatch):
    bad = _bars(10, "primary")
    bad[5] = replace(bad[5], high=1.0)  # impossible: high below low
    primary = Provider("primary", bars=bad)
    backup = Provider("backup", bars=_bars(10, "backup"))
    monkeypatch.setattr(md, "_PROVIDERS", [primary, backup])
    assert md.get_market_data(10).provider == "backup"


def test_primary_empty_falls_back(monkeypatch):
    monkeypatch.setattr(md, "_PROVIDERS", [Provider("primary", bars=[]), Provider("backup", bars=_bars(10, "backup"))])
    assert md.get_market_data(10).provider == "backup"


def test_all_providers_failing_raises(monkeypatch):
    monkeypatch.setattr(md, "_PROVIDERS", [Provider("a", error=ValueError("x")), Provider("b", bars=[])])
    with pytest.raises(RuntimeError, match="All market data providers failed"):
        md.get_market_data(10)


def test_gaps_are_reported_not_fatal(monkeypatch):
    bars = _bars(10, "primary")
    del bars[4]  # one missing hour
    monkeypatch.setattr(md, "_PROVIDERS", [Provider("primary", bars=bars)])
    market = md.get_market_data(10)
    assert market.quality.missing_hours == 1 and len(market.bars) == 9
