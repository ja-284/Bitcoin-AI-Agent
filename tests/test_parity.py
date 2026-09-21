"""
Backend Phase A: live / research parity.

- The comparison detects any drift between a stored live row and the replay of the same hour
  (a perturbed close, indicator, category score, weight, or overall score is a break).
- Rows the replay cannot judge (fallback data, another pipeline version, no full window) are
  skipped explicitly, never silently passed.
- The live outcome tracker and the research label builder agree on the target candle and the
  return, including across a gap (unavailable on both sides, never a neighbour).
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from agent.indicators.engine import HISTORY_HOURS
from agent.outcome_tracker import target_candle_open
from agent.research.labels import LabelSpec, make_labels
from agent.research.parity import check, compare_hour, overall_without_news
from agent.research.replay import analyze_window_detailed
from agent.shared.types import PriceBar
from agent.version import PIPELINE_VERSION

START = datetime(2026, 3, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def _bars(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    close = 50000 * np.exp(np.cumsum(rng.normal(0, 0.004, size=n)))
    out = []
    for i in range(n):
        c = float(close[i])
        o = float(close[i - 1]) if i else c
        out.append(PriceBar(START + i * HOUR, o, max(o, c) * 1.001, min(o, c) * 0.999, c, float(abs(rng.normal(100, 20))), "binance"))
    return out


def _live_row_from_replay(bars, i: int) -> dict:
    """What the live job would have stored for hour i, built from the replay so it is exact by construction."""
    rep = analyze_window_detailed(bars[i + 1 - HISTORY_HOURS : i + 1])
    cats = [{"name": n, "score": rep[f"{n}_score"], "weight": rep[f"{n}_weight"], "is_independent": rep[f"{n}_independent"], "detail": {}}
            for n in ("trend", "momentum", "volume", "chart_pattern")]
    cats.append({"name": "news", "score": 0.3, "weight": 0.15, "is_independent": True, "detail": {}})  # live had news; the replay does not
    ind = {k[4:]: v for k, v in rep.items() if k.startswith("ind_")}
    return {"as_of": bars[i].as_of, "close_price": rep["close"], "category_scores": cats, "raw_indicators": ind,
            "price_is_synthetic": False, "pipeline_version": PIPELINE_VERSION}


def test_exact_live_rows_pass_and_every_perturbation_breaks():
    bars = _bars(HISTORY_HOURS + 30)
    rows = [_live_row_from_replay(bars, i) for i in range(HISTORY_HOURS - 1, len(bars))]
    res = check(rows, bars)
    assert res["verdict"] == "PARITY" and res["compared"] == len(rows) and res["parity_breaks"] == 0
    rep = analyze_window_detailed(bars[-HISTORY_HOURS:])
    base = rows[-1]
    for mutate, field in (
        (lambda r: r.update(close_price=r["close_price"] * 1.0001), "close_price"),
        (lambda r: r["raw_indicators"].update(rsi=r["raw_indicators"]["rsi"] + 0.01), "indicator.rsi"),
        (lambda r: r["category_scores"][1].update(score=r["category_scores"][1]["score"] + 1e-3), "category.momentum.score"),
        (lambda r: r["category_scores"][0].update(weight=0.3), "category.trend.weight"),
    ):
        row = {**base, "raw_indicators": dict(base["raw_indicators"]), "category_scores": [dict(c) for c in base["category_scores"]]}
        mutate(row)
        out = compare_hour(row, rep)
        assert not out["ok"] and any(m[0].startswith(field) for m in out["mismatches"]), field


def test_news_is_removed_before_the_overall_score_is_compared():
    bars = _bars(HISTORY_HOURS + 5)
    row = _live_row_from_replay(bars, len(bars) - 1)
    rep = analyze_window_detailed(bars[-HISTORY_HOURS:])
    assert overall_without_news(row["category_scores"]) == pytest.approx(rep["overall_score"], rel=1e-9)


def test_unjudgeable_rows_are_skipped_explicitly():
    bars = _bars(HISTORY_HOURS + 10)
    ok = _live_row_from_replay(bars, len(bars) - 1)
    synthetic = {**_live_row_from_replay(bars, len(bars) - 2), "price_is_synthetic": True}
    other_pipeline = {**_live_row_from_replay(bars, len(bars) - 3), "pipeline_version": "0.1.0"}
    early = {**ok, "as_of": bars[5].as_of}  # no full window before it
    res = check([ok, synthetic, other_pipeline, early], bars)
    assert res["compared"] == 1 and res["parity_breaks"] == 0
    reasons = [r for _, r in res["skipped"]]
    assert "live row used fallback (synthetic) data" in reasons and "pipeline version differs" in reasons and "no full candle window available" in reasons


def test_live_tracker_and_research_labels_agree_on_target_and_return_across_a_gap():
    bars = _bars(400, seed=3)
    del bars[300:303]  # three missing hours
    for h in (1, 6, 24):
        lab = make_labels(bars, LabelSpec(h, "binary")).set_index("as_of")
        for i in range(250, 380):
            as_of = bars[i].as_of
            target = target_candle_open(as_of, h)  # the live rule
            by_time = {b.as_of: b for b in bars}
            if target in by_time:
                live_ret = (by_time[target].close - bars[i].close) / bars[i].close
                assert lab.loc[as_of, "ret"] == pytest.approx(live_ret, rel=1e-12), (h, as_of)
            else:
                assert np.isnan(lab.loc[as_of, "ret"]), (h, as_of)  # research: no label; live: 'unavailable', never a neighbour
