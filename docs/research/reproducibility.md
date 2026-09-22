# Reproducibility — what is stored, and what was re-derived from it (Backend Phase F)

## What a stored live prediction carries (`predictions`)

| need | column / field |
|---|---|
| prediction timestamp | `as_of` (reference candle open, UTC), `created_at` |
| information cutoff | `cutoff_at` (= `as_of` + 1h, enforced by a CHECK) |
| when the data was pulled | `fetched_at` (≥ `cutoff_at`, enforced), `run_meta.lag_seconds_after_cutoff` |
| reference price | `close_price`, `price_source`, `price_is_synthetic` |
| the inputs | `raw_indicators` (full indicator snapshot), `category_scores` (score, weight, independence, detail), `news_items` (headline, source, url, availability time) |
| the decision | `overall_score`, `signal`, `agreement_score`, `completeness_score`, `overall_confidence` |
| versions | `pipeline_version`, `scoring_version`, `ai_model_news`, `ai_model_explanation`, `run_meta.code_commit` (git SHA on GitHub runs) |
| data quality of the run | `run_meta.price_data` (provider, gaps, missing hours, zero-volume bars), `run_meta.news` (fetched / used / excluded counts, failed sources), `run_meta.news_error`, `run_meta.explanation_error` |
| later outcomes | `prediction_outcomes` (horizon, status, price at horizon, return as a fraction) — append-only |

## What a stored shadow row carries (`shadow_move_size`)

`as_of`, `cutoff_at`, `fetched_at`, `model_version` (frozen artefact incl. its Platt calibration), `pipeline_version`, `code_commit`, `price_source`, `reference_close`, `live_close_match`, `status`/`status_reason`, `features` (the raw input values), `p_raw`, `p_calibrated`, `threshold`, `horizon_hours`, and the outcome written once (`outcome_status`, `outcome_close`, `outcome_return`, `outcome_large`, `outcome_checked_at`).

## What an experiment carries (`research/experiments/*.json`, `research/results/*/`)

Hypothesis, pre-registered criterion, data snapshot names and ranges, periods, horizons, target definition, validation design, hyper-parameters, the exact command (roadmap), git commit, metrics, results, and the interpretation — plus per-run JSON/MD outputs. Per-hour prediction dumps are regenerable and git-ignored.

## Demonstrated on 2026-09-21

| claim | how it was checked | result |
|---|---|---|
| a live prediction can be rebuilt from candles + committed code | `agent/research/parity.py`: every live hour re-analysed by the replay on today's candles | 44/44 identical (close, volume, 9 indicators, 4 categories, overall score without news) |
| a shadow probability can be rebuilt from its stored features + the frozen artefact | `MoveSizeModel.predict(row.features)` vs stored `p_raw`/`p_calibrated` | agrees to **≤ 5e-16** on every stored row (2026-09-22: 13/13). Not bit-identical: the database returns 15 significant digits, so the stored number differs from the recomputed one in the 16th digit. Irrelevant at any scale a probability is used, but stated exactly rather than claimed as "identical" |
| an experiment can be re-run from its recorded command | E012 `size_expanding_1h` re-run to a scratch tag and compared with the committed JSON | n, Brier, accuracy, ECE, ρ **bit-identical** in exploration, validation and overall |
| the frozen model equals the research fit | artefact fit rows/ranges/Platt (a, b) vs the E013-style fit in the weekly paper record | identical (61,971 rows to 2025-03-30; a = 1.034, b = 0.196) |
| the live outcome tracker equals the research label rule | weekly report consistency check; `tests/test_parity.py` | 46/46 hours equal to 1e-16; unit test across a gap |

## Secrets

`.env` is git-ignored; only `.env.example` (placeholders) is tracked. Secrets live in `.env`
locally, GitHub Actions secrets, and the Supabase Vault. A scan of tracked files for
key-like strings (`sk-ant-`, `github_pat_`, connection strings with passwords, JWTs) found
none; a scan of every stored row's `run_meta`, `explanation` and `raw_indicators` found none.
Experiment records never contain credentials.

## Known limits

- Live rows made with the CoinGecko fallback (0 so far) cannot be rebuilt from Binance candles and are excluded from parity.
- The news scorer and explainer are LLM calls: their *inputs* and *outputs* are stored, but re-running them would not reproduce the same text or exactly the same scores. The numerical decision never depends on the explainer, and the news score's contribution is stored per run.
- Research data snapshots (`data/*.csv`) are git-ignored for size; their names are recorded in every experiment and they are re-downloadable from the same free sources (candles are immutable; Yahoo/blockchain.info may revise, which is why their point-in-time rules are conservative).
