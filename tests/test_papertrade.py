"""
Papirhandelen (E042), bare på syntetiske data og uten database: 118 strategier med riktige navn og inndata, daglige
data som er punkt i tid, beslutninger for begge regnskapsbøkene (Firi-boken bare med en gyldig kurs), at den bare
skriver i sine egne tabeller, og at den aldri bruker utførelseslaget eller en research-loader.
"""

import ast
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from agent.papertrade import run as R
from agent.papertrade import strategies as S

T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)


def live_rows(days=90, seed=3, change_after=None):
    rng = np.random.default_rng(seed)
    n = days * 24
    close = 30_000 * np.exp(np.cumsum(rng.normal(0, 0.006, n)))
    sig = rng.choice(["BUY", "HOLD", "SELL"], size=n)
    score = rng.normal(0, 0.2, n)
    p = rng.uniform(0.2, 0.6, n)
    if change_after is not None:
        close[change_after:] *= 1.5
        sig[change_after:] = "SELL"
        p[change_after:] = 0.9
    pred = [(T0 + timedelta(hours=h), close[h], sig[h], score[h]) for h in range(n)]
    shadow = [(T0 + timedelta(hours=h), p[h]) for h in range(n)]
    return pred, shadow


def test_the_registered_set_has_118_strategies_and_every_one_reports_its_inputs():
    pred, shadow = live_rows()
    df = S.daily_frame(pred, shadow)
    specs = S.strategy_set(df)
    assert len(specs) == 118 and S.STRATEGY_SET == "pt-1.0"
    assert sum(1 for n in specs if n.startswith("MS_")) == 12 and {"BASE_buy_and_hold", "BASE_cash"} <= set(specs)
    for name in specs:
        S.active(df, name, len(df) - 1)  # must not raise for any name
    assert S.active(df, "G_up55_down20", len(df) - 1) and not S.active(df, "B_MA200", len(df) - 1)


def test_the_daily_frame_is_point_in_time():
    cut_day = 60
    a = S.daily_frame(*live_rows())
    b = S.daily_frame(*live_rows(change_after=(cut_day + 1) * 24))
    cols = ["close", "R7", "R28", "MA20", "SIGMA30", "sig23", "vote", "pbar", "HI55", "LO20", "calm"]
    x, y = a[cols].iloc[: cut_day + 1], b[cols].iloc[: cut_day + 1]
    assert ((x == y) | (x.isna() & y.isna())).all().all()


def test_decisions_for_both_books_and_none_for_firi_without_a_quote():
    df = S.daily_frame(*live_rows())
    specs = S.strategy_set(df)
    i = len(df) - 1
    without = R.decide_day(df, specs, i, {}, None)
    assert {r["book"] for r in without} == {"modell"} and len(without) == 118
    quote = (300_000.0, 303_000.0, datetime.now(timezone.utc))
    rows = R.decide_day(df, specs, i, {}, quote)
    assert len(rows) == 236
    bh = {r["book"]: r for r in rows if r["strategy"] == "BASE_buy_and_hold"}
    assert bh["firi"]["action"] == "BUY" and bh["firi"]["btc"] == pytest.approx(500 * (1 - 0.007) / 303_000.0)
    assert bh["modell"]["btc"] == pytest.approx(500 * (1 - 0.0125) / df["close"].iat[i])
    cash = [r for r in rows if r["strategy"] == "BASE_cash"]
    assert all(r["value"] == 500.0 and r["action"] == "NONE" for r in cash)


def test_a_bad_firi_quote_is_refused():
    class Resp:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    ok, err = R.firi_quote(get=lambda *a, **k: Resp({"bid": "600000", "ask": "606000"}))
    assert ok[:2] == (600000.0, 606000.0) and err is None
    for bad in ({"bid": "606000", "ask": "600000"}, {"bid": "100", "ask": "600000"}, {"bid": "x"}):
        q, err = R.firi_quote(get=lambda *a, **k: Resp(bad))
        assert q is None and err


def _sql_targets(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"(?:INSERT INTO|UPDATE|DELETE FROM)\s+(\w+)", text))


def test_paper_trading_writes_only_its_own_tables_and_never_touches_execution_or_research_loaders():
    for f in Path("agent/papertrade").glob("*.py"):
        assert _sql_targets(f) <= {"paper_days", "paper_ledger", "paper_errors"}, f
        tree = ast.parse(f.read_text(encoding="utf-8"))
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not any(m.startswith("agent.execution") for m in mods), f
        called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                  for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not called & {"load_bars", "read_snapshot_rows", "read_snapshot_frame", "compute_group_features",
                             "build_frame", "load", "load_development", "_registered_replay"}, f


def test_the_hourly_job_can_never_fail_because_of_paper_trading(monkeypatch):
    def boom():
        raise RuntimeError("database down")

    monkeypatch.setattr(R, "run_once", boom)
    monkeypatch.setattr(R, "record_error", lambda *a, **k: None)
    assert R.main([]) == 0


def test_a_day_is_traded_only_within_six_hours_of_its_close():
    import pandas as pd
    day = pd.Timestamp("2030-01-05", tz="UTC")
    close_at = datetime(2030, 1, 6, tzinfo=timezone.utc)
    assert not R.too_late(day, close_at + timedelta(minutes=13))
    assert not R.too_late(day, close_at + timedelta(hours=6))
    assert R.too_late(day, close_at + timedelta(hours=6, seconds=1))
