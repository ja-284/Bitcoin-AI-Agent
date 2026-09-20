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
- **Market data**: Binance public API (primary) + CoinGecko (automatic backup). The plan originally had these the other way round; swapped during the build because CoinGecko's free tier gives no true per-hour volume, and volume is a required analysis category. Binance is reached via its public data mirror (`data-api.binance.vision`) first, because the main API refuses US addresses and GitHub's job runners are US-based. Price data is critical enough to need a fallback: missing it blocks the whole hourly run.
- **News**: Free RSS feeds from reputable outlets (e.g. CoinDesk, Cointelegraph). CryptoPanic's API turned out to be paid-only now (checked, not assumed). Headline + short snippet only, no full-article scraping; de-duplicate stories that appear on multiple feeds.
- **Database**: Supabase (hosted Postgres) — reachable from a cloud job, comfortably covers Phase 1 data volume on the free tier, and is the natural fit for the future Lovable frontend. Watch item: free projects auto-pause after 7 days idle; hourly writes should prevent this, but verify in practice during the first couple of weeks.
- **AI**: Claude, used in exactly two narrow, structured calls per run — never a free-roaming autonomous agent. (1) News headlines → a structured sentiment/relevance score (Haiku 4.5). (2) Final plain-English explanation, generated *after* the decision is already made by deterministic scoring — it narrates the result, it never judges or restates confidence. Estimated cost: well under $10/month at hourly cadence.
- **Confidence**: calculated from (a) agreement between category scores and (b) data completeness — never AI-guessed. Individual components are logged, not just the final blended number. Labeled explicitly as "a consistency/completeness estimate, not yet a calibrated probability" until enough real outcome history exists to actually calibrate against.
- **Indicators library**: pandas-ta-classic (the actively maintained community fork; the original pandas-ta looks at risk of going unmaintained).
- **Chart patterns**: simple deterministic rules only in Phase 1 (e.g. moving-average crossovers, higher-highs/higher-lows structure) — no image-based pattern recognition yet.
- **Backtests are technical-only and never touch the predictions table.** RSS has no archive, so past news is unknowable; backtests run with news absent (weight 0) and are labeled as such — not directly comparable to live runs. Results go to CSV files under `backtests/` (git-ignored), keeping live data pure. The no-lookahead rule is enforced by construction (each hour sees only `bars[:i+1]`) and checked by `tests/test_point_in_time.py`.
- **Outcomes record raw prices and returns only.** Whether a signal was "right" is decided at analysis time (which horizon, what threshold, vs. buy-and-hold), never by the tracker. Horizons: 1h, 24h, 168h.
- **Module map & build order**: see the full plan file — 13 build steps from project skeleton through to scheduled go-live, each module with a narrow, swappable interface (settings, market data, indicators, patterns, news, scoring, AI, decision/confidence, database, orchestrator, backtest runner, outcome tracker).

## Status

