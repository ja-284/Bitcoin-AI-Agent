# Experiment log

Every meaningful experiment gets one row here and one JSON file in `research/experiments/`
(`EXXX_<slug>.json`, schema in `research/experiments/README.md`). This log exists so we can
always answer: what changed, why, what we expected, what happened, was it consistent, and
did it change the design. Exploratory results are hypotheses; only confirmatory results
(pre-registered criteria, then a single evaluation) count as evidence.

## Ground rules (from the research brief, 2026-09-19)

- Fix and verify the pipeline before researching; research before changing scoring.
- One change at a time. Predefine the acceptance criterion before running.
- Time-ordered splits only. The final holdout is evaluated once, at the end.
- Label definitions, horizons and thresholds are explicit and configurable; changing one is itself a logged decision.
- Confidence is a heuristic until calibrated on validation data and checked on the holdout.
- Free data only. Unavailable or untrustworthy history is marked UNAVAILABLE/UNSAFE, never fabricated.
- Historical news is unavailable (no archive; LLM training knowledge would leak). News is evaluated only on the live archive, once large enough.

## Data range and split (from the verified Binance history, 2017-08-17 → present)

| Period | Range (UTC) | Use |
|---|---|---|
| Warm-up | first 250 hours | never scored |
| Exploration | 2017-08-27 → 2023-12-31 | look freely, form hypotheses |
| Validation | 2024-01-01 → 2025-06-30 | a change must also hold here to be accepted |
| **Final holdout** | 2025-07-01 → 2026-08-19 | **sealed** — evaluated once, after all design decisions |
| Contaminated buffer | 2026-08-20 → 2026-09-19 | seen once (aggregate means, scoring 0.1.0) during build; excluded from confirmatory use |
| Live record | 2026-09-19 → | the ultimate out-of-sample test; includes news |

Any accidental look at the holdout must be recorded here immediately and the period declared contaminated.

## Log

| ID | Date | Status | Type | What | Conclusion |
|---|---|---|---|---|---|
| E000 | 2026-09-19 | done | sanity | Corrected pipeline 0.2.0, scoring 0.1.0, 30-day technical-only replay (2026-08-20 → 2026-09-19, i.e. the contaminated buffer) to confirm the corrected runner works end-to-end | Runner works; outcomes-by-timestamp and gap flags behave; numbers not evidence of anything (single window, buffer period) |
| E001 | 2026-09-19 | done | exploratory (pre-registered criterion) | Scoring 0.1.0 vs trivial baselines over exploration (2017–2023) and validation (2024–mid 2025), horizons 1/6/24/72/168h, binary + three-class labels, block-bootstrap CIs, per year, per regime; confidence reliability | **Criterion not met at any horizon.** No edge beyond buy-and-hold drift; direction accuracy 47–50% (below always-UP); year-to-year sign flips; confidence heuristic uninformative (stated 0.7–0.9, observed ~0.48 everywhere, ECE ≈ 0.37). Do not tune 0.1.0. Next: per-category diagnosis and ablation. |
| E002 | 2026-09-20 | done | exploratory (pre-registered criterion) | Each category alone vs forward returns (rank correlation, block-bootstrap CI, both periods), decile shapes, leave-one-out ablation, redundancy | **No category carries positive information at any horizon.** Momentum and volume are weakly *anti*-correlated with the next hour's return in both periods (|ρ| 0.02–0.04: real, useless). trend↔chart_pattern 0.69 correlated. Conclusion: new information sources are needed, not re-weighting. Nothing flipped or tuned. |
| E003 | 2026-09-20 | done | exploratory (pre-registered criterion) | Volatility group (8 features from candles): direction and magnitude vs forward returns at 5 horizons, both periods, block-bootstrap CIs; interaction with E002's 1h effect | **Magnitude: strong and consistent at 1–24h** (ρ 0.13–0.45; monotonic deciles) — recent volatility predicts the *size* of the next move. Direction: five correlated features pass at 1h/6h with a tiny positive sign (|ρ| ≤ 0.05): consistent, negligible, not a signal. Adopt `tr_mean_14_rel` as the uncertainty input; use volatility-scaled neutral bands; calibration (Phase 11) must condition on volatility. |
| E004 | 2026-09-20 | done (re-run) | exploratory (pre-registered criterion) | Regime / long-horizon trend group (7d, 30d, 90d trailing returns; distance to 50d/200d averages). **First run invalid for one feature** (name collision made the target overwrite the feature → ρ = 1.000; caught by the too-good-to-be-true rule; harness hardened with name checks + a tripwire; re-run) | **No directional information that holds in both periods.** Monthly momentum shows up 2019–21 and reverses 2022–25; validation signs negative for every feature. Magnitude: nothing beyond E003. Regime conditioning flips between periods. Nothing adopted. |
