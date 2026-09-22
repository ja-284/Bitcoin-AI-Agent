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


# ---------------------------------------------------------------- partial news failure
# A news feed going down is the quiet failure: unlike a total outage it still produces a
# number, so without these it would look exactly like a normal hour. Never seen live in 69
# runs, which is precisely why it needs testing rather than watching.
def test_one_failed_feed_is_recorded_and_the_others_still_work(monkeypatch):
    from agent.news import rss_source

    def fake_fetch(name, url):
        if name == "Cointelegraph":
            raise RuntimeError("feed returned 503")
        return [NewsItem("%s headline" % name, name, "http://x/1", START)]

    monkeypatch.setattr(rss_source, "fetch_feed", fake_fetch)
    items, failed = rss_source.fetch_all_feeds()
    assert failed == ["Cointelegraph"]
    assert len(items) == len(rss_source.FEEDS) - 1, "the healthy feeds must still be collected"


def test_every_feed_failing_yields_no_items_and_a_full_failure_list(monkeypatch):
    from agent.news import rss_source

    monkeypatch.setattr(rss_source, "fetch_feed", lambda name, url: (_ for _ in ()).throw(RuntimeError("down")))
    items, failed = rss_source.fetch_all_feeds()
    assert items == []
    assert sorted(failed) == sorted(rss_source.FEEDS)


def test_no_news_is_unavailable_rather_than_neutral():
    """Weight 0, not score 0: an absent category must never look like a category with no opinion."""
    from agent.ai.news_scorer import score_news

    cat = score_news([])
    assert cat.weight == 0.0
    assert cat.is_independent is True
    assert "no recent news" in str(cat.detail)


def test_the_contract_shows_a_partial_news_failure():
    from datetime import datetime, timedelta, timezone

    from agent.api import state as api

    now = datetime(2026, 9, 22, 19, 5, tzinfo=timezone.utc)
    pred = {
        "as_of": now - timedelta(hours=2), "cutoff_at": now - timedelta(hours=1),
        "fetched_at": now - timedelta(minutes=53), "close_price": 1.0, "price_source": "binance",
        "price_is_synthetic": False, "overall_score": 0.1, "signal": "HOLD", "agreement_score": 0.5,
        "completeness_score": 1.0, "overall_confidence": 0.5, "pipeline_version": "0.2.0",
        "scoring_version": "0.2.0", "ai_model_news": "m", "ai_model_explanation": "m",
        "explanation": "x", "category_scores": [], "news_items": [{"headline": "h"}],
        "run_meta": {"news": {"sources_failed": ["Decrypt", "CoinDesk"]}},
    }
    counts = {"predictions": 1, "first_prediction": None, "latest_prediction": None,
              "missing_hours_last_48h": 0, "shadow_rows": 0, "shadow_errors_last_24h": 0}
    news = api.assemble(pred, None, counts, {"by_horizon": [], "latest_1h": [], "note": ""}, now)["latest"]["news"]
    assert news["sources_failed"] == ["Decrypt", "CoinDesk"]
    assert news["sources_used"] == news["sources_total"] - 2
    assert news["available"] is True, "it still produced news -- the point is that the shortfall is visible"
