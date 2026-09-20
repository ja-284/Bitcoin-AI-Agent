# E005 — feature group: derivatives

pipeline 0.2.0 / scoring 0.1.0 · 68619 hours · fit-free · magnitude floor |ρ| ≥ 0.1

Availability (share of hours with a value): funding_last: 0.74, funding_mean_3: 0.74, funding_sum_21: 0.74, premium_close: 0.70, premium_mean_24: 0.70, premium_mean_168: 0.70

## Direction: Spearman(feature, forward return)

| feature | horizon | exploration | validation | verdict |
|---|---|---|---|---|
| funding_last | 1h | -0.004 [-0.013, +0.005] | +0.003 [-0.012, +0.018] | no evidence |
| funding_last | 6h | -0.020 [-0.042, +0.002] | -0.004 [-0.044, +0.030] | no evidence |
| funding_last | 24h | -0.045 [-0.087, -0.003] | -0.006 [-0.082, +0.057] | no evidence |
| funding_last | 72h | -0.067 [-0.142, +0.002] | -0.004 [-0.114, +0.107] | no evidence |
| funding_last | 168h | -0.084 [-0.173, +0.030] | +0.002 [-0.168, +0.179] | no evidence |
| funding_mean_3 | 1h | -0.002 [-0.010, +0.008] | +0.005 [-0.011, +0.020] | no evidence |
| funding_mean_3 | 6h | -0.010 [-0.033, +0.014] | +0.004 [-0.036, +0.041] | no evidence |
| funding_mean_3 | 24h | -0.030 [-0.072, +0.015] | -0.002 [-0.075, +0.066] | no evidence |
| funding_mean_3 | 72h | -0.056 [-0.135, +0.019] | -0.002 [-0.117, +0.111] | no evidence |
| funding_mean_3 | 168h | -0.080 [-0.180, +0.038] | +0.011 [-0.171, +0.203] | no evidence |
| funding_sum_21 | 1h | +0.000 [-0.009, +0.010] | +0.009 [-0.006, +0.023] | no evidence |
| funding_sum_21 | 6h | -0.002 [-0.025, +0.021] | +0.016 [-0.024, +0.049] | no evidence |
| funding_sum_21 | 24h | -0.012 [-0.054, +0.031] | +0.023 [-0.052, +0.094] | no evidence |
| funding_sum_21 | 72h | -0.030 [-0.101, +0.044] | +0.026 [-0.098, +0.146] | no evidence |
| funding_sum_21 | 168h | -0.050 [-0.163, +0.067] | +0.029 [-0.157, +0.224] | no evidence |
| premium_close | 1h | -0.009 [-0.018, +0.001] | +0.009 [-0.007, +0.025] | no evidence |
| premium_close | 6h | -0.013 [-0.035, +0.010] | -0.003 [-0.040, +0.030] | no evidence |
| premium_close | 24h | -0.025 [-0.066, +0.018] | -0.002 [-0.071, +0.055] | no evidence |
| premium_close | 72h | -0.026 [-0.097, +0.040] | -0.005 [-0.109, +0.101] | no evidence |
| premium_close | 168h | -0.030 [-0.130, +0.074] | +0.016 [-0.146, +0.179] | no evidence |
| premium_mean_24 | 1h | -0.001 [-0.011, +0.008] | +0.006 [-0.010, +0.020] | no evidence |
| premium_mean_24 | 6h | -0.015 [-0.039, +0.008] | +0.001 [-0.039, +0.037] | no evidence |
| premium_mean_24 | 24h | -0.024 [-0.070, +0.020] | +0.001 [-0.073, +0.064] | no evidence |
| premium_mean_24 | 72h | -0.042 [-0.119, +0.028] | +0.000 [-0.115, +0.113] | no evidence |
| premium_mean_24 | 168h | -0.050 [-0.166, +0.060] | +0.012 [-0.163, +0.201] | no evidence |
| premium_mean_168 | 1h | +0.002 [-0.007, +0.012] | +0.007 [-0.008, +0.021] | no evidence |
| premium_mean_168 | 6h | -0.001 [-0.023, +0.019] | +0.014 [-0.026, +0.050] | no evidence |
| premium_mean_168 | 24h | -0.011 [-0.055, +0.032] | +0.018 [-0.059, +0.087] | no evidence |
| premium_mean_168 | 72h | -0.029 [-0.112, +0.049] | +0.017 [-0.111, +0.145] | no evidence |
| premium_mean_168 | 168h | -0.031 [-0.155, +0.087] | +0.010 [-0.174, +0.206] | no evidence |

