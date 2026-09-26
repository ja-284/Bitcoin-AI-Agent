# E028 — does a second calendar harmonic remove the intraday miscalibration? (research-only)

Generated 2026-09-26T14:11 UTC · 54,472 development hours, identical rows for both models · never adopted into move_size_1h_v1

## exploration (41,345 hours)

Skill: incumbent +0.1457, variant +0.1473 · ECE: 0.004 → 0.004 · Brier(incumbent) − Brier(variant) +0.00040 [+0.00020, +0.00061] (positive = variant better)

| block (UTC) | incumbent stated − observed | variant stated − observed |
|---|---|---|
| 00-06 | +0.047 [+0.037, +0.057] | +0.037 [+0.027, +0.047] |
| 06-12 | +0.003 [-0.006, +0.013] | +0.014 [+0.004, +0.024] |
| 12-18 | -0.022 [-0.033, -0.012] | -0.032 [-0.043, -0.022] |
| 18-24 | -0.017 [-0.027, -0.009] | -0.007 [-0.017, +0.002] |

Worst block offset: 0.047 → 0.037

## validation (13,127 hours)

Skill: incumbent +0.0983, variant +0.0986 · ECE: 0.014 → 0.017 · Brier(incumbent) − Brier(variant) +0.00007 [-0.00028, +0.00042] (positive = variant better)

| block (UTC) | incumbent stated − observed | variant stated − observed |
|---|---|---|
| 00-06 | +0.022 [+0.007, +0.038] | +0.015 [+0.000, +0.031] |
| 06-12 | +0.007 [-0.011, +0.022] | +0.013 [-0.005, +0.028] |
| 12-18 | -0.057 [-0.072, -0.040] | -0.064 [-0.079, -0.046] |
| 18-24 | +0.013 [-0.005, +0.030] | +0.019 [+0.001, +0.036] |

Worst block offset: 0.057 → 0.064

## Pre-registered hypotheses

- H_a_mechanism: **FAILS**
- H_b_no_loss: **HOLDS**
- H_c_calibration: **HOLDS**

*Research-only and hypothesis-generating (the validation period is worn). Whatever the verdict, move_size_1h_v1 and the live system are unchanged.*
