"""
The shared "shapes" every module agrees on. Keeping these in one place is what makes
the modules in this project actually swappable: as long as a replacement module still
produces/accepts these same shapes, nothing else needs to change.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PriceBar:
    """One hour of Bitcoin price history (a single 'candle')."""

    as_of: datetime  # UTC. The hour this bar covers, e.g. 14:00 = the 14:00-15:00 candle.
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str  # which provider this came from, e.g. "binance" or "coingecko"
    is_synthetic: bool = False  # True if open/high/low were approximated (see coingecko.py)


@dataclass
class NewsItem:
    headline: str
    source: str  # name of the outlet, e.g. "CoinDesk"
    url: str
    published_at: datetime  # UTC
    summary: Optional[str] = None


@dataclass
class CategoryScore:
    """One factor's contribution to the overall picture, e.g. 'trend' or 'momentum'."""

    name: str
    score: float  # -1.0 (very bearish) to +1.0 (very bullish)
    weight: float  # how much this factor counts toward the overall score
    is_independent: bool  # False if this score shares most of its underlying math with another category
    detail: dict = field(default_factory=dict)  # the raw numbers behind the score, kept for logging


@dataclass
class ConfidenceBreakdown:
    """
    A computed stand-in for confidence, not a true probability yet (see CLAUDE.md).
    Every component is kept so it can be checked against real outcomes later.
    """

    agreement_score: float  # 0-1: how much the independent category scores agree with each other
    completeness_score: float  # 0-1: how complete/reliable the input data was this run
    overall_confidence: float  # 0-1: the combined figure actually reported


@dataclass
class Prediction:
    as_of: datetime  # UTC. The point in time this analysis is about.
    fetched_at: datetime  # UTC. When the data behind this analysis was actually fetched.
    overall_score: float  # -1.0 to +1.0
    signal: str  # "BUY" | "HOLD" | "SELL"
    confidence: ConfidenceBreakdown
    category_scores: list[CategoryScore]
    scoring_version: str
    explanation: Optional[str] = None
