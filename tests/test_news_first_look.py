"""
E030, the news first look (roadmap 8.6): the computation is exactly what E025 and E030's registration fixed, on
synthetic data (no database). The live run reads the real record once; these tests pin that it can only read
the registered hours, cannot pick its window, and cannot be rewritten.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

import agent.research.news_first_look as nfl

T0 = datetime(2026, 9, 19, 20, tzinfo=timezone.utc)
H = timedelta(hours=1)


def _data(n: int, rho: float = 0.0, seed: int = 3, missing: tuple = ()):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    news = [(T0 + i * H, float(v)) for i, v in enumerate(x)]
    returns = {}
    for h in nfl.HORIZONS:
        y = rho * x + np.sqrt(1 - rho ** 2) * rng.normal(size=n)
        returns.update({(T0 + i * H, h): float(v) for i, v in enumerate(y) if i not in missing})
    return news, returns


def test_the_registered_parameters_are_the_ones_used():
    assert (nfl.FIRST_LOOK_HOURS, nfl.VERDICT_HOURS, nfl.HORIZONS, nfl.PRIMARY) == (500, 3140, (1, 6, 24), 1)
    assert (nfl.BLOCK, nfl.N_BOOT, nfl.SEED) == (48, 500, 17)
    reg = json.loads(Path("research/experiments/E030_news_first_look.json").read_text(encoding="utf-8"))
    assert "seed 17" in reg["method"]["interval"] and "500 resamples" in reg["method"]["interval"]
    assert "FIRST 500 usable news hours" in reg["method"]["hours"]


def test_it_uses_exactly_the_first_500_usable_hours_and_ignores_later_ones():
    news, returns = _data(700)
    r = nfl.first_look(news, returns)
    assert r["hours"]["n"] == 500 and r["hours"]["usable_available"] == 700
    assert r["hours"]["last"] == (T0 + 499 * H).isoformat()
    # later hours cannot move the reading: rewrite everything after the prefix, the result is identical
    later = {k: (v if k[0] <= T0 + 499 * H else 99.0) for k, v in returns.items()}
    assert nfl.first_look(news[:500] + [(t, -9.0) for t, _ in news[500:]], later) == r


def test_it_refuses_to_look_early_or_on_disordered_hours():
    news, returns = _data(499)
    with pytest.raises(ValueError, match="registered at 500"):
        nfl.first_look(news, returns)
    news, returns = _data(600)
    with pytest.raises(ValueError, match="time order"):
        nfl.first_look([news[1], news[0]] + news[2:], returns)


def test_an_hour_without_an_ok_outcome_is_left_out_and_counted():
    news, returns = _data(520, missing=(3, 40, 41))
    r = nfl.first_look(news, returns)
    for h in ("1h", "6h", "24h"):
        assert r["horizons"][h]["n"] == 497 and r["horizons"][h]["left_out_without_ok_outcome"] == 3


def test_no_effect_reads_near_zero_and_a_planted_effect_is_recovered():
    none = nfl.first_look(*_data(500, rho=0.0))["horizons"]["1h"]
    strong = nfl.first_look(*_data(500, rho=0.4))["horizons"]["1h"]
    assert abs(none["rho"]) < 0.12
    assert 0.3 < strong["rho"] < 0.5 and strong["interval_excludes_zero"]
    assert strong["ci95"][0] < strong["rho"] < strong["ci95"][1]


def test_the_result_is_reproducible_and_never_a_verdict():
    a, b = nfl.first_look(*_data(500, rho=0.1)), nfl.first_look(*_data(500, rho=0.1))
    assert a == b and a["verdict"] is None
    assert a["horizons"]["1h"]["role"] == "primary"
    assert {a["horizons"][h]["role"] for h in ("6h", "24h")} == {"descriptive only"}


def test_the_report_says_first_look_no_verdict_and_what_the_size_can_see():
    r = nfl.first_look(*_data(500))
    md = nfl._md(r, datetime(2026, 10, 14, 15, tzinfo=timezone.utc))
    assert "NO verdict" in md and "No verdict, by registration" in md and "0.125" in md and "about 9%" in md


def test_it_writes_once_and_refuses_to_overwrite(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(nfl, "OUT_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(nfl, "_read", lambda: calls.append(1) or _data(500))
    assert nfl.main(["--experiment", "E030"]) == 0 and len(calls) == 1
    first = (tmp_path / "news_first_look.json").read_text(encoding="utf-8")
    assert nfl.main(["--experiment", "E030"]) == 0
    assert len(calls) == 1, "the second run must not even read the database"
    assert (tmp_path / "news_first_look.json").read_text(encoding="utf-8") == first
    assert "already computed" in capsys.readouterr().out


def test_it_reads_only_ok_outcomes_of_the_prefix_and_uses_e025s_own_news_query():
    from agent.research.news_power import NEWS_SQL

    assert nfl.NEWS_SQL is NEWS_SQL
    sql = " ".join(nfl.OUTCOME_SQL.split())
    assert "o.status = 'ok'" in sql and "p.as_of = ANY(%s)" in sql
    src = Path("agent/research/news_first_look.py").read_text(encoding="utf-8")
    assert "conn.read_only = True" in src and "news[:FIRST_LOOK_HOURS]" in src
    assert "agent.reporting" not in src, "research must not import the reporting layer"
