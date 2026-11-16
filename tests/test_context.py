"""
Markedskonteksten (agent/context, retningsplanen kandidat B), uten nett og uten database: hver kilde tolkes riktig
fra et eksempel på svaret, likvidasjoner telles bare i forrige hele time og uten dobbelttelling, opsjonene oppsummeres
riktig, ordreboken får riktige bånd, én kilde som feiler stopper ikke de andre, hver rad er liten nok, steget kan aldri
feile, og det skriver bare i sine egne tabeller og bruker aldri utførelseslaget eller en research-loader.
"""

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.context import run as R
from agent.context import sources as S

UTC = timezone.utc
HOUR = 3_600_000
T = int(datetime(2030, 1, 1, 12, tzinfo=UTC).timestamp() * 1000)  # klokketimen 12:00


def _liq(ts, side, sz="1"):
    return {"ts": str(ts), "posSide": side, "side": "sell" if side == "long" else "buy", "sz": sz, "bkPx": "60000"}


def test_liquidations_are_counted_only_in_the_previous_whole_hour_and_never_twice():
    p1 = {"data": [{"details": [_liq(T + 60_000, "long"), _liq(T - 60_000, "long", "2"), _liq(T - 120_000, "short", "5")]}]}
    p2 = {"data": [{"details": [_liq(T - 120_000, "short", "5"),  # the same liquidation again on the next page
                                _liq(T - HOUR + 1, "long", "3"), _liq(T - HOUR - 1, "short", "7")]}]}
    s = S.summarize_liquidations([p1, p2], T - HOUR, T)
    assert (s["long_count"], s["long_contracts"], s["short_count"], s["short_contracts"]) == (2, 5.0, 1, 5.0)
    assert s["complete"] is True and s["window"] == [T - HOUR, T]
    assert S.summarize_liquidations([p1], T - HOUR, T)["complete"] is False  # did not reach the start: a minimum


def test_okx_pages_back_only_until_the_hour_is_covered():
    pages = [{"data": [{"details": [_liq(T - 1000, "long")]}]},
             {"data": [{"details": [_liq(T - HOUR - 5, "short")]}]},
             {"data": [{"details": [_liq(T - 3 * HOUR, "short")]}]}]
    calls = []

    def get(url):
        calls.append(url)
        if "liquidation-orders" in url:
            return pages[sum("liquidation-orders" in c for c in calls) - 1]
        if "funding-rate" in url:
            return {"data": [{"fundingRate": "0.0001", "settFundingRate": "0.00008", "premium": "-0.0002",
                              "fundingTime": str(T + 4 * HOUR), "ts": str(T + 1000)}]}
        if "open-interest?" in url:
            return {"data": [{"oi": "100", "oiCcy": "1", "oiUsd": "60000", "ts": str(T + 1000)}]}
        if "long-short" in url:
            return {"data": [[str(T), "2.5"], [str(T - HOUR), "2.6"], [str(T - 2 * HOUR), "2.7"]]}
        return {"data": [[str(T), "1e9", "2e8"], [str(T - HOUR), "1.1e9", "2.1e8"]]}

    d = S.fetch_okx(get, T)
    assert sum("liquidation-orders" in c for c in calls) == 2  # the second page reached past the start; no third
    assert f"after={T - 1000}" in [c for c in calls if "liquidation-orders" in c][1]
    assert d["liquidations_prev_hour"]["complete"] and d["long_short_accounts_1h"] == [[T, 2.5], [T - HOUR, 2.6]]
    assert d["funding"]["rate"] == 0.0001 and d["open_interest"]["usd"] == 60000.0 and d["contract_btc"] == 0.01


def _opt(name, und, iv, oi=10.0, vol=100.0):
    return {"instrument_name": name, "underlying_price": und, "mark_iv": iv, "open_interest": oi, "volume_usd": vol}


def test_the_options_are_summarised_into_fear_at_two_horizons():
    now = datetime(2030, 1, 1, 12, tzinfo=UTC)
    rows = [_opt("BTC-2JAN30-60000-C", 60000, 50),                        # 0.8 days away: too near, skipped
            _opt("BTC-4JAN30-60000-C", 60000, 48), _opt("BTC-4JAN30-60000-P", 60000, 52, oi=30),
            _opt("BTC-4JAN30-54000-P", 60000, 70, oi=20), _opt("BTC-4JAN30-66000-C", 60000, 45),
            _opt("BTC-31JAN30-60000-C", 61000, 40), _opt("BTC-31JAN30-55000-P", 61000, 47),
            _opt("BTC-31JAN30-67000-C", 61000, 38), _opt("BTC-PERPETUAL", 60000, 1)]
    o = S.summarize_options(rows, now)
    near, d30 = o["near"], o["d30"]
    assert near["expiry"] == "4JAN30" and near["atm_iv"] == 50.0 and (near["put90_iv"], near["call110_iv"]) == (70, 45)
    assert near["skew"] == 25 and (near["put_oi"], near["call_oi"]) == (50.0, 20.0)
    assert d30["expiry"] == "31JAN30" and d30["skew"] == 9 and round(d30["days"], 3) == 29.833
    assert o["totals"]["put_oi"] == 60.0 and o["totals"]["call_volume_usd"] == 500.0  # the perpetual is not an option


