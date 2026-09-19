"""
News may influence a prediction only if it was available at or before the information
cutoff. Undated items are never assumed fresh. These tests pin that down exactly.
"""

from datetime import datetime, timedelta, timezone

from agent.news.news_service import select_news
from agent.news.rss_source import availability_time
from agent.shared.types import NewsItem

CUTOFF = datetime(2026, 9, 19, 11, 0, tzinfo=timezone.utc)


def _item(headline: str, minutes_before_cutoff: float | None, source: str = "A") -> NewsItem:
    published = None if minutes_before_cutoff is None else CUTOFF - timedelta(minutes=minutes_before_cutoff)
    return NewsItem(headline=headline, source=source, url=f"https://x/{headline}", published_at=published)


def test_items_after_cutoff_are_excluded_and_counted():
    result = select_news([_item("before", 30), _item("after", -1), _item("way after", -59)], CUTOFF)
    assert [i.headline for i in result.items] == ["before"]
    assert result.excluded_after_cutoff == 2


def test_item_exactly_at_cutoff_is_allowed():
    result = select_news([_item("at cutoff", 0)], CUTOFF)
    assert [i.headline for i in result.items] == ["at cutoff"]


def test_undated_items_are_excluded_never_assumed_fresh():
    result = select_news([_item("dated", 10), _item("undated", None)], CUTOFF)
    assert [i.headline for i in result.items] == ["dated"]
    assert result.excluded_undated == 1


def test_items_older_than_lookback_are_excluded():
    result = select_news([_item("fresh", 60), _item("stale", 25 * 60)], CUTOFF, lookback_hours=24)
    assert [i.headline for i in result.items] == ["fresh"]
    assert result.excluded_too_old == 1


def test_duplicates_across_sources_are_counted_once():
    items = [
        _item("Bitcoin climbs above $80,000 as markets rally", 30, "A"),
        _item("Bitcoin climbs above $80,000 as markets rally", 20, "B"),
        _item("Ethereum upgrade delayed again", 10, "C"),
    ]
    result = select_news(items, CUTOFF)
    assert len(result.items) == 2
    assert result.excluded_duplicate == 1


def test_the_fetch_time_never_becomes_the_cutoff():
    # Even if these items were fetched an hour after the cutoff, the selection depends
    # only on the cutoff passed in -- there is no "now" anywhere in select_news.
    late_fetch_items = [_item("published in the gap", -30)]
    assert select_news(late_fetch_items, CUTOFF).items == []


def test_availability_time_uses_the_later_of_published_and_updated():
    published = (2026, 9, 19, 10, 0, 0, 0, 0, 0)
    updated = (2026, 9, 19, 12, 0, 0, 0, 0, 0)
    assert availability_time({"published_parsed": published, "updated_parsed": updated}) == datetime(
        2026, 9, 19, 12, 0, tzinfo=timezone.utc
    )
    assert availability_time({"published_parsed": published}) == datetime(2026, 9, 19, 10, 0, tzinfo=timezone.utc)
    assert availability_time({"updated_parsed": updated}) == datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)
    assert availability_time({}) is None
