# Changelog

Two version stamps travel with every prediction (see `agent/version.py`):
**pipeline** (how data is gathered, time-bounded and validated) and **scoring**
(the formulas, weights and thresholds). They move independently so that later
analysis can always tell which version produced a row.

## scoring 0.2.0 — 2026-09-22 (history counted in consecutive hours)

The first change to the scoring since go-live, made on the user's decision after the flaw was
found and quantified on 2026-09-22. **Formulas, weights and thresholds are untouched.** What
changed is what "enough history" means: it counted ROWS, so a window containing missing hours —
an exchange outage — was treated as consecutive.

- **Indicators** are computed on the longest unbroken hourly run ending at the reference candle
  (`consecutive_tail`); an indicator whose warm-up does not fit inside that run is unavailable
  rather than computed across the hole. A "200-hour average" could previously span 233 hours.
- **The volume category** looks its reference candle up **by timestamp**; before, it counted six
  rows back, which with a gap could be a candle up to 33 hours from the 6 it intends — the same
  row-counting mistake pipeline 0.2.0 fixed in the outcome lookup.
- **Chart patterns**: the 20-hour trend-structure window must be 20 real consecutive hours.
- `IndicatorSet` now records `window_hours` and `consecutive_hours`, so every row says what it
  actually saw.

**Verified against history before deployment (E016, principle 7).** Full replay of 68,619 hours
under both versions:
- on the 62,262 hours whose window has **no gap — every live hour so far — the output is
  identical**: same signals, same patterns, and **zero** numeric difference in every field
  checked. This is the safety property, and `tests/test_scoring_golden.py` pins it.
  *(Correction, same day: the first write-up quoted a worst difference of 1.46e-11 and blamed
  CSV precision. Both were wrong — the comparison script read the cache with pandas' default
  float parser, which loses up to 7.28e-12. The csv module and `float_precision="round_trip"`
  are exact, and the two replays agree bit for bit. Every research CSV loader now passes
  `round_trip`, and `tests/test_numeric_precision.py` keeps it that way.)*
- on the 6,357 gap-affected hours (9.26%), mean completeness falls 0.850 → 0.568 and the signal
  changes on 2,702 of them (42.5%), because trend becomes unavailable on 81%, chart pattern on
  32%, volume on 8% and momentum on 6%. Across the whole record 3.94% of hours change signal.
- 392 hours now have no usable category at all and report completeness 0 — an honest "this hour
  is unknowable" instead of a confident number built on holes.

Consequence for earlier work: E001, E002 and E011 evaluated scoring 0.1.0 and remain valid
statements about 0.1.0. They were null results, and 0.2.0 only removes silently-wrong inputs,
so their direction cannot be reversed by this — but any future comparison must state its version,
and the weekly report now prints the scoring-version mix of the live record.

## pipeline 0.2.0 — incident fix 2026-09-22 (information rules unchanged, version kept)

Full post-mortem: `docs/ops/incident_2026-09-21_shadow_step.md`. The live record was never
affected (18 of 18 hourly predictions in the window, no fallback data, no timestamp
violations, parity 62/62); the hourly job went red on ~half of all runs because of the
research shadow step added on 2026-09-21.

- **Root cause fixed.** The feature-definition guard hashed feature values printed to 12
  significant digits; GitHub's runners differ from the development machine in the last few
  bits, so `load_model()` raised on ~half of all runs (measured: a 1e-14 relative difference
  flips that hash 56% of the time). The guard now stores feature reference **values** in the
  model artefact and compares them with `rtol = 1e-6` — a real definition change is caught,
  platform floating-point noise is not.
- `move_size_1h_v1` regenerated with the new guard metadata; every model number and all
  training metadata verified identical first, so the model and its prospective record are
  unchanged. Artefact hash re-pinned.
- **A shadow failure is now recorded, not crashed on.** New append-only table
  `shadow_run_errors` (stage, error type, message, git commit, expected hour). The step exits
  0 once the failure is recorded and 1 if it cannot record it. The live prediction is saved
  and self-checked before this step regardless.
- **Watchdog alarm** for persistent shadow failures (> 2 in 6 h): `agent.healthcheck
  --shadow-errors-max`.
- **Weekly report**: shadow-job errors section; the pre-registered prospective rule is now
  enforced in code (a row written after its outcome candle closed is shown separately and
  excluded from the evaluation).
- **Second, unrelated defect fixed the same day** (found while reading the weekly report): the
  news scorer's `max_tokens` was 2048, room for ~50 headlines, and each assessment echoes its
  headline. The live 24h news window grew from 16 items (09-19) to 63 (09-22), so from
  2026-09-21 20:00 to 2026-09-22 12:00 UTC every answer was truncated and **17 predictions were
  made with news unavailable** (weight 0, `completeness_score` 0.85, `run_meta.news_error` set —
  the rows say so themselves). `max_tokens` is now a named constant at 16384 (~350 headlines);
  the prompt and schema are unchanged, so E009 still applies. A parsing failure now names
  truncation as the likely cause. Verified on the real volume (59 headlines scored).
- **The test suite now runs on GitHub's runners on every push** (`.github/workflows/tests.yml`)
  — the check that would have caught the first defect before it reached production.
- **Third defect of the same class, found by auditing for it and closed before it bit:** a
  truncated *explanation* would have been stored silently (unlike the news answer, cut-off
  prose is still readable text). `write_explanation` now refuses a response whose
  `stop_reason` is `max_tokens`, so the hour is recorded with `explanation_error` and no text
  rather than half a sentence presented as a whole one. Live explanations run 170–265 tokens
  against a 1024-token cap (~4× headroom), so nothing was affected in practice.

## pipeline 0.2.0 — hardening 2026-09-21 (Backend Phase B; information rules unchanged, version kept)

Robustness only. Nothing about what a prediction may know, or how it is scored, changed;
the weekly parity check reproduces every live hour before and after.

- **Exchange answers are schema-checked**: an error object or a wrongly shaped candle list is
  a `KlineSchemaError` (→ fallback), never parsed as data. One retry per endpoint for
  transient errors; rate-limit answers (429/418) are not retried on the same endpoint.
- **Stale data is a provider failure**: the newest candle must be the last closed hour;
  otherwise the provider is skipped (→ fallback), and if every provider is stale the run
  fails loudly instead of predicting an old hour.
- **Zero-volume candles are counted** in `run_meta.price_data.zero_volume_bars`.
- **RSS downloads are bounded** (15 s timeout, explicit User-Agent); `feedparser.parse(url)`
  had no timeout and could hang the job until the runner killed it.
- **AI calls are bounded** (90 s timeout, 2 retries) instead of the SDK's 10-minute default;
  **database connections** get a 15 s connect timeout.
- `run_meta.code_commit` records the exact git commit that produced the row (GitHub runs).
- Shadow record (Phase 13): `agent/shadow` — see `research/ROADMAP.md`.
- **Database invariants (Phase E)**: NOT NULL on `cutoff_at`/`pipeline_version`; CHECKs for the
  cutoff rule, fetch-after-cutoff, outcome status and status/values consistency; predictions
  and outcomes are append-only (triggers); shadow rows immutable except a one-time outcome.

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