def test_the_order_book_bands_and_how_far_the_book_reached():
    depth = {"lastUpdateId": 7, "bids": [["99.95", "10"], ["99.6", "10"], ["98.0", "10"]],
             "asks": [["100.05", "10"], ["100.4", "10"], ["101.5", "10"]]}
    b = S.parse_book(depth)
    assert b["mid"] == 100.0 and b["spread_bps"] == 10.0 and b["reach"] == [0.02, 0.015]
    assert b["bid_usd_0.001"] == 999.5 and b["bid_usd_0.005"] == 999.5 + 996.0 and b["ask_usd_0.02"] == 1000.5 + 1004.0 + 1015.0


def test_kraken_hyperliquid_and_bitfinex_keep_only_the_bitcoin_fields():
    k = S.parse_kraken({"tickers": [{"symbol": "PF_ETHUSD", "openInterest": 1},
                                    {"symbol": "PF_XBTUSD", "relativeFundingRate": 1e-5, "openInterest": 2000, "extra": "x"}]})
    assert k["openInterest"] == 2000 and k["relativeFundingRate"] == 1e-5 and "extra" not in k
    h = S.parse_hyperliquid([{"universe": [{"name": "ETH"}, {"name": "BTC"}]},
                             [{"funding": "0.1"}, {"funding": "0.0000125", "openInterest": "37000", "markPx": "65000"}]])
    assert h["funding"] == 0.0000125 and h["openInterest"] == 37000.0 and h["premium"] is None
    status = [["tBTCF0:USTF0", 1, None, 65000.0, 64990.0, None, 1.0, None, 2, 0.0002, 3, None, 0.00016, None, None,
               64995.0, None, None, 8800.0, None, None, None, 0.0005, 0.0025]]
    f = S.parse_bitfinex(status, [5, 90000.0], [5, 150.0])
    assert (f["open_interest"], f["current_funding"], f["mark_price"]) == (8800.0, 0.00016, 64995.0)
    assert f["margin_longs_btc"] == [5, 90000.0] and f["margin_shorts_btc"] == [5, 150.0]


def test_one_failing_source_does_not_stop_the_others_and_a_slow_step_stops_trying(monkeypatch):
    def fake(get, post, now):
        def boom():
            raise ConnectionError("blocked")
        return {"okx": boom, "kraken": lambda: {"a": 1}}

    monkeypatch.setattr(S, "fetchers", fake)
    rows, errors = R.collect(["okx", "kraken"], datetime(2030, 1, 1, tzinfo=UTC))
    assert [r[0] for r in rows] == ["kraken"] and [(s, type(e).__name__) for s, e in errors] == [("okx", "ConnectionError")]
    rows, errors = R.collect(["okx", "kraken"], datetime(2030, 1, 1, tzinfo=UTC), deadline=-1)
    assert rows == [] and all(isinstance(e, TimeoutError) for _, e in errors)


def test_every_row_stays_far_below_the_size_limit_even_with_a_big_options_market():
    now = datetime(2030, 1, 1, 12, tzinfo=UTC)
    rows = [_opt(f"BTC-{d}JAN30-{k}-{c}", 60000, 50) for d in range(3, 31) for k in range(30000, 90000, 1000) for c in "CP"]
    dvol = {"result": {"data": [[1, 2, 3, 4, 5]] * 4}}
    perp = {"result": {"timestamp": 1, "current_funding": 0.0, "funding_8h": 1e-4, "open_interest": 7e8,
                       "mark_price": 6e4, "index_price": 6e4}}
    d = S.parse_deribit(dvol, perp, {"result": rows}, now)
    assert len(json.dumps(d)) < 2000 and len(rows) > 3000  # schema limit: 8000 bytes per row


def test_the_hourly_job_can_never_fail_because_of_the_market_context(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("database down")

    monkeypatch.setattr(R, "run_once", boom)
    assert R.main([]) == 0


def test_it_writes_only_its_own_tables_and_never_touches_execution_or_research_loaders():
    for f in Path("agent/context").glob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert set(re.findall(r"(?:INSERT INTO|(?<!DO )UPDATE|DELETE FROM)\s+(\w+)", text)) <= {"context_hourly", "context_errors"}, f
        tree = ast.parse(text)
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m.startswith(("agent.execution", "agent.research", "agent.papertrade", "agent.shadow",
                                     "agent.direction_shadow")) for m in mods), (f, mods)
    wf = Path(".github/workflows/hourly.yml").read_text(encoding="utf-8")
    assert "python -m agent.context.run" in wf
    step = wf.split("- name: Market context (research data)")[1].split("- name:")[0]
    assert "continue-on-error" not in step  # it never fails by itself (tested above); only the heartbeats carry it


def test_the_sources_match_the_schema_list():
    sql = Path("agent/context/schema.sql").read_text(encoding="utf-8")
    listed = re.search(r"source IN \(([^)]*)\)", sql).group(1)
    assert sorted(re.findall(r"'(\w+)'", listed)) == sorted(S.SOURCES)
    assert set(S.fetchers(None, None, datetime(2030, 1, 1, tzinfo=UTC))) == set(S.SOURCES)
