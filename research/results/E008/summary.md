# E008 — feature group: microstructure

pipeline 0.2.0 / scoring 0.1.0 · 68619 hours · fit-free · magnitude floor |ρ| ≥ 0.1

Availability (share of hours with a value): taker_buy_share_1h: 1.00, taker_buy_share_6h: 1.00, taker_buy_share_24h: 0.99, trades_rel_24h: 0.99, trades_rel_168h: 0.94

## Direction: Spearman(feature, forward return)

| feature | horizon | exploration | validation | verdict |
|---|---|---|---|---|
| taker_buy_share_1h | 1h | -0.036 [-0.045, -0.028] | -0.054 [-0.070, -0.040] | information (negative) |
| taker_buy_share_1h | 6h | -0.019 [-0.031, -0.008] | -0.042 [-0.063, -0.022] | information (negative) |
| taker_buy_share_1h | 24h | -0.002 [-0.019, +0.016] | -0.015 [-0.036, +0.005] | no evidence |
| taker_buy_share_1h | 72h | +0.007 [-0.020, +0.028] | +0.012 [-0.017, +0.038] | no evidence |
| taker_buy_share_1h | 168h | +0.002 [-0.035, +0.036] | -0.001 [-0.037, +0.035] | no evidence |
| taker_buy_share_6h | 1h | -0.020 [-0.028, -0.012] | -0.039 [-0.056, -0.025] | information (negative) |
| taker_buy_share_6h | 6h | -0.015 [-0.032, +0.002] | -0.026 [-0.060, +0.005] | no evidence |
| taker_buy_share_6h | 24h | -0.001 [-0.028, +0.024] | -0.010 [-0.052, +0.029] | no evidence |
| taker_buy_share_6h | 72h | +0.012 [-0.028, +0.047] | +0.030 [-0.031, +0.079] | no evidence |
| taker_buy_share_6h | 168h | +0.008 [-0.043, +0.056] | -0.003 [-0.079, +0.070] | no evidence |
| taker_buy_share_24h | 1h | -0.001 [-0.009, +0.008] | -0.020 [-0.036, -0.006] | no evidence |
| taker_buy_share_24h | 6h | -0.006 [-0.024, +0.013] | -0.018 [-0.054, +0.020] | no evidence |
| taker_buy_share_24h | 24h | -0.003 [-0.039, +0.029] | +0.011 [-0.053, +0.074] | no evidence |
| taker_buy_share_24h | 72h | +0.014 [-0.040, +0.062] | +0.046 [-0.063, +0.129] | no evidence |
| taker_buy_share_24h | 168h | +0.008 [-0.055, +0.080] | -0.011 [-0.145, +0.114] | no evidence |
| trades_rel_24h | 1h | +0.009 [+0.001, +0.016] | +0.002 [-0.013, +0.018] | no evidence |
| trades_rel_24h | 6h | +0.002 [-0.010, +0.016] | +0.000 [-0.032, +0.031] | no evidence |
| trades_rel_24h | 24h | -0.002 [-0.015, +0.014] | +0.012 [-0.023, +0.046] | no evidence |
| trades_rel_24h | 72h | +0.005 [-0.008, +0.019] | +0.028 [-0.001, +0.059] | no evidence |
| trades_rel_24h | 168h | +0.007 [-0.006, +0.020] | +0.022 [+0.000, +0.041] | no evidence |
| trades_rel_168h | 1h | +0.014 [+0.007, +0.022] | +0.014 [-0.001, +0.028] | no evidence |
| trades_rel_168h | 6h | +0.009 [-0.007, +0.022] | +0.027 [-0.005, +0.058] | no evidence |
| trades_rel_168h | 24h | +0.011 [-0.010, +0.033] | +0.038 [-0.007, +0.081] | no evidence |
| trades_rel_168h | 72h | +0.019 [-0.012, +0.047] | +0.051 [-0.002, +0.106] | no evidence |
| trades_rel_168h | 168h | +0.023 [-0.010, +0.058] | +0.059 [+0.009, +0.105] | no evidence |

## Magnitude: Spearman(feature, |forward return|)

