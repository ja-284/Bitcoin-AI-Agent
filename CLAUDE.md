# Bitcoin AI Analysis Agent

## Project Goal

An AI-assisted system that checks on Bitcoin on a regular schedule and produces one of three signals — **BUY, HOLD, or SELL** — along with a **confidence level** and a **plain-language explanation**.

It looks at price/history, trends, volume, momentum (technical indicators), chart patterns, and relevant news. Each of these gets its own score, and the scores combine into one overall score plus a confidence level.

The system leans on solid, deterministic math (indicators, formulas) for anything math can reliably do, and uses AI specifically where AI adds real value (mainly reading/interpreting news, and writing explanations) — not as a vague "will Bitcoin go up?" question.

**This is analysis only.** It does not place real trades — not in this phase, and not any time soon.

## Current Phase: Phase 1

Scope: build the **backend**, the **AI agent**, and the **analysis engine** only. No frontend yet — that comes later, built separately in Lovable.

Once running, Phase 1 should operate on its own on a schedule (roughly hourly), without needing the user's phone or computer to be on. Each automatic run should roughly:

1. Collect fresh Bitcoin market data
2. Calculate relevant indicators and features
3. Collect relevant news
4. Analyze all of it
5. Run the scoring system
6. Produce BUY/HOLD/SELL, a confidence level, and an explanation
7. Store the full analysis in a database/log
8. (Later) compare each prediction with what actually happened afterward

## Important Principles

These rules govern every decision in this project. They should not be broken without stopping to discuss it first.

1. **Build the intelligence before the UI** — get the analysis right before worrying about how it looks.
2. **Prioritize data quality** — good data matters more than clever code.
3. **Avoid data leakage** — when testing against old data, the system must never be given information it wouldn't have actually known at that point in time.
4. **Avoid overfitting** — don't tune the system to match old data perfectly; that makes it good at explaining the past and bad at predicting the future.
5. **Log everything important about every prediction** — full inputs, scores, and outputs, every single run.
6. **Make confidence measurable and calibratable, not guessed** — confidence has to be checked against real outcomes over time, never just a number the AI states on its own.
7. **Test every meaningful change against historical data** before trusting it.
8. **Don't assume a signal is good just because the AI's explanation for it sounds convincing** — a persuasive-sounding explanation is not evidence that the call was right.
9. **Keep the architecture modular** — the AI model, data providers, technical indicators, scoring system, news sources, database, and frontend must each be swappable without rebuilding everything else.
10. **No real trading** — this project stays analysis-only for now, and for the foreseeable future. Do not implement real trading in this phase or any time soon.

## Architecture Decisions Log

_Decisions get added here once they're actually made and approved together with the user — not before._

Phase 1 architecture **approved 2026-09-19**. Full reasoning lives in the approved plan (`C:\Users\aarsn\.claude\plans\jolly-leaping-lampson.md`); this is the durable summary for future sessions:

- **Language**: Python — best-fit ecosystem for data handling, indicators, and AI glue code; no performance need to justify anything else.
- **Scheduling**: GitHub Actions scheduled workflow (hourly, off-peak minute) + a free heartbeat/dead-man's-switch alert (e.g. healthchecks.io) to catch silently-skipped runs. Repo recommended public (unlimited free Actions minutes, and there's nothing proprietary to protect); user may choose private instead — their call.
- **Market data**: CoinGecko (primary) + Binance public API (automatic backup) — aggregated price beats a single exchange, and price data is critical enough to need a fallback (missing it blocks the whole hourly run).
- **News**: Free RSS feeds from reputable outlets (e.g. CoinDesk, Cointelegraph). CryptoPanic's API turned out to be paid-only now (checked, not assumed). Headline + short snippet only, no full-article scraping; de-duplicate stories that appear on multiple feeds.
- **Database**: Supabase (hosted Postgres) — reachable from a cloud job, comfortably covers Phase 1 data volume on the free tier, and is the natural fit for the future Lovable frontend. Watch item: free projects auto-pause after 7 days idle; hourly writes should prevent this, but verify in practice during the first couple of weeks.
- **AI**: Claude, used in exactly two narrow, structured calls per run — never a free-roaming autonomous agent. (1) News headlines → a structured sentiment/relevance score (Haiku 4.5). (2) Final plain-English explanation, generated *after* the decision is already made by deterministic scoring — it narrates the result, it never judges or restates confidence. Estimated cost: well under $10/month at hourly cadence.
- **Confidence**: calculated from (a) agreement between category scores and (b) data completeness — never AI-guessed. Individual components are logged, not just the final blended number. Labeled explicitly as "a consistency/completeness estimate, not yet a calibrated probability" until enough real outcome history exists to actually calibrate against.
- **Indicators library**: pandas-ta-classic (the actively maintained community fork; the original pandas-ta looks at risk of going unmaintained).
- **Chart patterns**: simple deterministic rules only in Phase 1 (e.g. moving-average crossovers, higher-highs/higher-lows structure) — no image-based pattern recognition yet.
- **Module map & build order**: see the full plan file — 13 build steps from project skeleton through to scheduled go-live, each module with a narrow, swappable interface (settings, market data, indicators, patterns, news, scoring, AI, decision/confidence, database, orchestrator, backtest runner, outcome tracker).

## Status

- Phase 1 plan approved 2026-09-19. Implementation started same day.
- Built and tested against real live data: market data (Binance primary, CoinGecko backup), indicators, chart patterns, news (RSS), scoring, and the decision/confidence step. Verified end-to-end with `run.py`. Committed locally to git (not yet pushed to GitHub).
- Implementation refinement vs. the original plan text: **Binance is the primary price source, CoinGecko is the backup** (swapped from the plan's initial framing). Reason found while building: CoinGecko's free OHLC endpoint doesn't actually include volume data, and volume is one of the required analysis categories. Binance's public endpoint gives true open/high/low/close/volume directly. Both sources are still used, exactly as planned — just swapped which one leads.
- AI module and database are now built and working end-to-end. First real prediction saved to Supabase 2026-09-19. Anthropic API key and Supabase connection both live in `.env` (git-ignored).
- Lesson worth keeping (rule 8 in action): the first AI-written explanation confidently described "agreement" as covering all five categories, when it actually covers only the independent ones. The prompt in `agent/ai/explainer.py` now states precisely what each confidence component measures and passes each category's independence flag. A convincing explanation was wrong about our own math — worth re-checking whenever the explainer prompt or confidence formula changes.
- Still to build: the backtest runner, the outcome tracker, and scheduling/go-live (GitHub Actions + heartbeat alert).
