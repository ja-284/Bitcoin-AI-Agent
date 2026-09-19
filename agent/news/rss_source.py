"""
Fetches recent headlines from a fixed list of reputable, free, public RSS feeds --
no account or API key required. Only headlines and short summaries are collected;
this project deliberately doesn't scrape full article text (more brittle, and not
needed for a sentiment/relevance read).
"""

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from agent.shared.types import NewsItem

logger = logging.getLogger(__name__)

FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
}


def _parse_published(entry) -> datetime:
    raw = entry.get("published") or entry.get("updated")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(tz=timezone.utc)


def fetch_feed(source_name: str, url: str) -> list[NewsItem]:
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"could not parse feed: {parsed.get('bozo_exception')}")
    return [
        NewsItem(
            headline=entry.get("title", "").strip(),
            source=source_name,
            url=entry.get("link", ""),
            published_at=_parse_published(entry),
            summary=(entry.get("summary") or "").strip() or None,
        )
        for entry in parsed.entries
    ]


def fetch_all_feeds() -> tuple[list[NewsItem], list[str]]:
    """Returns (items, names_of_feeds_that_failed). One feed failing doesn't block the others."""
    items: list[NewsItem] = []
    failed: list[str] = []
    for name, url in FEEDS.items():
        try:
            items.extend(fetch_feed(name, url))
        except Exception as exc:  # noqa: BLE001 -- one bad feed must not take down news collection
            logger.warning("News feed %s failed: %s", name, exc)
            failed.append(name)
    return items, failed
