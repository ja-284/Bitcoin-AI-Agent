# E011 — logistic · expanding · 1h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 8 (none)

- overall:     n=56309 acted=1.00 acc=0.525 naive=0.509 brier=0.2490 (base 0.2499) ece=0.006 edge=-0.00% [-0.01, +0.01]
- exploration: n=43182 acted=1.00 acc=0.525 naive=0.509 brier=0.2490 (base 0.2499) ece=0.006 edge=-0.00% [-0.02, +0.01]
- validation:  n=13127 acted=1.00 acc=0.526 naive=0.508 brier=0.2489 (base 0.2499) ece=0.004 edge=+0.01% [-0.01, +0.03]

Per year (acted accuracy / naive / edge %):
- 2018: 0.513 / 0.506 / -0.02
- 2019: 0.531 / 0.517 / +0.01
- 2020: 0.523 / 0.518 / -0.02
- 2021: 0.512 / 0.500 / -0.02
- 2022: 0.524 / 0.503 / +0.00
- 2023: 0.538 / 0.513 / -0.01
- 2024: 0.528 / 0.511 / +0.00
- 2025: 0.522 / 0.502 / +0.02

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.488 edge=+0.01%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- momentum_score: -0.0978  (same sign in 100% of folds)
- taker_buy_share_1h: -0.0968  (same sign in 100% of folds)
- taker_buy_share_6h: +0.0289  (same sign in 100% of folds)
- chart_pattern_score: +0.0274  (same sign in 100% of folds)
- trades_rel_168h: +0.0092  (same sign in 82% of folds)
- volume_score: +0.0044  (same sign in 75% of folds)
- tr_mean_14_rel: +0.0021  (same sign in 82% of folds)
- trend_score: -0.0010  (same sign in 86% of folds)

Fold gaps (hours between last fitted row and test start): 26, 26, 26, 26, 26, 26 ...