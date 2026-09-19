"""
The conductor: runs one complete analysis cycle, in order, and writes the result to
the database. This is what the hourly schedule will trigger.

Partial-failure handling is a first-class concern here rather than an afterthought,
because the whole thing runs unattended: one flaky news feed shouldn't take down a run.
Price data is the deliberate exception -- nothing downstream can be computed without
it, so if every price provider fails, the run fails loudly instead of quietly logging
a meaningless result.
"""

import logging
from dataclasses import asdict
from datetime import datetime, timezone

from agent.ai import explainer, news_scorer
from agent.data_providers.market_data import get_hourly_bars
from agent.database.db import save_prediction
from agent.decision.decision import compute_confidence, decide_signal
from agent.indicators.engine import compute_indicators
from agent.news.news_service import get_recent_news
from agent.patterns.rules import detect_patterns
from agent.scoring.scorer import SCORING_VERSION, score_all
from agent.shared.types import Prediction

logger = logging.getLogger(__name__)

HISTORY_HOURS = 250  # enough to cover the longest indicator warm-up (the 200h moving average)


def run_once(save: bool = True) -> Prediction:
    fetched_at = datetime.now(tz=timezone.utc)

    bars = get_hourly_bars(HISTORY_HOURS)
    indicators = compute_indicators(bars)
    patterns = detect_patterns(bars, indicators)

    news_items = []
    news_score = None
    try:
        news = get_recent_news()
        news_items = news.items
        news_score = news_scorer.score_news(news_items)
    except Exception as exc:  # noqa: BLE001 -- a failed news step degrades the run, it doesn't end it
        logger.warning("News step failed, continuing with reduced confidence: %s", exc)

    result = score_all(bars, indicators, patterns, news_score=news_score)
    signal = decide_signal(result.overall_score)
    confidence = compute_confidence(result)

    explanation = None
    try:
        explanation = explainer.write_explanation(
            signal=signal,
            overall_score=result.overall_score,
            confidence=confidence,
            category_scores=result.category_scores,
            close_price=indicators.close,
        )
    except Exception as exc:  # noqa: BLE001 -- the explanation is commentary; losing it must not lose the analysis
        logger.warning("Explanation step failed, continuing without one: %s", exc)

    prediction = Prediction(
        as_of=bars[-1].as_of,
        fetched_at=fetched_at,
        close_price=indicators.close,
        price_source=bars[-1].source,
        price_is_synthetic=bars[-1].is_synthetic,
        overall_score=result.overall_score,
        signal=signal,
        confidence=confidence,
        category_scores=result.category_scores,
        scoring_version=SCORING_VERSION,
        news_items=news_items,
        raw_indicators=asdict(indicators),
        ai_model_news=news_scorer.MODEL if news_score is not None else None,
        ai_model_explanation=explainer.MODEL if explanation else None,
        explanation=explanation,
    )

    if save:
        saved_id = save_prediction(prediction)
        if saved_id is None:
            logger.info("A prediction for %s already existed -- left untouched.", prediction.as_of)
        else:
            logger.info("Saved prediction id=%s", saved_id)

    return prediction