- Phase 1 plan approved 2026-09-19. Implementation started same day.
- Built and tested against real live data: market data (Binance primary, CoinGecko backup), indicators, chart patterns, news (RSS), scoring, and the decision/confidence step. Verified end-to-end with `run.py`. Committed locally to git (not yet pushed to GitHub).
- Implementation refinement vs. the original plan text: **Binance is the primary price source, CoinGecko is the backup** (swapped from the plan's initial framing). Reason found while building: CoinGecko's free OHLC endpoint doesn't actually include volume data, and volume is one of the required analysis categories. Binance's public endpoint gives true open/high/low/close/volume directly. Both sources are still used, exactly as planned — just swapped which one leads.
- AI module and database are now built and working end-to-end. First real prediction saved to Supabase 2026-09-19. Anthropic API key and Supabase connection both live in `.env` (git-ignored).
- Lesson worth keeping (rule 8 in action): the first AI-written explanation confidently described "agreement" as covering all five categories, when it actually covers only the independent ones. The prompt in `agent/ai/explainer.py` now states precisely what each confidence component measures and passes each category's independence flag. A convincing explanation was wrong about our own math — worth re-checking whenever the explainer prompt or confidence formula changes.
- Outcome tracker, backtest runner (with point-in-time guard test), and the GitHub Actions hourly workflow (`.github/workflows/hourly.yml`, runs at :17 past each hour) are built. First real outcome row recorded 2026-09-19.
- First 30-day backtest of scoring v0.1.0 (2026-08-20 → 2026-09-19, technical-only): **no measurable edge.** BUY hours averaged +0.33% over 24h vs. +0.33% for all hours; SELL hours averaged +0.52%. Expected for a first formula. Do not tune weights against this window (rule 4) — collect live outcomes first, and keep a held-out period untouched when tuning does begin.
- **Live since 2026-09-19 12:20 UTC.** Code is on GitHub at `ja-284/Bitcoin-AI-Agent` (public, branch `main`); secrets ANTHROPIC_API_KEY and DATABASE_URL are set; the first manual run from GitHub's servers succeeded (42s) and wrote prediction #2. The schedule fires at :17 past each hour.
- Phase 1 scope is complete. The signal itself is NOT good yet (see backtest above) — "live" means the measuring instrument is switched on and collecting real outcomes, not that the analysis is finished. Improving the scoring is the next phase, done against accumulated live outcomes + a held-out period, never against a single backtest window.
- Watch items for the first weeks: (1) confirm scheduled runs actually fire (Actions tab; GitHub can delay or skip) — optional heartbeat via healthchecks.io + HEARTBEAT_URL secret not yet set up; (2) confirm Supabase doesn't auto-pause; (3) GitHub disables scheduled workflows on public repos after 60 days with no commits — any commit resets the clock, and GitHub emails a warning first.
- An older branch `claude/sleepy-fermat-wmrosq` on GitHub (2026-09-18, a first CLAUDE.md from a web session) is superseded and can be deleted.
- **E001 (2026-09-19): scoring 0.1.0 has no measurable predictive value.** 68,619 replayed hours, 2017 → mid-2025, five horizons, pre-registered criterion not met anywhere: no edge beyond buy-and-hold drift, direction accuracy 47–50% on acted hours (below always-UP), sign flips year to year, and the confidence heuristic is uninformative (stated 0.7–0.9, observed ≈ 0.48 in every bucket). **Do not tune 0.1.0's weights or thresholds.** Details: `research/results/E001/summary.md`.
- **Scheduling (2026-09-19/20):** GitHub's own cron ran 2 of 8 slots on day one; with four slots/hour it covered ~9 of 11 hours overnight. **Fixed 2026-09-20 08:12 UTC:** Supabase `pg_cron` + `pg_net` posts to GitHub's `workflow_dispatch` API at :12 each hour (token in Supabase Vault, `docs/ops/external_trigger.md`); first dispatched run started within 1 second and succeeded. GitHub's own four slots/hour remain as backup. If runs stop, check `cron.job_run_details` and `net._http_response` in Supabase first (a 401 there means the token is wrong/expired). The GitHub fine-grained token `supabase-dispatch` **expires 2027-09-20 — regenerate and re-store it before then.** Healthchecks.io heartbeat still not set up.
- **2026-09-19 evening — correctness phase (pipeline 0.2.0).** Inspection report found and the fixes addressed: GitHub skipped 6 of the first 7 hourly slots (now two slots/hour + self-check + watchdog); news leaked past the reference candle's close (now an explicit `cutoff_at`, news limited to it, undated items excluded); backtest outcomes were found by row count not timestamp (fixed; gaps → unavailable); backtest used a growing window unlike live (fixed: exactly 250 bars); fallback volume was scored on a rolling-24h figure (now unavailable); no candle validation (added; gaps flagged, never filled); outcome tracker guards and `unavailable` status. Full list in `CHANGELOG.md`. 43 tests. Predictions 1–4 are pipeline 0.1.0 (news not cutoff-limited).

## Research phase — rules and decisions (2026-09-19)

The user's research brief (from ChatGPT, reviewed and adopted) governs everything after Phase 1. Its order is binding: **fix → prove the fixes → evaluate what exists → improve only on evidence.** Decisions already made:

- **Time split** is defined in `research/EXPERIMENTS.md`. The **final holdout (2025-07-01 → 2026-08-19) is sealed** — never inspected, tuned on, or used to pick anything; evaluated once at the very end. The 30 days before go-live are a contaminated buffer (seen once). The live record from 2026-09-19 is the ultimate test.
- **Primary horizon is NOT decided.** Evaluate 1h, 6h, 24h (and 72h, 168h) with one consistent framework; choose on evidence.
- **Targets:** both binary direction (UP/DOWN) and three-class (UP/NEUTRAL/DOWN) with an explicit, configurable, documented definition (reference = close at cutoff; outcome = close of the candle opening at as_of+H; threshold fixed-% vs volatility-scaled to be tested, not assumed).
- **Free data only.** Anything paid, revised-after-the-fact, or without trustworthy historical timestamps is UNAVAILABLE/UNSAFE — never fabricated. Historical news is UNAVAILABLE (no archive; an LLM's training knowledge would leak).
- **Feature-group order** (after the baseline is evaluated, one at a time): volatility → regime → derivatives → macro → on-chain → news → microstructure → social; data quality overrides the order.
- **Experiment log:** `research/EXPERIMENTS.md` + one JSON per experiment in `research/experiments/`. Exploratory vs confirmatory is always stated.
- **Do not change** scoring formulas, weights, thresholds, or prompts until the corrected baseline (pipeline 0.2.0, scoring 0.1.0) has been evaluated against simple baselines with uncertainty, per year and per regime. Scoring 0.1.0 is the thing under test.
- **Confidence** stays a labelled heuristic until calibrated on validation data (Brier, log loss, reliability buckets with intervals) — never presented as a probability before then.
- **Overlapping outcome windows** (hourly predictions, multi-hour horizons) mean n hours ≠ n independent trials: use block bootstrap for uncertainty and an embargo ≥ horizon at any train/validation boundary once anything is fitted.
- The AI's roles stay separated (news → structured score; explanation after the decision) and must themselves be tested (schema reliability, faithfulness of explanations, whether news adds information beyond simpler alternatives).

**Research state (2026-09-20, E000–E009; details in `research/ROADMAP.md`, `research/EXPERIMENTS.md`):** Phases 1–5, 7, 8, 8A complete. 47 candidate features tested fit-free across volatility, regime, derivatives, macro, on-chain and microstructure: **no directional feature is usable**; a consistent but tiny 1–6h *reversal* family exists (momentum, volume, taker-buy share; |ρ| ≤ 0.05); **move size is predictable** (recent volatility ρ up to 0.45, trade intensity up to 0.30, plus a time-of-day effect). Live watch list for confirmatory re-tests: funding rate (24h contrarian, held 2019–23), dollar/yield 5-day changes (168h negative). AI components verified (E009): news scorer reliable with a small order-sensitivity bias; explainer faithful and provably decision-neutral. Next: Phase 6 (walk-forward with embargo) → Phase 9 (one pre-registered fitted-model test for direction; an uncertainty model for move size) → Phase 11 (calibration). The honest deliverable is shaping up as calibrated *uncertainty* plus HOLD-heavy signals, unless Phase 9 finds a combinable directional signal.

## How to run things

All commands from the project folder, using the virtual environment (`.venv\Scripts\python.exe` on Windows):

- `python run.py` — one full analysis, saved to the database (exits early if this hour is already saved). `--no-save` to skip saving.
- `python -m agent.outcome_tracker` — grade past predictions that are old enough.
- `python -m agent.healthcheck --max-age-hours 2` — exit 1 if the newest prediction is stale (used by the workflows).
- `python -m agent.backtest.runner --days 30` — technical-only backtest; CSV lands in `backtests/`. Never run it over the sealed holdout.
- `python -m pytest tests/` — run the tests (no network or database needed).
- Fresh database: `python -c "from agent.database.db import init_schema; init_schema()"` (safe to re-run; also applies migrations at the bottom of `schema.sql`).
