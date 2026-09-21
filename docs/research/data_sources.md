# Data sources — what each one provides and how it is trusted (Backend Phase B)

Rules that apply to every source: never fabricate a missing observation; prefer an explicit
`unavailable` to a filled-in number; the availability time of a datum is when it could have
been known, never when we fetched it; anything paid, revised after the fact, or without a
trustworthy historical timestamp is classed UNAVAILABLE/UNSAFE for research.

## Live pipeline (hourly job)

| source | provides | history | timestamp semantics | availability delay | known limitations | failure / fallback | point-in-time class |
|---|---|---|---|---|---|---|---|
| **Binance spot klines** (`data-api.binance.vision` first, `api.binance.com` second) | closed hourly OHLCV for BTCUSDT; kline fields 8/9 (trade count, taker-buy volume) for the shadow model | 2017-08-17 → ; 28 gaps / 128 missing hours (mostly 2018–19; last notable 2020-02-19, 2021-02) | `as_of` = candle **open** time UTC; the candle is final at open + 1h | ~seconds after the close; the job fetches ~12 min after | main API refuses US addresses (GitHub runners) → mirror first; 1,000 candles per request | schema-checked (list of 12-field lists; error objects rejected); one retry per endpoint for transient errors; no retry on 429/418; stale data (newest candle ≠ last closed hour) is a failure → **CoinGecko fallback**; both failing → the hour's run fails loudly, no prediction | SAFE (closed candles are immutable — verified weekly by the parity check) |
| **CoinGecko market_chart** (fallback only) | hourly-spaced price snapshots + rolling-24h volume | free tier, hourly points for `days ≥ 2` | snapshot a few minutes into the hour, assigned to that hour (floored) — older than the true close, never newer | minutes | not candles: open/high/low are synthetic; volume is a rolling 24h figure, not the hour's | rows flagged `price_is_synthetic = true`; volume category weight 0; excluded from research use and from parity | POTENTIAL RISK (approximate prices) — flagged, never mixed silently; used 0 times so far |
| **RSS feeds** (CoinDesk, Cointelegraph, Decrypt) | headline, link, summary (raw HTML possible), published/updated | **none** (no archive) — only what the feed shows at fetch time (~30–50 items) | availability = later of `published`/`updated`; undated items excluded; retrieval time = the run's `fetched_at` | feeds update within minutes of publication | duplicates across feeds; summaries contain HTML; a story stays in the 24h lookback across many runs (first-seen time = earliest `fetched_at` of a prediction containing its URL) | bounded download (15 s timeout, explicit User-Agent); one feed failing does not block the others (`run_meta.news.sources_failed`); all failing → news weight 0, run continues | SAFE for live (cutoff-limited: `published_at ≤ cutoff_at`); historical news UNAVAILABLE |
| **Claude (Haiku 4.5 news scorer, Sonnet 5 explainer)** | structured news score; plain-English explanation after the decision | n/a | n/a | 90 s timeout, 2 retries | non-determinism; order sensitivity (E009); the explainer cannot touch the decision (tested) | scorer failure → `run_meta.news_error`, news weight 0; explainer failure → `run_meta.explanation_error`, prediction saved without text | n/a (the numerical decision never depends on the LLM) |
| **Supabase Postgres** | predictions, outcomes, shadow rows | since 2026-09-19 | `as_of` reference hour; `cutoff_at`; `fetched_at`; `created_at` | — | free tier auto-pauses after 7 idle days (hourly writes prevent it) | 15 s connect timeout; a failed run is retried by the next slot (`prediction_exists` makes it idempotent) | — |

## Research-only sources (snapshots on disk, never in the hourly job)

| source | provides | history | timestamp semantics / availability rule | limitations | class |
|---|---|---|---|---|---|
| Binance USDⓈ-M funding (`fapi`) | settled funding rate every 8h | 2019-09-10 → | known at settlement time (+1 ms in the feed, normalised) | none for research | SAFE |
| Binance premium index klines | hourly premium index OHLC | 2019-12-24 → | closed candle at open + 1h | perp only | SAFE |
| Yahoo Finance daily (S&P, Nasdaq, DXY, gold, oil, 10y) | daily OHLC | years | **visible from 22:00 UTC on the trading date** (a margin after US close); weekends/holidays carry forward with `macro_staleness_h` recorded | Yahoo revises rarely; delisting risk | SAFE with the 22:00 rule |
| blockchain.info charts (hash rate, tx count, active addresses, fees) | daily values | 2009 → | day D **known from D+1 06:00 UTC** | estimated tx volume marked UNSAFE (revised) | SAFE with the D+1 rule |
| mempool.space difficulty adjustments | adjustment time, height, factor | 2009 → | known at the triggering block's time | — | SAFE |
| Open interest, liquidations, order-book depth/spread, social | — | no free, timestamped history | — | — | UNAVAILABLE |

## Candle validation (`agent/data_providers/quality.py`)

Impossible data **raises** (duplicates, out-of-order, NaN/inf, non-positive price, negative
volume, OHLC inconsistency, timestamp off the hour, a candle that has not closed). Gaps are
**flagged, never filled**; zero-volume candles are **counted** (`zero_volume_bars` in
`run_meta.price_data`) — real during exchange outages, always suspicious. A provider whose
newest candle is not the last closed hour is **stale** and counts as failed.

## What the hourly job stores about its data (`predictions.run_meta`)

`lag_seconds_after_cutoff`, `price_data` {provider, synthetic, bars, first, last, gaps,
missing_hours, zero_volume_bars}, `news` {fetched, used, excluded_after_cutoff,
excluded_undated, excluded_too_old, excluded_duplicate, sources_failed, cutoff},
`news_error` / `explanation_error` when they happen, and `code_commit` (the exact git
commit that ran, on GitHub).
