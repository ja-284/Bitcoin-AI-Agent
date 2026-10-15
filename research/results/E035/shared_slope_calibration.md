# E035 — one shared slope with four block intercepts: does it fix the intraday miscalibration without E031's cost? (research-only)

Generated 2026-10-15T16:20 UTC · 54,472 development hours, identical rows for all · 27 calibrated folds · folds on the fallback: 0 · hypothesis-generating (validation wear) · never adopted into move_size_1h_v1

Fitted across folds (mean, sd, range): slope +0.955 (sd 0.173, +0.452 to +1.262); intercept_00-06 -0.100 (sd 0.230, -0.499 to +0.294); intercept_06-12 +0.072 (sd 0.223, -0.514 to +0.503); intercept_12-18 +0.203 (sd 0.209, -0.204 to +0.585); intercept_18-24 +0.140 (sd 0.210, -0.205 to +0.664)

## exploration (41,345 hours)

| measure | incumbent (one Platt) | variant (shared slope + block intercepts) | E031 four maps (descriptive) |
|---|---|---|---|
| Brier skill vs base rate | +0.1457 | +0.1479 | +0.1464 |
| skill as a multiple of the free EWMA rule's | 1.20× | 1.22× | 1.20× |
| Spearman ρ(p, move size) | +0.440 | +0.445 | +0.443 |
| ECE | 0.004 | 0.010 | 0.011 |
| buckets n ≥ 100 within 0.05 (E013) | yes | yes | yes |
| calibration intercept / slope | -0.013 / 0.989 | -0.013 / 0.969 | -0.011 / 0.953 |
| accuracy at 0.5 | 0.658 (naive 0.501) | 0.662 (naive 0.501) | 0.661 (naive 0.501) |
| worst block offset | 0.047 | 0.007 | 0.013 |

Brier(incumbent) − Brier(variant): +0.00055 [+0.00017, +0.00095] (positive = variant better)

| block (UTC) | incumbent stated − observed | variant | E031 four maps |
|---|---|---|---|
| 00-06 | +0.047 [+0.037, +0.057] | +0.006 [-0.004, +0.017] | +0.005 |
| 06-12 | +0.003 [-0.006, +0.013] | +0.002 [-0.008, +0.012] | -0.004 |
| 12-18 | -0.022 [-0.033, -0.012] | -0.003 [-0.014, +0.007] | -0.004 |
| 18-24 | -0.017 [-0.027, -0.009] | +0.007 [-0.003, +0.016] | +0.013 |

Descriptive (never used to choose anything): per year, skill and worst block offset, incumbent → variant: 2018 +0.011→+0.014, 0.056→0.026; 2019 +0.110→+0.111, 0.057→0.017; 2020 +0.106→+0.109, 0.049→0.020; 2021 +0.043→+0.043, 0.038→0.019; 2022 +0.128→+0.128, 0.060→0.026; 2023 +0.121→+0.128, 0.085→0.024

Descriptive: stated − observed per frozen volatility tercile, incumbent → variant: low -0.003→-0.001; mid +0.006→+0.006; high +0.005→+0.005

## validation (13,127 hours)

| measure | incumbent (one Platt) | variant (shared slope + block intercepts) | E031 four maps (descriptive) |
|---|---|---|---|
| Brier skill vs base rate | +0.0983 | +0.1013 | +0.0989 |
| skill as a multiple of the free EWMA rule's | 2.47× | 2.55× | 2.48× |
| Spearman ρ(p, move size) | +0.360 | +0.369 | +0.365 |
| ECE | 0.014 | 0.012 | 0.015 |
| buckets n ≥ 100 within 0.05 (E013) | yes | no | no |
| calibration intercept / slope | +0.016 / 0.976 | +0.014 / 0.962 | +0.006 / 0.928 |
| accuracy at 0.5 | 0.627 (naive 0.525) | 0.633 (naive 0.525) | 0.632 (naive 0.525) |
| worst block offset | 0.057 | 0.008 | 0.012 |

Brier(incumbent) − Brier(variant): +0.00074 [+0.00011, +0.00132] (positive = variant better)

| block (UTC) | incumbent stated − observed | variant | E031 four maps |
|---|---|---|---|
| 00-06 | +0.022 [+0.007, +0.038] | -0.007 [-0.023, +0.009] | -0.008 |
| 06-12 | +0.007 [-0.011, +0.022] | +0.003 [-0.015, +0.018] | +0.007 |
| 12-18 | -0.057 [-0.072, -0.040] | -0.003 [-0.018, +0.014] | -0.000 |
| 18-24 | +0.013 [-0.005, +0.030] | -0.008 [-0.027, +0.009] | -0.012 |

Descriptive (never used to choose anything): per year, skill and worst block offset, incumbent → variant: 2024 +0.091→+0.093, 0.057→0.014; 2025 +0.110→+0.115, 0.059→0.013

Descriptive: stated − observed per frozen volatility tercile, incumbent → variant: low -0.011→-0.007; mid -0.006→-0.008; high +0.021→+0.015

## Pre-registered hypotheses (E031's, unchanged)

- H_a_removes_the_offsets: **HOLDS**
- H_b_no_skill_loss: **HOLDS**
- H_c_calibration: **FAILS**
- H_d_ranking: **HOLDS**

*Research-only and hypothesis-generating: the validation period is worn, E027 found these offsets on these rows, and this design was chosen after E031 failed on them. Whatever the verdict, move_size_1h_v1, the live system, both shadow tracks and the checkpoints are unchanged.*
