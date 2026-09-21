"""
Backend Phase C: deliberate failures, end to end through the orchestrator, with every
external dependency faked. For each: what does the system do, what is recorded, is a
prediction produced, and can a bad result enter the record silently?

  news model answers garbage / nothing   -> news_error recorded, news weight 0, prediction saved
  explainer fails                        -> explanation None, error recorded, decision unchanged
  database down at save time             -> the run raises (nothing silently lost), and nothing
                                            about the prediction depended on the save
  a late run                             -> as_of comes from the candles, never from the clock
  history shorter than the indicators need -> indicators say so, completeness drops, run finishes
  the model assessed fewer headlines     -> flagged in the stored detail, not hidden
"""

from datetime import datetime, timedelta, timezone

import pytest

import agent.orchestrator as orch
from agent.ai import news_scorer
from agent.data_providers.market_data import MarketData
from agent.data_providers.quality import validate_bars
from agent.indicators.engine import HISTORY_HOURS
from agent.news.news_service import NewsResult
from agent.shared.types import CategoryScore, NewsItem, PriceBar

START = datetime(2026, 3, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def _bars(n: int) -> list[PriceBar]:
    out = []
    for i in range(n):
        p = 100 + (i % 17) * 0.3 + (i % 5) * 0.1
        out.append(PriceBar(START + i * HOUR, p, p + 0.5, p - 0.5, p + 0.1, 10.0 + (i % 3), "binance"))
    return out


def _market(bars):
    return MarketData(bars=bars, quality=validate_bars(bars, now=bars[-1].as_of + 2 * HOUR), provider="binance")


def _wire(monkeypatch, bars, news_scorer_fn=None, explainer_fn=None, save_fn=None):
    monkeypatch.setattr(orch, "get_market_data", lambda n: _market(bars))
    monkeypatch.setattr(orch, "prediction_exists", lambda as_of: False)
    items = [NewsItem("Bitcoin does a thing", "Test", "http://x/1", bars[-1].as_of + timedelta(minutes=30))]
    monkeypatch.setattr(orch, "get_recent_news", lambda cutoff: NewsResult(items=items, cutoff=cutoff, sources_attempted=1, fetched_count=1))
    monkeypatch.setattr(orch.news_scorer, "score_news", news_scorer_fn or (lambda items: CategoryScore("news", 0.2, 0.15, True, {})))
    monkeypatch.setattr(orch.explainer, "write_explanation", explainer_fn or (lambda **kw: "fine"))
    monkeypatch.setattr(orch, "save_prediction", save_fn or (lambda p: 1))


def test_news_model_garbage_degrades_the_run_and_is_recorded(monkeypatch):
    bars = _bars(HISTORY_HOURS)

    def broken(items):
        raise ValueError("news model returned no assessments for 1 headlines")

    _wire(monkeypatch, bars, news_scorer_fn=broken)
    pred = orch.run_once(save=True)
    assert pred is not None and pred.signal in ("BUY", "HOLD", "SELL")
    assert "no assessments" in pred.run_meta["news_error"]
    news = [c for c in pred.category_scores if c.name == "news"][0]
    assert news.weight == 0.0 and pred.ai_model_news is None  # unavailable, not neutral


def test_explainer_failure_never_touches_the_decision(monkeypatch):
    bars = _bars(HISTORY_HOURS)
    _wire(monkeypatch, bars)
    baseline = orch.run_once(save=True)

    def broken(**kw):
        raise TimeoutError("LLM timeout")

    _wire(monkeypatch, bars, explainer_fn=broken)
    pred = orch.run_once(save=True)
    assert pred.explanation is None and pred.ai_model_explanation is None and "LLM timeout" in pred.run_meta["explanation_error"]
    assert (pred.signal, pred.overall_score, pred.confidence.overall_confidence) == (baseline.signal, baseline.overall_score, baseline.confidence.overall_confidence)


def test_database_down_at_save_raises_instead_of_silently_losing_the_hour(monkeypatch):
    bars = _bars(HISTORY_HOURS)

    def down(p):
        raise ConnectionError("database unreachable")

    _wire(monkeypatch, bars, save_fn=down)
    with pytest.raises(ConnectionError, match="unreachable"):
        orch.run_once(save=True)
    # and the same run without saving is complete -- nothing about the analysis depended on the database
    _wire(monkeypatch, bars, save_fn=down)
    assert orch.run_once(save=False) is not None


def test_conflict_at_save_is_reported_not_overwritten(monkeypatch):
    bars = _bars(HISTORY_HOURS)
    _wire(monkeypatch, bars, save_fn=lambda p: None)  # ON CONFLICT DO NOTHING returns no id
    pred = orch.run_once(save=True)
    assert pred is not None  # the analysis is returned; the existing row was left untouched (logged)


def test_late_run_still_labels_the_hour_by_its_candle(monkeypatch):
    bars = _bars(HISTORY_HOURS)
    _wire(monkeypatch, bars)
    pred = orch.run_once(save=False)
    assert pred.as_of == bars[-1].as_of and pred.cutoff_at == bars[-1].as_of + HOUR
    assert pred.fetched_at > pred.cutoff_at  # the clock only sets fetched_at
    assert pred.run_meta["lag_seconds_after_cutoff"] > 0


def test_short_history_is_declared_and_lowers_completeness(monkeypatch):
    bars = _bars(60)  # far fewer than the 200h SMA needs
    _wire(monkeypatch, bars)
    pred = orch.run_once(save=False)
    assert pred.raw_indicators["insufficient_history"]
    assert pred.confidence.completeness_score < 1.0
    assert pred.signal in ("BUY", "HOLD", "SELL")


def test_news_scorer_flags_partial_and_rejects_empty_model_answers(monkeypatch):
    items = [NewsItem(f"headline {i}", "Test", f"http://x/{i}", START) for i in range(3)]

    class FakeResp:
        def __init__(self, parsed):
            self.parsed_output = parsed

    class FakeMessages:
        def __init__(self, parsed):
            self._parsed = parsed

        def parse(self, **kw):
            return FakeResp(self._parsed)

    class FakeClient:
        def __init__(self, parsed):
            self.messages = FakeMessages(parsed)

    empty = news_scorer.NewsAnalysis(assessments=[])
    monkeypatch.setattr(news_scorer, "Anthropic", lambda **kw: FakeClient(empty))
    with pytest.raises(ValueError, match="no assessments"):
        news_scorer.score_news(items)

    partial = news_scorer.NewsAnalysis(assessments=[news_scorer.HeadlineAssessment(headline="headline 0", relevance_to_bitcoin=1.0, sentiment=0.5)])
    monkeypatch.setattr(news_scorer, "Anthropic", lambda **kw: FakeClient(partial))
    score = news_scorer.score_news(items)
    assert score.detail["assessment_count_mismatch"] is True and score.detail["headlines_given"] == 3 and score.detail["headlines_assessed"] == 1

    with pytest.raises(Exception):  # out-of-range values never pass the schema
        news_scorer.HeadlineAssessment(headline="x", relevance_to_bitcoin=2.0, sentiment=0.0)
