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
| E005 | 2026-09-20 | done | exploratory (pre-registered criterion) | Derivatives group: settled funding rate (8h, since 2019-09) and hourly premium index (since 2019-12); open interest / liquidations marked UNAVAILABLE | **No pass.** The predicted contrarian sign (crowded longs → lower returns) appears at 24h in *every* year 2019–2023 (ρ −0.05 to −0.11) and vanishes in 2024–25. Not adopted; added to the live-monitoring watch list for a confirmatory re-test when ≥6 months of live data exist. Magnitude weak and redundant with E003. |
| E006 | 2026-09-20 | done | exploratory (pre-registered criterion) | Macro group (13 features: S&P, Nasdaq, dollar, gold, oil, 10y yield; 1-day and 5-day changes; staleness), daily bars visible from 22:00 UTC | **No pass** (0 of 65). Dollar and yield 5-day changes carry the expected *negative* sign at the weekly horizon in both periods, missing the rule by a hair (exploration upper bound +0.003); per-year signs unstable. Stocks: Nasdaq co-movement only in 2017–23. Nothing adopted; dollar/yield weekly pattern added to the live watch list. |
| E007 | 2026-09-20 | done | exploratory (pre-registered criterion) | On-chain group (hash rate, transactions, active addresses, fees: 7d/30d growth; last difficulty adjustment; staleness), daily values known from D+1 06:00 UTC; estimated tx volume marked UNSAFE | **No pass** (0 of 50). Activity growth leans the expected way in 2017–23 and the opposite way in 2024–25. Side-observation: a time-of-day effect on move *size* (US session) — candidate input for the uncertainty model, not on-chain information. |
| E009 | 2026-09-20 | done | exploratory (pre-registered criteria) | AI component tests: news scorer (schema, stability, relevance, sentiment sign, order) and explainer (signal named, forbidden content, adversarial faithfulness, structural isolation) | **8 of 9 pass.** News scorer reliable and stable (std 0.013), relevance 0.93 vs 0.04, signs correct; **order sensitivity fails** (shift 0.046 ≈ 0.007 on the overall score — negligible now, re-test if news weight rises). Explainer faithful 9/9, no forbidden content, provably no influence on the decision (2 unit tests). |
| E008 | 2026-09-20 | done | exploratory (pre-registered criterion) | Microstructure group from candle fields: taker-buy share (1h/6h/24h) and trade intensity vs prior 24h/168h | **Direction: the opposite of the hypothesis, consistently** — heavy aggressive buying precedes slightly *lower* returns over the next 1–6h (|ρ| 0.02–0.05, both periods): third appearance of the short-horizon reversal family. **Magnitude: trade intensity strongly predicts move size at 1–6h** (ρ 0.17–0.30) — second uncertainty input. |
| E010 | 2026-09-20 | done | infrastructure verification (pre-registered checks) | Walk-forward bench on real data, 24h binary labels, 28 quarterly folds 2018-08 → 2025-06: memorising model, last-label model, constant base-rate model (expanding and rolling), scoring 0.1.0 on the same rows | **5 of 5 pass.** Memoriser exactly 0.5 everywhere (no test hour ever seen); last-label 0.510 vs naive 0.523 (no head start from overlapping labels); 49h gap on 27 folds, 50h on one (Binance outage 2020-02-19 → label unavailable, row dropped); expanding/rolling test blocks identical; baseline 0.478 acted accuracy reproduces E001. Side note: the hindsight naive rate beats a training-prior model in bear years (2018, 2022) — the acceptance benchmark is strict. |
