# E020 -- is the logistic the right kind of model?

Generated 2026-09-22T19:03:02.646943+00:00  |  pipeline 0.2.0  |  snapshot btcusdt_1h_2026-09-19.csv
27 folds, 54472 out-of-sample rows, every candidate on identical rows. Settings fixed in advance; no search.

## Validation

| model | inputs | Brier | skill | ECE | worst bucket | rho |
|---|---|---|---|---|---|---|
| I_logistic_interactions | 30 | 0.22462 | +0.0993 | 0.015 | 0.054 | +0.362 |
| L_logistic_incumbent | 9 | 0.22487 | +0.0983 | 0.014 | 0.029 | +0.360 |
| T_gradient_boosted_trees | 9 | 0.22394 | +0.1020 | 0.007 | 0.027 | +0.367 |
| *(E019 reference: 24h EWMA, no fitting)* | 0 | 0.23946 | +0.0398 | 0.024 | 0.058 | +0.235 |

## Verdict (pre-registered: 10% more skill AND a paired interval excluding zero AND still calibrated)

| candidate | skill ratio | practical | statistical | calibrated | replaces incumbent? | reading |
|---|---|---|---|---|---|---|
| I_logistic_interactions | 1.01x | fail | fail | NO | **no** | not calibrated enough to be the deliverable, whatever its Brier |
| T_gradient_boosted_trees | 1.04x | fail | PASS | yes | **no** | statistically better, practically equivalent -- the complexity is not earned |

Paired Brier differences (positive = the candidate is better than the incumbent):

- I_logistic_interactions: +0.00024 [-0.00021, +0.00073]
- T_gradient_boosted_trees: +0.00093 [+0.00006, +0.00178]

**no candidate clears the pre-registered bars -- the logistic stands.**

## Exploration (reported, not used for the verdict)

| model | Brier | skill | ECE | rho |
|---|---|---|---|---|
| I_logistic_interactions | 0.21298 | +0.1481 | 0.005 | +0.443 |
| L_logistic_incumbent | 0.21357 | +0.1457 | 0.004 | +0.440 |
| T_gradient_boosted_trees | 0.21287 | +0.1485 | 0.003 | +0.442 |
