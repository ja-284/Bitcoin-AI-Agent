# E019 -- does the move-size model beat "how often lately?"

Generated 2026-09-22T18:52:53.977045+00:00  |  pipeline 0.2.0  |  snapshot btcusdt_1h_2026-09-19.csv
Threshold |1h return| > 0.25%.  All candidates scored on the incumbent's own out-of-sample rows (54472 hours, 27 folds); the criterion is judged on the 13127 validation hours where every candidate has a value.

## Validation, on identical rows

| candidate | fitted? | Brier | skill | ECE | rho | mean p | Brier minus incumbent [95%] |
|---|---|---|---|---|---|---|---|
| A_expanding_base_rate | no | 0.25174 | -0.0094 | 0.050 | +0.043 | 0.525 | +0.02687 [+0.02275, +0.03124] |
| B_trailing_24h | no | 0.24137 | +0.0321 | 0.056 | +0.248 | 0.475 | +0.01650 [+0.01458, +0.01852] |
| C_trailing_168h | no | 0.24414 | +0.0210 | 0.019 | +0.174 | 0.476 | +0.01927 [+0.01632, +0.02225] |
| D_trailing_720h | no | 0.24694 | +0.0098 | 0.015 | +0.115 | 0.478 | +0.02207 [+0.01864, +0.02568] |
| E_ewma_halflife_24h | no | 0.23946 | +0.0398 | 0.024 | +0.235 | 0.476 | +0.01459 [+0.01261, +0.01652] |
| F_one_feature_logistic | yes (1 input) | 0.23488 | +0.0582 | 0.018 | +0.268 | 0.468 | +0.01001 [+0.00871, +0.01136] |
| **G_incumbent** | yes (9 inputs) | **0.22487** | **+0.0983** | 0.014 | +0.360 | 0.471 | -- |

A positive difference means the candidate is WORSE than the incumbent.

## Verdict (pre-registered, two parts)

- best simple (non-fitted) rule: **E_ewma_halflife_24h**, skill +0.0398
- incumbent skill +0.0983 -> ratio **2.47x**
- practical bar (at least 1.10x the skill): **PASS**
- statistical bar (paired 95% interval excludes zero): **PASS** (+0.01459 [+0.01261, +0.01652])
- tripwire (a simple rule beats the incumbent): **not fired**

**the fitted model earns its complexity.**

## Secondary check -- NOT pre-registered: the same calibration for everyone

The pre-registration scored the simple rules uncalibrated, on the stated ground that a rule
needing a fitted calibrator is no longer simple. That invites the objection that the
comparison was rigged, so here every simple rule gets the incumbent's exact advantage: a
Platt re-map fitted on the same purged 90-day slice of each fold and applied to the same
test block. Only the mapping is fitted; the rules themselves are untouched.

| candidate | Brier (calibrated) | skill | ECE | Brier minus incumbent [95%] |
|---|---|---|---|---|
| A_expanding_base_rate | 0.25180 | -0.0097 | 0.030 | +0.02694 [+0.02296, +0.03110] |
| B_trailing_24h | 0.23888 | +0.0421 | 0.013 | +0.01401 [+0.01204, +0.01595] |
| C_trailing_168h | 0.24444 | +0.0198 | 0.004 | +0.01957 [+0.01661, +0.02251] |
| D_trailing_720h | 0.25287 | -0.0140 | 0.039 | +0.02800 [+0.02399, +0.03250] |
| E_ewma_halflife_24h | 0.23912 | +0.0412 | 0.005 | +0.01425 [+0.01221, +0.01625] |

Best simple rule once calibrated: **B_trailing_24h**, skill +0.0421 -- the incumbent is still **2.33x** more skilful, and the verdict is **unchanged**.

## Exploration period (reported, not used for the verdict)

| candidate | Brier | skill | ECE | rho |
|---|---|---|---|---|
| A_expanding_base_rate | 0.25364 | -0.0146 | 0.069 | +0.092 |
| B_trailing_24h | 0.22198 | +0.1121 | 0.037 | +0.399 |
| C_trailing_168h | 0.22413 | +0.1035 | 0.014 | +0.372 |
| D_trailing_720h | 0.23158 | +0.0737 | 0.018 | +0.316 |
| E_ewma_halflife_24h | 0.21960 | +0.1216 | 0.013 | +0.404 |
| F_one_feature_logistic | 0.21722 | +0.1311 | 0.005 | +0.417 |
| G_incumbent | 0.21357 | +0.1457 | 0.004 | +0.440 |
