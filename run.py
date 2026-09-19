"""
Manual dry run of everything built so far: real price data -> indicators -> chart
patterns -> real news -> scoring -> decision. This intentionally stops short of the
AI explanation step and the database (those need an Anthropic API key and a Supabase
project, which aren't set up yet) -- everything else is real, live, and working.
"""

from datetime import datetime, timezone

from agent.data_providers.market_data import get_hourly_bars
from agent.decision.decision import compute_confidence, decide_signal
from agent.indicators.engine import compute_indicators
from agent.news.news_service import get_recent_news
from agent.patterns.rules import detect_patterns
from agent.scoring.scorer import score_all

HISTORY_HOURS = 250  # enough for every indicator's warm-up period (the 200h SMA is the longest)


def main() -> None:
    fetched_at = datetime.now(tz=timezone.utc)

    bars = get_hourly_bars(HISTORY_HOURS)
    indicators = compute_indicators(bars)
    patterns = detect_patterns(bars, indicators)
    news = get_recent_news()

    result = score_all(bars, indicators, patterns, news_score=None)
    signal = decide_signal(result.overall_score)
    confidence = compute_confidence(result)

    print(f"As of (last closed hour): {bars[-1].as_of.isoformat()}")
    print(f"Fetched at:               {fetched_at.isoformat()}")
    print(f"Price data source:        {bars[-1].source} (synthetic={bars[-1].is_synthetic})")
    print(f"Close price:              ${indicators.close:,.2f}")
    print()
    print("Category scores:")
    for c in result.category_scores:
        flag = "" if c.weight > 0 else "  (no data this run)"
        print(f"  {c.name:15s} score={c.score:+.2f}  weight={c.weight:.2f}  independent={c.is_independent}{flag}")
    if indicators.insufficient_history:
        print("\nIndicators skipped due to insufficient history:")
        for note in indicators.insufficient_history:
            print(f"  - {note}")
    print()
    print(f"Overall score:  {result.overall_score:+.3f}")
    print(f"Signal:         {signal}")
    print(f"Confidence:     {confidence.overall_confidence:.0%}  "
          f"(agreement={confidence.agreement_score:.0%}, completeness={confidence.completeness_score:.0%})")
    print()
    print(f"News: {len(news.items)} recent items, "
          f"{news.completeness:.0%} of sources reachable (failed: {news.sources_failed or 'none'})")
    for item in news.items[:5]:
        print(f"  - [{item.source}] {item.headline}")


if __name__ == "__main__":
    main()
