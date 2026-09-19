"""
The orchestrator must derive one explicit cutoff from the reference candle, hand that
exact cutoff to the news step, and stamp it on the prediction. No network, no AI, no
database: every outside dependency is replaced with a stand-in that records what it
was asked.
"""

from datetime import datetime, timedelta, timezone

import agent.orchestrator as orch
from agent.news.news_service import NewsResult
from agent.shared.types import CategoryScore, PriceBar

START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _bars(n: int) -> list[PriceBar]:
    bars = []
    price = 60_000.0
    for i in range(n):
        price *= 1.0005
        bars.append(PriceBar(START + timedelta(hours=i), price, price * 1.001, price * 0.999, price, 100.0, "test"))
    return bars


def test_cutoff_is_reference_candle_close_and_reaches_news_and_prediction(monkeypatch):
    bars = _bars(orch.HISTORY_HOURS)
    seen = {}

    def fake_news(cutoff):
        seen["news_cutoff"] = cutoff
        return NewsResult(items=[], cutoff=cutoff, sources_attempted=3)

    monkeypatch.setattr(orch, "get_hourly_bars", lambda n: bars)
    monkeypatch.setattr(orch, "prediction_exists", lambda as_of: False)
    monkeypatch.setattr(orch, "get_recent_news", fake_news)
    monkeypatch.setattr(orch.news_scorer, "score_news", lambda items: CategoryScore("news", 0.0, 0.0, True, {}))
    monkeypatch.setattr(orch.explainer, "write_explanation", lambda **kwargs: "explanation")

    prediction = orch.run_once(save=False)

    expected_cutoff = bars[-1].as_of + timedelta(hours=1)
    assert seen["news_cutoff"] == expected_cutoff
    assert prediction.cutoff_at == expected_cutoff
    assert prediction.as_of == bars[-1].as_of
    assert prediction.run_meta["lag_seconds_after_cutoff"] == (prediction.fetched_at - expected_cutoff).total_seconds()
    assert prediction.run_meta["news"]["cutoff"] == expected_cutoff.isoformat()
    assert prediction.pipeline_version == orch.PIPELINE_VERSION


def test_existing_prediction_short_circuits_before_any_ai_call(monkeypatch):
    bars = _bars(orch.HISTORY_HOURS)
    calls = {"news": 0, "explain": 0}

    monkeypatch.setattr(orch, "get_hourly_bars", lambda n: bars)
    monkeypatch.setattr(orch, "prediction_exists", lambda as_of: True)
    monkeypatch.setattr(orch, "get_recent_news", lambda cutoff: calls.__setitem__("news", calls["news"] + 1))
    monkeypatch.setattr(orch.news_scorer, "score_news", lambda items: calls.__setitem__("news", calls["news"] + 1))
    monkeypatch.setattr(orch.explainer, "write_explanation", lambda **kw: calls.__setitem__("explain", 1))

    assert orch.run_once(save=True) is None
    assert calls == {"news": 0, "explain": 0}
