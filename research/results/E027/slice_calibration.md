# E027 — calibration by weekday/weekend and hour-of-day block (descriptive)

Generated 2026-09-26T14:05 UTC · walk-forward out-of-sample predictions, 54,472 development hours · slices exactly as the 2,000-hour checkpoint defines them

Hypothesis (pre-registered): in every slice |mean stated − observed| ≤ 0.02 and the 95% interval contains 0.

## exploration (41,345 hours)

| slice | rows | mean stated | observed | stated − observed [95%] | ECE | H holds |
|---|---|---|---|---|---|---|
| weekday | 29,484 | 0.525 | 0.531 | -0.007 [-0.012, -0.001] | 0.009 | NO |
| weekend | 11,861 | 0.446 | 0.420 | +0.026 [+0.016, +0.035] | 0.026 | NO |
| 00-06 | 10,309 | 0.491 | 0.444 | +0.047 [+0.037, +0.057] | 0.047 | NO |
| 06-12 | 10,335 | 0.487 | 0.484 | +0.003 [-0.006, +0.013] | 0.014 | yes |
| 12-18 | 10,346 | 0.521 | 0.543 | -0.022 [-0.033, -0.012] | 0.025 | NO |
| 18-24 | 10,355 | 0.509 | 0.526 | -0.017 [-0.027, -0.009] | 0.023 | NO |

## validation (13,127 hours)

| slice | rows | mean stated | observed | stated − observed [95%] | ECE | H holds |
|---|---|---|---|---|---|---|
| weekday | 9,383 | 0.523 | 0.533 | -0.010 [-0.018, -0.001] | 0.020 | NO |
| weekend | 3,744 | 0.342 | 0.331 | +0.012 [-0.004, +0.029] | 0.018 | yes |
| 00-06 | 3,282 | 0.445 | 0.423 | +0.022 [+0.007, +0.038] | 0.022 | NO |
| 06-12 | 3,282 | 0.429 | 0.422 | +0.007 [-0.011, +0.022] | 0.025 | yes |
| 12-18 | 3,282 | 0.524 | 0.581 | -0.057 [-0.072, -0.040] | 0.067 | NO |
| 18-24 | 3,281 | 0.487 | 0.475 | +0.013 [-0.005, +0.030] | 0.027 | yes |

*Descriptive. Nothing about the frozen model, its calibration, the live signal or any checkpoint rule changes because of these numbers (pre-registered).*
