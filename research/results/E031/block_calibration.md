# E031 — does a time-of-day-conditional calibration remove the intraday miscalibration? (research-only)

Generated 2026-10-14T14:05 UTC · 54,472 development hours, identical rows for both · 27 calibrated folds · fallback to the single map: never · hypothesis-generating (validation wear) · never adopted into move_size_1h_v1

## exploration (41,345 hours)

| measure | incumbent (one Platt) | variant (four block Platts) |
|---|---|---|
| Brier skill vs base rate | +0.1457 | +0.1464 |
| skill as a multiple of the free EWMA rule's | 1.20× | 1.20× |
| Spearman ρ(p, move size) | +0.440 | +0.443 |
| ECE | 0.004 | 0.011 |
| buckets n ≥ 100 within 0.05 (E013) | yes | yes |
| calibration intercept / slope | -0.013 / 0.989 | -0.011 / 0.953 |
| accuracy at 0.5 (naive 0.501) | 0.658 | 0.661 |
| worst block offset | 0.047 | 0.013 |

Brier(incumbent) − Brier(variant): +0.00017 [-0.00026, +0.00061] (positive = variant better)

| block (UTC) | incumbent stated − observed | variant stated − observed |
|---|---|---|
| 00-06 | +0.047 [+0.037, +0.057] | +0.005 [-0.005, +0.016] |
| 06-12 | +0.003 [-0.006, +0.013] | -0.004 [-0.014, +0.007] |
| 12-18 | -0.022 [-0.033, -0.012] | -0.004 [-0.015, +0.006] |
| 18-24 | -0.017 [-0.027, -0.009] | +0.013 [+0.002, +0.022] |

Descriptive (never used to choose anything): per year, skill and worst block offset, incumbent → variant: 2018 +0.011→+0.006, 0.056→0.075; 2019 +0.110→+0.109, 0.057→0.017; 2020 +0.106→+0.107, 0.049→0.041; 2021 +0.043→+0.043, 0.038→0.017; 2022 +0.128→+0.128, 0.060→0.030; 2023 +0.121→+0.127, 0.085→0.027

Descriptive: stated − observed per frozen volatility tercile, incumbent → variant: low -0.003→-0.001; mid +0.006→+0.005; high +0.005→+0.004

## validation (13,127 hours)

| measure | incumbent (one Platt) | variant (four block Platts) |
|---|---|---|
| Brier skill vs base rate | +0.0983 | +0.0989 |
| skill as a multiple of the free EWMA rule's | 2.47× | 2.48× |
| Spearman ρ(p, move size) | +0.360 | +0.365 |
| ECE | 0.014 | 0.015 |
| buckets n ≥ 100 within 0.05 (E013) | yes | no |
| calibration intercept / slope | +0.016 / 0.976 | +0.006 / 0.928 |
| accuracy at 0.5 (naive 0.525) | 0.627 | 0.632 |
| worst block offset | 0.057 | 0.012 |

Brier(incumbent) − Brier(variant): +0.00014 [-0.00058, +0.00085] (positive = variant better)

| block (UTC) | incumbent stated − observed | variant stated − observed |
|---|---|---|
| 00-06 | +0.022 [+0.007, +0.038] | -0.008 [-0.023, +0.009] |
| 06-12 | +0.007 [-0.011, +0.022] | +0.007 [-0.010, +0.023] |
| 12-18 | -0.057 [-0.072, -0.040] | -0.000 [-0.015, +0.016] |
| 18-24 | +0.013 [-0.005, +0.030] | -0.012 [-0.030, +0.007] |

Descriptive (never used to choose anything): per year, skill and worst block offset, incumbent → variant: 2024 +0.091→+0.090, 0.057→0.017; 2025 +0.110→+0.114, 0.059→0.015

Descriptive: stated − observed per frozen volatility tercile, incumbent → variant: low -0.011→-0.007; mid -0.006→-0.007; high +0.021→+0.017

## Pre-registered hypotheses

- H_a_removes_the_offsets: **HOLDS**
- H_b_no_skill_loss: **HOLDS**
- H_c_calibration: **FAILS**
- H_d_ranking: **HOLDS**

*Research-only and hypothesis-generating: the validation period is worn, and E027 found these offsets on these rows. Whatever the verdict, move_size_1h_v1, the live system and the checkpoints are unchanged.*
