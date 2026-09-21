"""
Fetches recent headlines from a fixed list of reputable, free, public RSS feeds --
no account or API key required. Only headlines and short summaries are collected;
this project deliberately doesn't scrape full article text (more brittle, and not
needed for a sentiment/relevance read).

Timestamp rule (matters for point-in-time correctness):
- An item's availability time is the LATER of its published and updated timestamps.
  The text we read is the latest version, and if that version was produced after a
  prediction's cutoff it may contain information from after the cutoff -- so the
  conservative choice is to date the item by its last change.
- An item with neither timestamp gets published_at=None. It is never assumed to be
  fresh; news_service excludes it from time-sensitive use and counts the exclusion.
- These are publisher-reported times, not first-seen times. The first-seen time for
  the archive is the run's fetched_at, stored alongside every prediction.
"""

import logging
from calendar import timegm
from datetime import datetime, timezone
from typing import Optional

import feedparser
import requests

from agent.shared.types import NewsItem

logger = logging.getLogger(__name__)

FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "Decrypt": "https://decrypt.co/feed",
}


def _struct_to_utc(value) -> Optional[datetime]:
    if value is None:
        return None
    return datetime.fromtimestamp(timegm(value), tz=timezone.utc)


def availability_time(entry) -> Optional[datetime]:
    """Later of published/updated (feedparser gives both as UTC struct_time), or None."""
    candidates = [
        _struct_to_utc(entry.get("published_parsed")),
        _struct_to_utc(entry.get("updated_parsed")),
    ]
    known = [c for c in candidates if c is not None]
    return max(known) if known else None


FETCH_TIMEOUT_S = 15
USER_AGENT = "bitcoin-agent/0.2 (research; RSS reader)"


def fetch_feed(source_name: str, url: str) -> list[NewsItem]:
    # The download is done here with a hard timeout; feedparser only parses the bytes.
    # feedparser.parse(url) would download with no timeout at all -- one stalled feed server
    # could hang the hourly job until the runner kills it, losing the hour.
    resp = requests.get(url, timeout=FETCH_TIMEOUT_S, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"could not parse feed: {parsed.get('bozo_exception')}")
    return [
        NewsItem(
            headline=entry.get("title", "").strip(),
            source=source_name,
            url=entry.get("link", ""),
            published_at=availability_time(entry),
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
