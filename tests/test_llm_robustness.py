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
    def __init__(self, exc=None, content=None, parsed=None, stop_reason="end_turn"):
        self._exc, self._content, self._parsed, self._stop = exc, content, parsed, stop_reason
        outer = self

        class Messages:
            def create(self, **kw):
                if outer._exc:
                    raise outer._exc
                return type("R", (), {"content": outer._content, "stop_reason": outer._stop})()

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


def test_news_answer_has_room_for_a_realistic_headline_count():
    """
    REGRESSION (2026-09-21/22): the answer echoes each headline, so it costs ~45 output tokens
    per item. max_tokens=2048 covered ~50 headlines; the live 24h window grew to 63 and every
    answer came back truncated -- invalid JSON -- so the live signal lost its news category for
    17 hours. The cap must cover far more than the observed volume.
    """
    assert news_scorer.MAX_TOKENS >= 45 * 200, "the cap must fit at least 200 headlines"
    import inspect

    src = inspect.getsource(news_scorer.score_news)
    assert "max_tokens=MAX_TOKENS" in src  # no stray literal that can drift from the constant


def test_a_truncated_answer_names_the_cause(monkeypatch):
    """A truncated structured answer must not surface as a bare JSON error."""
    from pydantic import ValidationError

    class Boom:
        def __init__(self):
            self.messages = self

        def parse(self, **kw):
            raise ValidationError.from_exception_data("NewsAnalysis", [])

    monkeypatch.setattr(news_scorer, "Anthropic", lambda **kw: Boom())
    with pytest.raises(ValueError, match="truncated answer arrives as invalid JSON"):
        news_scorer.score_news([NewsItem(f"h{i}", "s", f"u{i}", None) for i in range(60)])


def _explain():
    return explainer.write_explanation(signal="HOLD", overall_score=0.0, confidence=ConfidenceBreakdown(0.5, 1.0, 0.6),
                                       category_scores=[], close_price=1.0)


def test_a_truncated_explanation_is_refused_rather_than_stored_as_complete(monkeypatch):
    """
    Unlike the news answer, a cut-off explanation is still readable text, so nothing would
    notice it. Same class of defect as the 2026-09-21 news truncation, caught before it bit.
    """
    block = type("B", (), {"type": "text", "text": "The signal is BUY because the trend"})()

    class R:
        content = [block]
        stop_reason = "max_tokens"

    monkeypatch.setattr(explainer, "Anthropic", lambda **kw: _Client(content=R.content, stop_reason="max_tokens"))
    with pytest.raises(ValueError, match="truncated at max_tokens"):
        _explain()

    monkeypatch.setattr(explainer, "Anthropic", lambda **kw: _Client(content=R.content, stop_reason="end_turn"))
    assert _explain().startswith("The signal is BUY")


def test_explanations_have_headroom_over_what_the_model_actually_writes():
    # longest live explanation on 2026-09-22: 1061 characters, i.e. roughly 265 tokens
    assert explainer.MAX_TOKENS >= 3 * 265
    import inspect

    assert "max_tokens=MAX_TOKENS" in inspect.getsource(explainer.write_explanation)
