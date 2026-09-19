"""
Combines the raw RSS feeds into one clean, recent, de-duplicated list of headlines
that were available at or before a given information cutoff.

The cutoff is an explicit input, never "now": the hourly job runs some minutes (or,
when GitHub is late, an hour) after the reference candle closed, and news published
in that gap would otherwise leak into a prediction that is supposed to know only what
was knowable at the cutoff.

De-duplication matters because the same story often runs on multiple outlets within
the same hour -- without catching that, one big story could get counted three times
over in the news score just because three feeds carried it.
"""

import difflib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from agent.news.rss_source import FEEDS, fetch_all_feeds
from agent.shared.types import NewsItem

logger = logging.getLogger(__name__)

LOOKBACK_HOURS = 24
DEDUP_SIMILARITY_THRESHOLD = 0.75  # 0-1; higher = only near-identical headlines count as duplicates


@dataclass
class NewsResult:
    items: list[NewsItem]
    cutoff: datetime
    sources_attempted: int
    sources_failed: list[str] = field(default_factory=list)
    fetched_count: int = 0
    excluded_undated: int = 0
    excluded_after_cutoff: int = 0
    excluded_too_old: int = 0
    excluded_duplicate: int = 0

    @property
    def completeness(self) -> float:
        if self.sources_attempted == 0:
            return 0.0
        return 1 - (len(self.sources_failed) / self.sources_attempted)

    def summary(self) -> dict:
        return {
            "cutoff": self.cutoff.isoformat(),
            "fetched": self.fetched_count,
            "used": len(self.items),
            "excluded_undated": self.excluded_undated,
            "excluded_after_cutoff": self.excluded_after_cutoff,
            "excluded_too_old": self.excluded_too_old,
            "excluded_duplicate": self.excluded_duplicate,
            "sources_failed": list(self.sources_failed),
        }


def _normalize(headline: str) -> str:
    return " ".join(headline.lower().split())


def _is_duplicate(headline: str, already_seen: list[str]) -> bool:
    normalized = _normalize(headline)
    return any(
        difflib.SequenceMatcher(None, normalized, seen).ratio() >= DEDUP_SIMILARITY_THRESHOLD
        for seen in already_seen
    )


def select_news(raw_items: list[NewsItem], cutoff: datetime, lookback_hours: int = LOOKBACK_HOURS) -> NewsResult:
    """
    Pure selection step (no network), so it can be tested exactly. Keeps items with a
    known availability time inside (cutoff - lookback, cutoff]; excludes and counts
    everything else. Never guesses a time for an undated item.
    """
    window_start = cutoff - timedelta(hours=lookback_hours)
    result = NewsResult(items=[], cutoff=cutoff, sources_attempted=len(FEEDS), fetched_count=len(raw_items))

    eligible: list[NewsItem] = []
    for item in raw_items:
        if item.published_at is None:
            result.excluded_undated += 1
        elif item.published_at > cutoff:
            result.excluded_after_cutoff += 1
        elif item.published_at <= window_start:
            result.excluded_too_old += 1
        else:
            eligible.append(item)

    seen_normalized: list[str] = []
    for item in sorted(eligible, key=lambda i: i.published_at):
        if _is_duplicate(item.headline, seen_normalized):
            result.excluded_duplicate += 1
            continue
        result.items.append(item)
        seen_normalized.append(_normalize(item.headline))

    if result.excluded_undated:
        logger.warning("Excluded %d undated news item(s) -- never assumed fresh.", result.excluded_undated)
    return result


def get_recent_news(cutoff: datetime, lookback_hours: int = LOOKBACK_HOURS) -> NewsResult:
    raw_items, failed = fetch_all_feeds()
    result = select_news(raw_items, cutoff, lookback_hours)
    result.sources_failed = failed
    return result
