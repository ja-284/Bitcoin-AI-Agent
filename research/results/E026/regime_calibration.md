# E026 — calibration of the move-size model family within volatility regimes (descriptive)

Generated 2026-09-26T10:58 UTC · walk-forward out-of-sample predictions, 54,472 development hours · frozen rv_168 cut points 0.004759 / 0.006966

Hypothesis (pre-registered): in every regime |mean stated − observed| ≤ 0.02 and the 95% interval contains 0.

## exploration (41,345 hours)

| regime | share of hours | rows | mean stated | observed | stated − observed [95%] | ECE | H holds |
|---|---|---|---|---|---|---|---|
| low | 34% | 13,930 | 0.317 | 0.320 | -0.003 [-0.012, +0.006] | 0.010 | yes |
| mid | 35% | 14,316 | 0.520 | 0.514 | +0.006 [-0.003, +0.014] | 0.010 | yes |
| high | 32% | 13,099 | 0.679 | 0.674 | +0.005 [-0.003, +0.014] | 0.007 | yes |

## validation (13,127 hours)

| regime | share of hours | rows | mean stated | observed | stated − observed [95%] | ECE | H holds |
|---|---|---|---|---|---|---|---|
| low | 46% | 6,102 | 0.393 | 0.404 | -0.011 [-0.024, +0.002] | 0.022 | yes |
| mid | 38% | 4,967 | 0.506 | 0.513 | -0.006 [-0.019, +0.004] | 0.017 | yes |
| high | 16% | 2,058 | 0.617 | 0.596 | +0.021 [+0.002, +0.042] | 0.031 | NO |

*Descriptive. Nothing about the frozen model, its calibration, the live signal or any checkpoint rule changes because of these numbers (pre-registered).*
