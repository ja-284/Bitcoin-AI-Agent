# Live / research parity — the rules both sides follow (Backend Phase A)

*Question: if the research replay is run on the same candles for an hour the live job already
analysed, does it produce the same numbers? It must, or every historical result would be
about a different system than the one running.*

## The shared rules

| rule | live job (`agent/orchestrator.py`) | research replay (`agent/research/replay.py`) | how it is proven |
|---|---|---|---|
| reference candle | last **closed** hourly candle (`get_hourly_bars` drops the forming one) | `bars[i]`, one row per closed candle | `test_backtest_matches_live.py` |
| information cutoff | `as_of + 1h` (the reference candle's close), stored as `cutoff_at` | `as_of + 1h` | `test_orchestrator_cutoff.py`, `test_point_in_time.py` |
| feature window | exactly `HISTORY_HOURS` = 250 closed candles | exactly `bars[i+1-250 : i+1]` | `test_backtest_matches_live.py` (a growing window is shown to diverge) |
| indicators, patterns, scores | `compute_indicators → detect_patterns → score_all → decide` | the same functions, same order | replay calls the live functions; **`agent/research/parity.py` re-analyses every stored live hour on today's candles and compares close, volume, 9 indicators, 4 category scores + weights, overall score without news** — 44/44 hours identical on 2026-09-21 (weekly report §4) |
| news | live only, limited to `published_at <= cutoff_at`, undated excluded, duplicates once | **absent** (weight 0) — no archive exists | `test_news_cutoff.py`; the parity check recombines the live overall score with news at weight 0 before comparing |
| target / outcome | `outcome_tracker`: close of the candle **opening at** `as_of + H`, by timestamp; missing candle → `unavailable` after a 6h grace, never a neighbour | `labels.py`: same candle, same rule; missing → no label | `test_parity.py::test_live_tracker_and_research_labels_agree…`; live check: the weekly report compares the tracker's stored 1h returns with research candles (46/46 hours equal to 1e-16) |
| return unit | **fraction** (`0.0044` = +0.44%) in `pct_change_from_prediction` despite the name | fraction | `test_weekly_report.py` |
| fallback data | Binance → CoinGecko (synthetic bars, rolling-24h volume) — rows flagged `price_is_synthetic`, volume category weight 0 | **never** (Binance snapshot only) | `test_market_data_fallback.py`, `test_synthetic_volume.py`; parity check skips synthetic rows explicitly |
| gaps in the window | candles validated, gaps flagged in `run_meta.price_data`, never filled; the scoring-0.1.0 indicators run on the bars as given (a gap is *not* blanked — see "known differences") | same code, same behaviour | `test_candle_validation.py` |
| versions | `pipeline_version`, `scoring_version`, `ai_model_*` stored per row | replay cache named by pipeline + scoring version | parity check refuses to compare rows of another pipeline version |
| shadow move-size model | `agent/shadow`: research feature code on a 250-candle window, frozen artefact, own table | `agent/research/features.py`, `microstructure.py` on the full series | `test_shadow.py::test_window_features_equal_full_series_features`; two implementations (sklearn long-fetch vs numpy window) agree to 4 decimals on live hours |
| prediction timing | data fetched ~12 min after the cutoff (`fetched_at >= cutoff_at`, checked) | assumed available at the cutoff | closed candles are immutable, which the parity check verifies empirically every week (a revised candle would break `close_price`/`volume`) |

## Known, documented differences (not bugs)

1. **News exists only live.** Replays and backtests are technical-only; live and replay
   overall scores are compared only after removing the news category. Live signals can
   therefore differ from what a replay of the same hour would say — by design, and stated on
   every backtest.
2. **Scoring 0.1.0 does not blank a window that contains a gap** (both live and replay treat
   the 250 bars as consecutive). The research *features* (E003 onwards, and the shadow model)
   do blank any window touching a gap. Both are deliberate: the live scoring is the frozen
   thing under test; the research features follow the stricter no-fill rule. A gap inside the
   live window is recorded in `run_meta.price_data.gaps` so such hours can be excluded later.

   **Quantified 2026-09-22, and worse than "the indicators are slightly stale":** 6,357 of the
   68,619 replayed hours (**9.26%**) have at least one missing hour inside their 250-candle
   window — up to 33 missing hours in a single window — concentrated in 2017–2021 and ending
   2023-04. For those hours two things are off. The indicators are computed over a window that
   silently spans more than 250 hours; and `score_volume` compares `bars[-1]` with
   `bars[-1-24]` **by position**, so its direction term can be reading a candle up to 33 hours
   away from the 24 it intends. This is the same class of mistake that pipeline 0.2.0 fixed in
   the outcome lookup (row counting instead of timestamps), surviving inside frozen scoring.

   It is **not** being fixed here: scoring 0.1.0 is the object under test and changing it
   silently would invalidate every comparison made against it. It is recorded instead, with
   two consequences: the live record is unaffected so far (0 gap-affected hours since go-live,
   and `run_meta` marks any that occur), and any future *fitted* work on the replay should run
   a robustness check excluding the 9.26% of gap-affected hours. The decision on whether
   scoring should switch to timestamp-based lookups belongs with the user (it is a scoring
   change, so a version bump and a re-run of the affected baselines).
3. **Fallback rows** (`price_is_synthetic = true`) have no research counterpart and are
   excluded from parity and from any research use of the live record. Count so far: 0.
4. **Pipeline 0.1.0 rows** (the first four predictions) were written before the news cutoff
   existed and are not compared.

## What would break parity, and how it would be seen

- a code change to an indicator, pattern, weight or threshold without a version bump → the
  weekly parity check reports the exact hours and fields;
- an exchange revising a closed candle → `close_price` / `volume` breaks for that hour;
- a change to the window length on one side only → every hour breaks;
- a change to the target rule on one side only → `test_parity.py` fails.
