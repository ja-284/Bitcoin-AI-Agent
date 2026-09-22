# Failure modes — what the hourly job does when things break (Backend Phase C)

Principle: **fail loudly or degrade visibly; never fill in, never guess, never write a bad row
silently.** Every row records what degraded it (`run_meta`), and a missed hour stays missed —
it is never back-filled, because the news it would have needed no longer exists in
point-in-time form.

| failure | what happens | recorded where | prediction? | proven by |
|---|---|---|---|---|
| Binance unreachable / times out | one retry per endpoint, then the mirror, then **CoinGecko fallback** | `run_meta.price_data.provider = coingecko`, `price_is_synthetic = true` | yes, volume category weight 0 | `test_market_data_fallback.py`, `test_data_hardening.py` |
| Binance answers with an error object or a malformed body | `KlineSchemaError` → treated as provider failure → fallback | provider log warning | as above | `test_data_hardening.py` |
| Binance rate-limits (429/418) | endpoint skipped without retry → mirror → fallback | warning | as above | `test_data_hardening.py` |
| provider returns stale data (newest candle ≠ last closed hour) | provider failure → fallback; **all stale → run fails** (no old-hour prediction) | exception; job step red; watchdog | **no** | `test_market_data_fallback.py` |
| duplicate / out-of-order / NaN / impossible OHLC / unclosed candle | `BarValidationError` → provider failure → fallback | warning | as above | `test_candle_validation.py` |
| gap inside the 250-candle window | flagged, never filled; indicators run on the bars as given | `run_meta.price_data.gaps`, `missing_hours` | yes | `test_candle_validation.py` |
| zero-volume candle | counted | `run_meta.price_data.zero_volume_bars` | yes | `test_market_data_fallback.py` |
| fewer candles than the indicators need | `insufficient_history` listed; affected categories unavailable | `raw_indicators.insufficient_history`; completeness < 1 | yes, lower completeness | `test_failure_modes.py` |
| one RSS feed fails / times out (15 s) | the others continue | `run_meta.news.sources_failed` | yes | `test_data_hardening.py`, `test_news_cutoff.py` |
| all RSS feeds fail | news step fails → news weight 0 | `run_meta.news_error` | yes, news unavailable | `test_failure_modes.py` |
| news model times out (90 s, 2 retries) or answers nothing / garbage | news step fails → news weight 0 (**unavailable, not neutral**) | `run_meta.news_error`, `ai_model_news = null` | yes | `test_failure_modes.py` |
| news model assesses fewer headlines than given | score used, mismatch flagged | `category_scores[news].detail.assessment_count_mismatch` | yes | `test_failure_modes.py` |
| news model returns out-of-range numbers | rejected by the schema (pydantic) → news_error | `run_meta.news_error` | yes | `test_failure_modes.py` |
| explainer fails / times out | prediction saved without text; decision untouched | `run_meta.explanation_error`, `explanation = null` | yes | `test_failure_modes.py`, `test_explainer_isolation.py` |
| database unreachable before the run | `prediction_exists` raises → run fails before any AI call | job step red | no; next slot retries | code order (`orchestrator.run_once`) |
| database unreachable at save time | run raises; the AI cost is spent, the row is lost; next slot recomputes | job step red | no (this slot) | `test_failure_modes.py` |
| the same hour runs twice (four cron slots + dispatch) | second run exits before any AI call; `INSERT … ON CONFLICT (as_of) DO NOTHING` as the last line of defence | log "already exists" | one row, never two | `test_orchestrator_cutoff.py`, `test_failure_modes.py`, `UNIQUE(as_of)` |
| a run is late (e.g. :50) | `as_of` comes from the candle, not the clock; `lag_seconds_after_cutoff` records the delay | `run_meta.lag_seconds_after_cutoff` | yes, correct hour | `test_failure_modes.py` |
| a run is missed entirely | the hour stays missing (no back-fill by design); healthcheck fails the next job if > 2 h stale; watchdog every 3 h; weekly report lists missing hours | Actions failure email; weekly report | no | `agent/healthcheck.py`, `watchdog.yml` |
| outcome candle missing (exchange gap) | outcome `unavailable` after a 6 h grace — never the neighbouring candle | `prediction_outcomes.status` | — | `test_outcome_tracker.py`, `test_horizon_lookup.py` |
| outcome lookup fails (network) | left ungraded; retried next hour | warning | — | `test_outcome_tracker.py` |
| shadow: **any** failure (exchange down, malformed answer, artefact missing, guard mismatch, DB write refused) | recorded in `shadow_run_errors` with the stage and the exception; the step exits 0 so the live record's job stays green; that hour has no shadow row | `shadow_run_errors`; weekly report §3; watchdog fails on > 2 errors in 6 h | live yes; shadow no | `test_shadow.py::test_run_and_record_*`, `test_healthcheck.py`, integration test |
| shadow: failure that cannot even be recorded (database unreachable) | step exits 1 → job red, because an unrecorded failure would be invisible | Actions failure email | live yes (saved earlier) | `test_shadow.py` |
| shadow: missing input (gap, zero-trade candle) | row stored as `unavailable` with the reason; no probability | `shadow_move_size.status_reason` | shadow blank | `test_shadow.py` |
| shadow: feature definitions changed since the model was fitted | `load_model` raises `ModelVersionError` (values compared with `rtol = 1e-6`, so platform noise never triggers it) → recorded as above | `shadow_run_errors` | live unaffected | `test_shadow.py` (both directions) |
| shadow: concurrent duplicate | `ON CONFLICT (as_of) DO NOTHING` | log | one row | `agent/shadow/db.py` |
| research: holdout requested by accident | loader truncates at the holdout start unless `allow_holdout=True` with a reason (logged to `research/HOLDOUT_ACCESS.log`) | log file | — | `test_research_guards.py` |

## Known residual risks (accepted, documented)

- A database outage at save time wastes one hour's AI calls (cents) and, if it lasts across
  all slots of the hour, loses that hour of the live record. Acceptable: the record is
  research data, not a trading system, and the gap is visible.
- CoinGecko fallback rows are approximate (snapshot prices, rolling volume). They are
  flagged and excluded from research use; 0 so far.
- GitHub's own cron remains unreliable (≈ 20 % of slots fire); the Supabase dispatch at :12
  is the primary trigger. If Supabase's cron stopped, GitHub's slots would still cover most
  hours and the healthcheck/watchdog would flag the rest. A healthchecks.io heartbeat (not yet
  set up) would add an alarm outside both.
