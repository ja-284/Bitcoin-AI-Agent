"""
Backend Phase M: the two LLM calls fail safely and cannot gain authority.

- SDK failures (timeout, rate limit, connection, overload) propagate as exceptions, which the
  orchestrator records as news_error / explanation_error (tests/test_failure_modes.py);
- a response with no text, or blank text, is an error -- never an empty explanation stored as
  success;
- the news schema rejects NaN, infinities, out-of-range values and missing fields;
- the clients are constructed with the bounded timeout and retry settings.
"""

import anthropic
import httpx2 as httpx
import pytest

from agent.ai import explainer, news_scorer
from agent.shared.types import CategoryScore, ConfidenceBreakdown, NewsItem


class _Client:
    def __init__(self, exc=None, content=None, parsed=None):
        self._exc, self._content, self._parsed = exc, content, parsed
        outer = self

        class Messages:
            def create(self, **kw):
                if outer._exc:
                    raise outer._exc
                return type("R", (), {"content": outer._content})()

            def parse(self, **kw):
                if outer._exc:
                    raise outer._exc
                return type("R", (), {"parsed_output": outer._parsed})()

        self.messages = Messages()


def _sdk_errors():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp429 = httpx.Response(429, request=req)
    resp529 = httpx.Response(529, request=req)
    return [anthropic.APITimeoutError(request=req), anthropic.APIConnectionError(request=req),
            anthropic.RateLimitError("rate limited", response=resp429, body=None), anthropic.APIStatusError("overloaded", response=resp529, body=None)]


@pytest.mark.parametrize("exc", _sdk_errors(), ids=lambda e: type(e).__name__)
def test_sdk_failures_propagate_from_both_calls(monkeypatch, exc):
    monkeypatch.setattr(news_scorer, "Anthropic", lambda **kw: _Client(exc=exc))
    with pytest.raises(anthropic.AnthropicError):
        news_scorer.score_news([NewsItem("h", "s", "u", None)])
    monkeypatch.setattr(explainer, "Anthropic", lambda **kw: _Client(exc=exc))
    with pytest.raises(anthropic.AnthropicError):
        explainer.write_explanation(signal="HOLD", overall_score=0.0, confidence=ConfidenceBreakdown(0.5, 1.0, 0.6), category_scores=[], close_price=1.0)


def test_explainer_without_text_is_an_error_not_an_empty_success(monkeypatch):
    for content in ([], [type("B", (), {"type": "tool_use", "text": None})()], [type("B", (), {"type": "text", "text": "   "})()]):
        monkeypatch.setattr(explainer, "Anthropic", (lambda _c: (lambda **kw: _Client(content=_c)))(content))
        with pytest.raises(ValueError, match="no text"):
            explainer.write_explanation(signal="HOLD", overall_score=0.0, confidence=ConfidenceBreakdown(0.5, 1.0, 0.6), category_scores=[], close_price=1.0)
    monkeypatch.setattr(explainer, "Anthropic", lambda **kw: _Client(content=[type("B", (), {"type": "text", "text": " fine "})()]))
    assert explainer.write_explanation(signal="HOLD", overall_score=0.0, confidence=ConfidenceBreakdown(0.5, 1.0, 0.6), category_scores=[], close_price=1.0) == "fine"


@pytest.mark.parametrize("bad", [dict(sentiment=float("nan")), dict(sentiment=float("inf")), dict(sentiment=1.5), dict(relevance_to_bitcoin=-0.1), dict(relevance_to_bitcoin=None)])
def test_news_schema_rejects_bad_values(bad):
    fields = {"headline": "h", "relevance_to_bitcoin": 0.5, "sentiment": 0.0, **bad}
    with pytest.raises(Exception):
        news_scorer.HeadlineAssessment(**fields)


def test_clients_are_bounded(monkeypatch):
    seen = {}

    def fake_anthropic(**kw):
        seen.update(kw)
        return _Client(parsed=news_scorer.NewsAnalysis(assessments=[news_scorer.HeadlineAssessment(headline="h", relevance_to_bitcoin=1.0, sentiment=0.2)]))

    monkeypatch.setattr(news_scorer, "Anthropic", fake_anthropic)
    score = news_scorer.score_news([NewsItem("h", "s", "u", None)])
    assert seen["timeout"] == news_scorer.AI_TIMEOUT_S and seen["max_retries"] == news_scorer.AI_MAX_RETRIES
    assert isinstance(score, CategoryScore) and score.score == pytest.approx(0.2)