| feature | horizon | exploration | validation | verdict |
|---|---|---|---|---|
| taker_buy_share_1h | 1h | -0.016 [-0.031, -0.001] | +0.027 [+0.008, +0.045] | no evidence |
| taker_buy_share_1h | 6h | -0.001 [-0.015, +0.015] | +0.007 [-0.013, +0.027] | no evidence |
| taker_buy_share_1h | 24h | -0.000 [-0.016, +0.019] | +0.018 [-0.004, +0.043] | no evidence |
| taker_buy_share_1h | 72h | +0.001 [-0.025, +0.026] | +0.009 [-0.017, +0.032] | no evidence |
| taker_buy_share_1h | 168h | +0.016 [-0.019, +0.052] | +0.035 [+0.003, +0.066] | no evidence |
| taker_buy_share_6h | 1h | -0.024 [-0.043, -0.002] | +0.035 [+0.008, +0.058] | no evidence |
| taker_buy_share_6h | 6h | -0.014 [-0.035, +0.010] | +0.034 [+0.000, +0.066] | no evidence |
| taker_buy_share_6h | 24h | -0.010 [-0.033, +0.016] | +0.030 [-0.014, +0.076] | no evidence |
| taker_buy_share_6h | 72h | -0.001 [-0.041, +0.036] | +0.039 [-0.017, +0.086] | no evidence |
| taker_buy_share_6h | 168h | +0.026 [-0.027, +0.080] | +0.069 [+0.002, +0.138] | no evidence |
| taker_buy_share_24h | 1h | -0.036 [-0.060, -0.009] | +0.030 [-0.004, +0.061] | no evidence |
| taker_buy_share_24h | 6h | -0.031 [-0.059, -0.004] | +0.005 [-0.038, +0.046] | no evidence |
| taker_buy_share_24h | 24h | -0.009 [-0.046, +0.025] | -0.001 [-0.058, +0.058] | no evidence |
| taker_buy_share_24h | 72h | -0.002 [-0.054, +0.050] | +0.026 [-0.072, +0.111] | no evidence |
| taker_buy_share_24h | 168h | +0.032 [-0.043, +0.103] | +0.100 [-0.020, +0.207] | no evidence |
| trades_rel_24h | 1h | +0.085 [+0.074, +0.098] | +0.211 [+0.189, +0.231] | consistent but below size floor |
| trades_rel_24h | 6h | +0.074 [+0.060, +0.086] | +0.151 [+0.124, +0.175] | consistent but below size floor |
| trades_rel_24h | 24h | +0.069 [+0.054, +0.084] | +0.116 [+0.087, +0.144] | consistent but below size floor |
| trades_rel_24h | 72h | +0.036 [+0.021, +0.052] | +0.034 [+0.002, +0.063] | consistent but below size floor |
| trades_rel_24h | 168h | +0.023 [+0.007, +0.037] | +0.025 [-0.003, +0.052] | no evidence |
| trades_rel_168h | 1h | +0.170 [+0.150, +0.187] | +0.295 [+0.272, +0.317] | information (positive) |
| trades_rel_168h | 6h | +0.125 [+0.105, +0.144] | +0.230 [+0.199, +0.261] | information (positive) |
| trades_rel_168h | 24h | +0.079 [+0.054, +0.101] | +0.135 [+0.103, +0.168] | consistent but below size floor |
| trades_rel_168h | 72h | +0.041 [+0.012, +0.069] | +0.046 [-0.010, +0.094] | no evidence |
| trades_rel_168h | 168h | +0.030 [-0.006, +0.062] | +0.081 [+0.013, +0.144] | no evidence |

## Shape at 24h (exploration): mean |return| by feature decile (1 = lowest feature value)

- taker_buy_share_1h: 2.70 2.53 2.60 2.58 2.48 2.48 2.54 2.61 2.59 2.77
- taker_buy_share_6h: 2.82 2.61 2.66 2.57 2.38 2.35 2.55 2.63 2.47 2.84
- taker_buy_share_24h: 2.93 2.60 2.60 2.58 2.36 2.26 2.59 2.68 2.45 2.79
- trades_rel_24h: 2.25 2.44 2.52 2.50 2.54 2.65 2.59 2.71 2.72 2.93
- trades_rel_168h: 2.33 2.29 2.34 2.45 2.52 2.55 2.62 2.75 2.74 3.16

## Direction by year at 24h (Spearman point estimates)

- taker_buy_share_1h: 2017: +0.032 · 2018: +0.023 · 2019: +0.039 · 2020: -0.017 · 2021: +0.006 · 2022: -0.015 · 2023: +0.001 · 2024: -0.013 · 2025: -0.021
- taker_buy_share_6h: 2017: +0.082 · 2018: +0.026 · 2019: +0.044 · 2020: -0.027 · 2021: +0.011 · 2022: -0.019 · 2023: +0.010 · 2024: -0.008 · 2025: -0.012
- taker_buy_share_24h: 2017: +0.123 · 2018: +0.004 · 2019: +0.039 · 2020: -0.023 · 2021: +0.037 · 2022: +0.004 · 2023: -0.005 · 2024: +0.023 · 2025: -0.018
- trades_rel_24h: 2017: +0.006 · 2018: -0.025 · 2019: -0.021 · 2020: +0.029 · 2021: -0.004 · 2022: +0.017 · 2023: -0.023 · 2024: -0.011 · 2025: +0.058
- trades_rel_168h: 2017: -0.011 · 2018: +0.000 · 2019: +0.024 · 2020: +0.006 · 2021: +0.017 · 2022: +0.003 · 2023: -0.002 · 2024: +0.017 · 2025: +0.076

## Feature correlation (Spearman, exploration)

| | taker_buy_share_1h | taker_buy_share_6h | taker_buy_share_24h | trades_rel_24h | trades_rel_168h |
|---|---|---|---|---|---|
| taker_buy_share_1h | +1.00 | +0.51 | +0.36 | -0.01 | -0.00 |
| taker_buy_share_6h | +0.51 | +1.00 | +0.66 | +0.01 | +0.00 |
| taker_buy_share_24h | +0.36 | +0.66 | +1.00 | +0.03 | +0.02 |
| trades_rel_24h | -0.01 | +0.01 | +0.03 | +1.00 | +0.78 |
| trades_rel_168h | -0.00 | +0.00 | +0.02 | +0.78 | +1.00 |