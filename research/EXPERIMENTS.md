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
