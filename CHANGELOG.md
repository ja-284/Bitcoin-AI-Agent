# Changelog

Two version stamps travel with every prediction (see `agent/version.py`):
**pipeline** (how data is gathered, time-bounded and validated) and **scoring**
(the formulas, weights and thresholds). They move independently so that later
analysis can always tell which version produced a row.

## pipeline 0.2.0 — 2026-09-19 (corrected, leakage-safe baseline)

Scoring formulas unchanged (still 0.1.0). Fixes only.

- **Information cutoff made explicit.** Every prediction carries `cutoff_at` = close
  of the reference candle. Previously the reference price was that close but news was
  collected up to the run's fetch time, 17–84 minutes later in practice — headlines from
  that gap leaked into predictions (severe at the 1h horizon).
- **News limited to the cutoff.** Only items whose availability time is in
  `(cutoff − 24h, cutoff]` are used. Availability time = the later of the feed's
  published/updated timestamps. Every exclusion is counted in `run_meta.news`.
- **Undated news excluded.** Items with no trustworthy timestamp are dropped and
  counted; they were previously treated as published "now".
- **Idempotent early exit.** A run for an hour that is already saved stops before any
  AI call. Enables the retry slot below at zero cost.
- **Schedule hardened.** Two slots per hour (:17 and :47), a self-check step that fails
  the job when no row landed, and an independent 3-hourly watchdog (`watchdog.yml`).
  GitHub skipped 6 of the first 7 hourly slots on go-live day.
- **Candle validation.** Duplicates, out-of-order rows, NaN, impossible OHLC, partial
  candles and misaligned timestamps raise; gaps are flagged in `run_meta.price_data`
  and never filled. Invalid provider output triggers the fallback provider.
- **Fallback volume.** On CoinGecko (synthetic) bars the volume category is marked
  unavailable instead of scored on a rolling-24h figure. CoinGecko snapshots are
  assigned to the hour they fall in (last snapshot per hour).
- **Backtest outcomes by timestamp.** "H hours later" = the candle that opened at
  `as_of + H`; a missing candle yields an unavailable outcome, never the next row.
  Windows containing a gap are flagged.
- **Backtest window = live window.** Each simulated hour is analysed from exactly
  `HISTORY_HOURS` (250) bars, as live runs are. The previous growing window gave
  different RSI/MACD values from live.
- **Outcome tracker.** Python-side timing guard mirroring the SQL rule, exact-timestamp
  check, `unavailable` status after a 6h grace period, horizons 1/6/24/72/168h.
- **Schema.** `predictions`: `cutoff_at`, `pipeline_version`, `run_meta`;
  `prediction_outcomes`: `status`, nullable price/return. Rows from before this
  version are stamped `pipeline_version = '0.1.0'`; their news was **not** cutoff-limited.

Rows affected: predictions 1–4 (2026-09-19 09:00–17:00) are pipeline 0.1.0.

## pipeline 0.1.0 / scoring 0.1.0 — 2026-09-19 (go-live)

First working version. Binance/CoinGecko prices, RSS news scored by Claude Haiku 4.5,
explanation by Claude Sonnet 5, five-category weighted score, ±0.15 thresholds,
agreement/completeness confidence heuristic, Supabase storage, hourly GitHub Actions.
