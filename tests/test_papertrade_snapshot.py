"""
Papirhandelens oversiktsdokument («paper-state 1», agent/papertrade/snapshot.py), uten database: forståelige navn på
alle 118 strategier, riktige små regnestykker (fall fra topp, løpende vinduer uten tap, tålmodige ordrer), at
dokumentet stemmer med regnskapsbøkene, at en dag regnes som manglende først etter 6-timersfristen, og at den
oppdiktede demoen er merket og bygget av den ekte motoren.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from agent.papertrade import demo
from agent.papertrade import snapshot as P
from agent.papertrade import strategies as S
from tests.test_papertrade import live_rows

UTC = timezone.utc


def test_every_strategy_gets_a_readable_norwegian_name():
    specs = S.strategy_set(S.daily_frame(*live_rows()))
    names = {n: P.nice_name(n) for n in specs}
    assert all(v != k and "_" not in v for k, v in names.items()), [k for k, v in names.items() if v == k or "_" in v]
    assert len(set(names.values())) == len(names)  # no two accounts share a name
    assert P.nice_name("G_up55_down20") == "Utbrudd 55/20"
    assert P.nice_name("H_BH_tr15") == "Kjøp og hold + glidende stopp 15 %"
    assert P.nice_name("MS_pt-1.0__G_up55_down20__msmore") == "Utbrudd 55/20 · mer ved stor bevegelse"
    assert {P.family(n) for n in specs} == set(P.FAMILY_NAMES)


def test_drawdown_and_rolling_no_loss_windows():
    assert P.max_drawdown([550, 440, 600]) == pytest.approx(0.2)
    assert P.max_drawdown([]) == 0.0
    assert P.no_loss([510, 490, 520], 5) is None
    w = P.no_loss([510, 490, 520], 1)  # 500->510 up, 510->490 down, 490->520 up
    assert w["n"] == 3 and w["share"] == pytest.approx(2 / 3, abs=1e-4)  # rounded to 4 decimals
    assert P.no_loss([500, 500], 1)["share"] == 1.0  # standing still is not a loss (the goal's own definition)


def test_a_patient_order_counts_as_filled_only_when_a_trade_went_through_its_price():
    t0 = datetime(2030, 1, 1, 12, 5, tzinfo=UTC)
    quotes = [{"hour": t0.replace(minute=0), "fetched_at": t0, "bid": 100.0, "ask": 102.0},
              {"hour": t0.replace(minute=0) + timedelta(hours=1), "fetched_at": t0 + timedelta(hours=1),
               "bid": 100.0, "ask": 102.0},
              {"hour": t0.replace(minute=0) + timedelta(hours=5), "fetched_at": t0 + timedelta(hours=5),
               "bid": 100.0, "ask": 102.0}]  # not yet covered by the trade log
    seen = t0 + timedelta(hours=3)
    trades = [{"traded_at": t0 + timedelta(minutes=30), "price": 99.5, "fetched_at": seen},   # under the bid
              {"traded_at": t0 + timedelta(minutes=70), "price": 101.0, "fetched_at": seen},  # inside the spread
              {"traded_at": t0 + timedelta(minutes=200), "price": 103.0, "fetched_at": seen}]  # after both windows
    f = P.passive_fill(quotes, trades)
    assert f == {"hours": 2, "bid_fill_share": 0.5, "ask_fill_share": 0.0, "window_minutes": 60}
    assert P.passive_fill([], trades) is None


def _ledger(day, strategy, book, value, btc=0.0, action="NONE", notional=0.0, fee=0.0, reason=None, active=True):
    return {"day": day, "strategy": strategy, "book": book, "active": active, "action": action, "notional": notional,
            "fee": fee, "cash": value - btc * 100, "btc": btc, "value": value, "reason": reason}


def test_the_document_agrees_with_the_ledgers_and_marks_missing_days_only_after_the_deadline():
    d1, d2, d3 = date(2030, 1, 1), date(2030, 1, 2), date(2030, 1, 4)
    days = [{"day": d, "close": 100.0, "firi_bid": 99.0, "firi_ask": 101.0} for d in (d1, d2, d3)]
    ledger = [_ledger(d1, "BASE_buy_and_hold", "firi", 500, 4.9, "BUY", 500, 3.5, "signal"),
              _ledger(d2, "BASE_buy_and_hold", "firi", 520, 4.9),
              _ledger(d3, "BASE_buy_and_hold", "firi", 480, 4.9),
              _ledger(d1, "BASE_cash", "firi", 500), _ledger(d2, "BASE_cash", "firi", 500),
              _ledger(d3, "BASE_cash", "firi", 500),
              _ledger(d1, "G_up55_down20", "firi", 500, active=False), _ledger(d3, "G_up55_down20", "firi", 505)]
    errors = [{"occurred_at": datetime(2030, 1, 3, 0, 20, tzinfo=UTC), "step": "run", "error_type": "OSError"}]
    now = datetime(2030, 1, 5, 5, 0, tzinfo=UTC)  # 2030-01-04's deadline (01-05 06:00) has not passed
    doc = P.build_document(days, ledger, [], [], errors, now, first_day=d1)
    assert doc["schema"] == P.SCHEMA and doc["days"] == ["2030-01-01", "2030-01-02", "2030-01-04"]
    assert doc["operation"]["missing_days"] == ["2030-01-03"] and doc["operation"]["errors"] == 1
    firi = {a["id"]: a for a in doc["books"]["firi"]["accounts"]}
    bh = firi["BASE_buy_and_hold"]
    assert bh["values"] == [500, 520, 480] and bh["ret"] == pytest.approx(-0.04) and bh["in_btc"]
    assert bh["events"] == [{"day": "2030-01-01", "action": "BUY", "price": 101.0, "amount": 500, "fee": 3.5,
                             "reason": "signal"}]  # a Firi buy is at the ask
    assert bh["max_dd"] == pytest.approx(40 / 520, abs=1e-4)
    assert firi["G_up55_down20"]["values"] == [500, None, 505]
    s = doc["books"]["firi"]["summary"]
    assert s["best"] == ["G_up55_down20"] and "BASE_cash" not in s["best"] + s["worst"]  # baselines are not ranked
    assert (s["in_plus"], s["in_minus"], s["flat"]) == (1, 1, 1) and s["beat_buy_hold"] == 1
    assert doc["books"]["modell"] == {"accounts": [], "summary": None} and doc["market"] is None
    later = P.build_document(days, ledger, [], [], errors, datetime(2030, 1, 6, 7, tzinfo=UTC), first_day=d1)
    assert later["operation"]["missing_days"] == ["2030-01-03", "2030-01-05"]


def test_the_demo_is_fictional_and_made_by_the_real_engine():
    doc = demo.build(days=260, paper_days=20)
    assert doc["fictional"] is True and doc["days"][0].startswith("2030")
    for book in ("firi", "modell"):
        accounts = doc["books"][book]["accounts"]
        assert len(accounts) == 118 and all(len(a["values"]) == 20 for a in accounts)
    cash = next(a for a in doc["books"]["firi"]["accounts"] if a["id"] == "BASE_cash")
    assert set(cash["values"]) == {500.0} and cash["trades"] == 0
    assert doc["market"]["passive"] is not None and len(doc["market"]["spread_by_hour_utc"]) == 24


def test_the_committed_demo_page_data_is_fictional_and_in_the_current_format():
    import json
    from pathlib import Path
    doc = json.loads(Path("web/papir/demo.json").read_text(encoding="utf-8"))
    assert doc["fictional"] is True and doc["schema"] == P.SCHEMA and doc["note"].startswith("OPPDIKTET")
    assert all(d.startswith(("2030", "2031")) for d in doc["days"])  # never a real date
    for f in ("index.html", "app.js", "charts.js", "data.js"):  # no outside scripts or hosts in the page
        src = Path("web/papir", f).read_text(encoding="utf-8")
        assert "supabase.co" not in src and "<script src=\"http" not in src, f
