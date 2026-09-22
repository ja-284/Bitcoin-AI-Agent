"""
The conductor: runs one complete analysis cycle, in order, and writes the result to
the database. This is what the hourly schedule will trigger.

Point-in-time discipline: every run has one explicit INFORMATION CUTOFF -- the close
of the last fully-closed candle. Price data can't see past it by construction (the
still-forming candle is never fetched), and the news step is handed the cutoff and
keeps only items available at or before it. The run's actual fetch time is recorded
too, so the lag between "what the prediction is about" and "when it was made" stays
measurable rather than hidden.

Partial-failure handling is a first-class concern here rather than an afterthought,
because the whole thing runs unattended: one flaky news feed shouldn't take down a run.
Price data is the deliberate exception -- nothing downstream can be computed without
it, so if every price provider fails, the run fails loudly instead of quietly logging
a meaningless result.
"""

import logging
import os
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from agent.ai import explainer, news_scorer
from agent.data_providers.market_data import get_market_data
from agent.database.db import prediction_exists, save_prediction
from agent.decision.decision import compute_confidence, decide_signal
from agent.indicators.engine import HISTORY_HOURS, compute_indicators
from agent.news.news_service import get_recent_news
from agent.patterns.rules import detect_patterns
from agent.scoring.scorer import SCORING_VERSION, score_all
from agent.shared.types import Prediction, PriceBar
from agent.version import PIPELINE_VERSION

logger = logging.getLogger(__name__)


def information_cutoff(reference_bar: PriceBar) -> datetime:
    """The reference candle's close: the last instant whose information a prediction may use."""
    return reference_bar.as_of + timedelta(hours=1)


def run_once(save: bool = True) -> Prediction | None:
    """
    One full analysis cycle. Returns None when a saved run for this hour already exists:
    the schedule fires twice an hour so a late or skipped slot can be retried, and the
    retry must cost nothing (no AI calls) when the first attempt already succeeded.
    """
    fetched_at = datetime.now(tz=timezone.utc)

    market = get_market_data(HISTORY_HOURS)
    bars = market.bars
    reference = bars[-1]
    cutoff = information_cutoff(reference)
    if save and prediction_exists(reference.as_of):
        logger.info("Prediction for %s already exists -- nothing to do.", reference.as_of.isoformat())
        return None

    run_meta: dict = {
        "lag_seconds_after_cutoff": (fetched_at - cutoff).total_seconds(),
        "price_data": {"provider": market.provider, "synthetic": reference.is_synthetic, **market.quality.summary()},
        "code_commit": os.environ.get("GITHUB_SHA"),  # exactly which code produced this row (None when run by hand)
    }
    if reference.is_synthetic:
        logger.warning("Price data is SYNTHETIC (%s fallback): volume is not a true hourly figure this run.", market.provider)

    indicators = compute_indicators(bars)
    patterns = detect_patterns(bars, indicators)

    news_items = []
    news_score = None
    try:
        news = get_recent_news(cutoff=cutoff)
        news_items = news.items
        run_meta["news"] = news.summary()
        news_score = news_scorer.score_news(news_items)
    except Exception as exc:  # noqa: BLE001 -- a failed news step degrades the run, it doesn't end it
        logger.warning("News step failed, continuing with reduced confidence: %s", exc)
        run_meta["news_error"] = str(exc)
        # The full message is kept for diagnosis (it is what identified the 2026-09-21
        # truncation); the TYPE is stored separately so failures can be counted and grouped
        # without anything having to parse free text or repeat it to a reader.
        run_meta["news_error_type"] = type(exc).__name__

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
        run_meta["explanation_error"] = str(exc)

    prediction = Prediction(
        as_of=reference.as_of,
        cutoff_at=cutoff,
        fetched_at=fetched_at,
        close_price=indicators.close,
        price_source=reference.source,
        price_is_synthetic=reference.is_synthetic,
        overall_score=result.overall_score,
        signal=signal,
        confidence=confidence,
        category_scores=result.category_scores,
        scoring_version=SCORING_VERSION,
        pipeline_version=PIPELINE_VERSION,
        news_items=news_items,
        raw_indicators=asdict(indicators),
        run_meta=run_meta,
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
