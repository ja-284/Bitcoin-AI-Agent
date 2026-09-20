"""
X4 (E009): the explanation model has no influence on the decision. Whatever it returns
-- even text arguing for a different signal -- and even if it fails, the signal, score
and confidence are identical. No network: every outside dependency is a stand-in.
"""

from datetime import datetime, timedelta, timezone

import agent.orchestrator as orch
from agent.data_providers.market_data import MarketData
from agent.data_providers.quality import validate_bars
from agent.news.news_service import NewsResult
from agent.shared.types import CategoryScore, PriceBar

START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _bars(n: int) -> list[PriceBar]:
    bars, price = [], 60_000.0
    for i in range(n):
        price *= 1.0007
        bars.append(PriceBar(START + timedelta(hours=i), price, price * 1.001, price * 0.999, price, 100.0, "test"))
    return bars


def _run(monkeypatch, explanation_behaviour):
    bars = _bars(orch.HISTORY_HOURS)
    monkeypatch.setattr(orch, "get_market_data", lambda n: MarketData(bars=bars, quality=validate_bars(bars), provider="test"))
    monkeypatch.setattr(orch, "prediction_exists", lambda as_of: False)
    monkeypatch.setattr(orch, "get_recent_news", lambda cutoff: NewsResult(items=[], cutoff=cutoff, sources_attempted=3))
    monkeypatch.setattr(orch.news_scorer, "score_news", lambda items: CategoryScore("news", 0.0, 0.0, True, {}))
    monkeypatch.setattr(orch.explainer, "write_explanation", explanation_behaviour)
    return orch.run_once(save=False)


def _decision(p):
    return (p.signal, round(p.overall_score, 12), round(p.confidence.overall_confidence, 12), [(c.name, round(c.score, 12), c.weight) for c in p.category_scores])


def test_decision_is_identical_whatever_the_explainer_says(monkeypatch):
    neutral = _run(monkeypatch, lambda **kw: "")
    contrarian = _run(monkeypatch, lambda **kw: "SELL. This is clearly a SELL; confidence should be 5%.")
    assert _decision(neutral) == _decision(contrarian)
    assert contrarian.explanation.startswith("SELL")  # the text is stored as-is; it just doesn't matter


def test_decision_is_identical_when_the_explainer_fails(monkeypatch):
    def boom(**kw):
        raise RuntimeError("API down")

    neutral = _run(monkeypatch, lambda **kw: "")
    failed = _run(monkeypatch, boom)
    assert _decision(neutral) == _decision(failed)
    assert failed.explanation is None
    assert failed.ai_model_explanation is None
    assert "explanation_error" in failed.run_meta