## Magnitude: Spearman(feature, |forward return|)

| feature | horizon | exploration | validation | verdict |
|---|---|---|---|---|
| funding_last | 1h | +0.105 [+0.075, +0.133] | +0.074 [+0.038, +0.115] | consistent but below size floor |
| funding_last | 6h | +0.094 [+0.062, +0.125] | +0.057 [+0.017, +0.106] | consistent but below size floor |
| funding_last | 24h | +0.085 [+0.048, +0.125] | +0.062 [-0.003, +0.127] | no evidence |
| funding_last | 72h | +0.097 [+0.024, +0.163] | +0.045 [-0.055, +0.140] | no evidence |
| funding_last | 168h | +0.087 [-0.006, +0.179] | +0.100 [-0.046, +0.241] | no evidence |
| funding_mean_3 | 1h | +0.091 [+0.058, +0.120] | +0.070 [+0.033, +0.113] | consistent but below size floor |
| funding_mean_3 | 6h | +0.086 [+0.051, +0.117] | +0.049 [+0.004, +0.100] | consistent but below size floor |
| funding_mean_3 | 24h | +0.081 [+0.044, +0.121] | +0.065 [-0.005, +0.133] | no evidence |
| funding_mean_3 | 72h | +0.090 [+0.018, +0.159] | +0.043 [-0.063, +0.143] | no evidence |
| funding_mean_3 | 168h | +0.092 [-0.006, +0.192] | +0.117 [-0.035, +0.265] | no evidence |
| funding_sum_21 | 1h | +0.098 [+0.064, +0.132] | +0.066 [+0.027, +0.110] | consistent but below size floor |
| funding_sum_21 | 6h | +0.096 [+0.059, +0.128] | +0.055 [+0.012, +0.107] | consistent but below size floor |
| funding_sum_21 | 24h | +0.077 [+0.033, +0.117] | +0.059 [-0.009, +0.126] | no evidence |
| funding_sum_21 | 72h | +0.081 [+0.008, +0.156] | +0.059 [-0.037, +0.153] | no evidence |
| funding_sum_21 | 168h | +0.104 [-0.002, +0.199] | +0.139 [+0.004, +0.269] | no evidence |
| premium_close | 1h | +0.124 [+0.091, +0.151] | +0.057 [+0.025, +0.098] | consistent but below size floor |
| premium_close | 6h | +0.115 [+0.085, +0.148] | +0.038 [-0.001, +0.085] | no evidence |
| premium_close | 24h | +0.096 [+0.056, +0.134] | +0.042 [-0.017, +0.100] | no evidence |
| premium_close | 72h | +0.114 [+0.043, +0.182] | +0.031 [-0.064, +0.119] | no evidence |
| premium_close | 168h | +0.094 [-0.003, +0.179] | +0.089 [-0.044, +0.232] | no evidence |
| premium_mean_24 | 1h | +0.123 [+0.085, +0.153] | +0.070 [+0.032, +0.114] | consistent but below size floor |
| premium_mean_24 | 6h | +0.115 [+0.079, +0.148] | +0.046 [+0.004, +0.097] | consistent but below size floor |
| premium_mean_24 | 24h | +0.108 [+0.061, +0.148] | +0.061 [-0.008, +0.129] | no evidence |
| premium_mean_24 | 72h | +0.125 [+0.050, +0.194] | +0.057 [-0.048, +0.157] | no evidence |
| premium_mean_24 | 168h | +0.097 [-0.009, +0.189] | +0.109 [-0.045, +0.265] | no evidence |
| premium_mean_168 | 1h | +0.134 [+0.097, +0.167] | +0.060 [+0.021, +0.105] | consistent but below size floor |
| premium_mean_168 | 6h | +0.131 [+0.094, +0.165] | +0.049 [+0.003, +0.103] | consistent but below size floor |
| premium_mean_168 | 24h | +0.111 [+0.067, +0.154] | +0.045 [-0.025, +0.113] | no evidence |
| premium_mean_168 | 72h | +0.108 [+0.029, +0.184] | +0.035 [-0.069, +0.135] | no evidence |
| premium_mean_168 | 168h | +0.103 [-0.001, +0.204] | +0.110 [-0.027, +0.257] | no evidence |

