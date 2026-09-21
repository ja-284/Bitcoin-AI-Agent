"""
The first of the project's two narrow AI calls: reads a list of news headlines and
rates each one's relevance to Bitcoin and its likely sentiment. The AI's job stays
narrow -- assess text, in a fixed structured format the SDK validates -- while turning
those assessments into one number is left to plain code below, not the AI. That keeps
the one place an "opinion" gets formed (this file) separate from the place opinions
get blended together (agent/scoring/scorer.py).

Uses Claude's structured-output feature (client.messages.parse against a Pydantic
model) instead of asking for free text and regexing a number out of it -- a fragile
pattern that breaks in ways that are annoying to debug.
"""

from anthropic import Anthropic
from pydantic import BaseModel, Field

from agent.config.settings import AI_MAX_RETRIES, AI_TIMEOUT_S, ANTHROPIC_API_KEY
from agent.shared.types import CategoryScore, NewsItem

MODEL = "claude-haiku-4-5"  # narrow, structured classification -- the cheapest current model is genuinely enough
NEWS_WEIGHT = 0.15

SYSTEM_PROMPT = (
    "You rate news headlines for a Bitcoin price-analysis system. For each headline, "
    "give its relevance to Bitcoin specifically (0-1) and its likely sentiment for "
    "Bitcoin's price (-1 to +1). Be conservative: general crypto or macroeconomic news "
    "that doesn't clearly bear on Bitcoin should get low relevance. Do not explain your "
    "reasoning -- just return the ratings."
)


class HeadlineAssessment(BaseModel):
    headline: str
    relevance_to_bitcoin: float = Field(
        ge=0, le=1, description="0 = not about Bitcoin at all, 1 = directly about Bitcoin's price, adoption, or regulation"
    )
    sentiment: float = Field(ge=-1, le=1, description="-1 = very bearish for Bitcoin's price, 0 = neutral, +1 = very bullish")


class NewsAnalysis(BaseModel):
    assessments: list[HeadlineAssessment]


def score_news(news_items: list[NewsItem]) -> CategoryScore:
    if not news_items:
        return CategoryScore("news", score=0.0, weight=0.0, is_independent=True, detail={"reason": "no recent news"})

    client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=AI_TIMEOUT_S, max_retries=AI_MAX_RETRIES)  # bounded: an hourly job cannot wait the SDK's 10-minute default
    headlines_text = "\n".join(f"{i + 1}. {item.headline}" for i, item in enumerate(news_items))

    response = client.messages.parse(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": headlines_text}],
        output_format=NewsAnalysis,
    )
    analysis = response.parsed_output

    total_relevance = sum(a.relevance_to_bitcoin for a in analysis.assessments)
    if total_relevance == 0:
        return CategoryScore(
            "news",
            score=0.0,
            weight=NEWS_WEIGHT,
            is_independent=True,
            detail={"reason": "no headline judged relevant to Bitcoin", "model": MODEL},
        )

    # We compute the aggregate ourselves (a relevance-weighted average) rather than
    # asking the AI for one overall number -- its job is limited to reading each
    # headline; combining them is deterministic, like everywhere else in scoring.
    weighted_sentiment = sum(a.sentiment * a.relevance_to_bitcoin for a in analysis.assessments) / total_relevance

    return CategoryScore(
        "news",
        score=weighted_sentiment,
        weight=NEWS_WEIGHT,
        is_independent=True,
        detail={
            "model": MODEL,
            "headlines_assessed": len(analysis.assessments),
            "avg_relevance": total_relevance / len(analysis.assessments),
            "assessments": [a.model_dump() for a in analysis.assessments],
        },
    )
