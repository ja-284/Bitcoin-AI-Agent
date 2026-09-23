"""
The AI calls' real token usage is recorded with every run (agent/ai/usage.py), so the project's
running cost is measured rather than estimated. The recording is bookkeeping: it must be exact
when the figures exist, visibly absent when they do not, and unable to affect the analysis.
"""

import pytest

import agent.orchestrator as orch
from agent.ai import explainer, news_scorer
from agent.ai import usage as ai_usage
from agent.indicators.engine import HISTORY_HOURS
from agent.shared.types import NewsItem

from tests.test_failure_modes import _bars, _wire


def _usage(i, o):
    return type("U", (), {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": 0,
                          "cache_read_input_tokens": 0})()


class _Client:
    """A fake Anthropic client whose answers carry usage figures, like the real API's do."""

    def __init__(self, news_usage=None, explain_usage=None, stop_reason="end_turn"):
        outer = self
        self._nu, self._eu, self._stop = news_usage, explain_usage, stop_reason

        class Messages:
            def parse(self, **kw):
                analysis = news_scorer.NewsAnalysis(assessments=[
                    news_scorer.HeadlineAssessment(headline="h", relevance_to_bitcoin=1.0, sentiment=0.3)])
                return type("R", (), {"parsed_output": analysis, "usage": outer._nu})()

            def create(self, **kw):
                block = type("B", (), {"type": "text", "text": "An explanation."})()
                return type("R", (), {"content": [block], "stop_reason": outer._stop, "usage": outer._eu})()

        self.messages = Messages()


def _real_ai(monkeypatch, client):
    monkeypatch.setattr(news_scorer, "Anthropic", lambda **kw: client)
    monkeypatch.setattr(explainer, "Anthropic", lambda **kw: client)


REAL_SCORE_NEWS, REAL_EXPLAIN = news_scorer.score_news, explainer.write_explanation


def test_a_run_records_exactly_what_each_call_consumed(monkeypatch):
    _wire(monkeypatch, _bars(HISTORY_HOURS), news_scorer_fn=REAL_SCORE_NEWS, explainer_fn=REAL_EXPLAIN)
    _real_ai(monkeypatch, _Client(news_usage=_usage(3120, 2870), explain_usage=_usage(410, 222)))
    pred = orch.run_once(save=True)
    u = pred.run_meta["ai_usage"]
    assert u["news"] == {"model": news_scorer.MODEL, "input_tokens": 3120, "output_tokens": 2870,
                         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    assert u["explanation"]["model"] == explainer.MODEL
    assert (u["explanation"]["input_tokens"], u["explanation"]["output_tokens"]) == (410, 222)


def test_a_refused_answer_is_still_counted_because_it_was_still_billed(monkeypatch):
    """A truncated explanation is refused (no text stored) -- but the tokens were generated and paid for."""
    _wire(monkeypatch, _bars(HISTORY_HOURS), news_scorer_fn=REAL_SCORE_NEWS, explainer_fn=REAL_EXPLAIN)
    _real_ai(monkeypatch, _Client(news_usage=_usage(100, 50), explain_usage=_usage(400, 1024), stop_reason="max_tokens"))
    pred = orch.run_once(save=True)
    assert pred.explanation is None and "truncated" in pred.run_meta["explanation_error"]
    assert pred.run_meta["ai_usage"]["explanation"]["output_tokens"] == 1024


def test_missing_figures_are_marked_unavailable_never_recorded_as_zero(monkeypatch):
    _wire(monkeypatch, _bars(HISTORY_HOURS), news_scorer_fn=REAL_SCORE_NEWS, explainer_fn=REAL_EXPLAIN)
    _real_ai(monkeypatch, _Client(news_usage=None, explain_usage=_usage(1, 1)))
    u = orch.run_once(save=True).run_meta["ai_usage"]
    assert u["news"] == {"model": news_scorer.MODEL, "usage_unavailable": True}


def test_recording_cannot_change_the_analysis(monkeypatch):
    """Same inputs with and without usage figures: identical decision, score, confidence and text."""
    bars = _bars(HISTORY_HOURS)
    _wire(monkeypatch, bars, news_scorer_fn=REAL_SCORE_NEWS, explainer_fn=REAL_EXPLAIN)
    _real_ai(monkeypatch, _Client(news_usage=_usage(5, 5), explain_usage=_usage(5, 5)))
    a = orch.run_once(save=True)
    _real_ai(monkeypatch, _Client(news_usage=None, explain_usage=None))
    b = orch.run_once(save=True)
    assert (a.signal, a.overall_score, a.confidence, a.explanation) == (b.signal, b.overall_score, b.confidence, b.explanation)
    assert [c.score for c in a.category_scores] == [c.score for c in b.category_scores]


def test_a_run_without_ai_calls_records_nothing(monkeypatch):
    """Stubbed AI (no API answer at all) must not produce an empty or invented usage entry."""
    _wire(monkeypatch, _bars(HISTORY_HOURS))
    assert "ai_usage" not in orch.run_once(save=True).run_meta


def test_record_never_raises_even_on_a_hostile_response():
    class Hostile:
        @property
        def usage(self):
            raise RuntimeError("boom")

    with ai_usage.recording() as sink:
        ai_usage.record("news", "m", Hostile())
    assert sink == {"news": {"model": "m", "usage_unavailable": True}}


def test_outside_a_recording_nothing_is_kept_and_nothing_leaks_between_runs():
    ai_usage.record("news", "m", type("R", (), {"usage": _usage(1, 1)})())  # no recording open: a no-op
    with ai_usage.recording() as first:
        ai_usage.record("news", "m", type("R", (), {"usage": _usage(1, 1)})())
    with ai_usage.recording() as second:
        pass
    assert first["news"]["input_tokens"] == 1 and second == {}


def test_the_ai_calls_themselves_are_unchanged():
    """The recording sits AFTER each call; the prompt, schema and limits E009 validated are untouched."""
    import inspect

    for fn, call in ((news_scorer.score_news, "client.messages.parse("), (explainer.write_explanation, "client.messages.create(")):
        src = inspect.getsource(fn)
        assert src.index(call) < src.index("ai_usage.record(")
    assert news_scorer.MAX_TOKENS == 16384 and explainer.MAX_TOKENS == 1024