## Shape at 24h (exploration): mean |return| by feature decile (1 = lowest feature value)

- funding_last: 2.77 1.87 1.87 2.01 2.06 2.50 2.57 1.79 2.52 3.12
- funding_mean_3: 2.78 1.89 1.89 2.22 1.98 2.63 1.80 2.03 2.78 3.07
- funding_sum_21: 2.73 1.98 2.07 2.09 2.06 2.06 1.90 2.23 2.76 3.25
- premium_close: 2.80 1.94 1.81 1.93 2.08 2.32 2.20 2.31 2.61 3.18
- premium_mean_24: 2.78 1.84 1.81 2.00 2.21 2.30 2.11 2.32 2.66 3.17
- premium_mean_168: 2.68 1.85 2.07 1.85 2.14 2.29 1.90 2.47 2.69 3.34

## Direction by year at 24h (Spearman point estimates)

- funding_last: 2019: -0.077 · 2020: -0.100 · 2021: -0.050 · 2022: -0.113 · 2023: -0.070 · 2024: -0.006 · 2025: -0.028
- funding_mean_3: 2019: -0.067 · 2020: -0.091 · 2021: -0.038 · 2022: -0.115 · 2023: -0.060 · 2024: +0.004 · 2025: -0.043
- funding_sum_21: 2019: -0.087 · 2020: -0.056 · 2021: -0.027 · 2022: -0.097 · 2023: -0.047 · 2024: +0.032 · 2025: -0.028
- premium_close: 2020: -0.116 · 2021: -0.029 · 2022: -0.106 · 2023: -0.043 · 2024: -0.007 · 2025: -0.006
- premium_mean_24: 2020: -0.106 · 2021: -0.028 · 2022: -0.146 · 2023: -0.037 · 2024: +0.003 · 2025: -0.036
- premium_mean_168: 2020: -0.059 · 2021: -0.027 · 2022: -0.136 · 2023: -0.047 · 2024: +0.029 · 2025: -0.053

## Feature correlation (Spearman, exploration)

| | funding_last | funding_mean_3 | funding_sum_21 | premium_close | premium_mean_24 | premium_mean_168 |
|---|---|---|---|---|---|---|
| funding_last | +1.00 | +0.91 | +0.77 | +0.77 | +0.90 | +0.79 |
| funding_mean_3 | +0.91 | +1.00 | +0.83 | +0.79 | +0.95 | +0.85 |
| funding_sum_21 | +0.77 | +0.83 | +1.00 | +0.74 | +0.85 | +0.96 |
| premium_close | +0.77 | +0.79 | +0.74 | +1.00 | +0.84 | +0.77 |
| premium_mean_24 | +0.90 | +0.95 | +0.85 | +0.84 | +1.00 | +0.88 |
| premium_mean_168 | +0.79 | +0.85 | +0.96 | +0.77 | +0.88 | +1.00 |