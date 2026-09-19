"""
Combines the raw RSS feeds into one clean, recent, de-duplicated list.

De-duplication matters because the same story often runs on multiple outlets within
the same hour -- without catching that, one big story could get counted three times
over in the news score just because three feeds carried it.
"""

import difflib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from agent.news.rss_source import FEEDS, fetch_all_feeds
from agent.shared.types import NewsItem

LOOKBACK_HOURS = 24
DEDUP_SIMILARITY_THRESHOLD = 0.75  # 0-1; higher = only near-identical headlines count as duplicates


@dataclass
class NewsResult:
    items: list[NewsItem]
    sources_attempted: int
    sources_failed: list[str] = field(default_factory=list)

    @property
    def completeness(self) -> float:
        if self.sources_attempted == 0:
            return 0.0
        return 1 - (len(self.sources_failed) / self.sources_attempted)


def _normalize(headline: str) -> str:
    return " ".join(headline.lower().split())


def _is_duplicate(headline: str, already_seen: list[str]) -> bool:
    normalized = _normalize(headline)
    return any(
        difflib.SequenceMatcher(None, normalized, seen).ratio() >= DEDUP_SIMILARITY_THRESHOLD
        for seen in already_seen
    )


def get_recent_news(lookback_hours: int = LOOKBACK_HOURS) -> NewsResult:
    raw_items, failed = fetch_all_feeds()
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)

    recent = sorted(
        (item for item in raw_items if item.published_at >= cutoff),
        key=lambda item: item.published_at,
    )

    deduped: list[NewsItem] = []
    seen_normalized: list[str] = []
    for item in recent:
        if _is_duplicate(item.headline, seen_normalized):
            continue
        deduped.append(item)
        seen_normalized.append(_normalize(item.headline))

    return NewsResult(items=deduped, sources_attempted=len(FEEDS), sources_failed=failed)
