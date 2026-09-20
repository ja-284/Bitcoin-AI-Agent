# E011 — logistic · rolling · 1h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=45740 acted=1.00 acc=0.529 naive=0.508 brier=0.2489 (base 0.2499) ece=0.004 edge=+0.00% [-0.01, +0.02]
- exploration: n=32613 acted=1.00 acc=0.528 naive=0.508 brier=0.2489 (base 0.2499) ece=0.003 edge=-0.00% [-0.02, +0.01]
- validation:  n=13127 acted=1.00 acc=0.530 naive=0.508 brier=0.2489 (base 0.2499) ece=0.015 edge=+0.02% [+0.00, +0.04]

Per year (acted accuracy / naive / edge %):
- 2018: 0.485 / 0.512 / -0.02
- 2019: 0.520 / 0.519 / -0.03
- 2020: 0.525 / 0.515 / -0.01
- 2021: 0.522 / 0.503 / -0.01
- 2022: 0.532 / 0.503 / +0.00
- 2023: 0.539 / 0.514 / -0.00
- 2024: 0.530 / 0.511 / +0.00
- 2025: 0.531 / 0.502 / +0.04

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.487 edge=+0.01%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- taker_buy_share_1h: -0.1318  (same sign in 100% of folds)
- momentum_score: -0.0818  (same sign in 100% of folds)
- volume_score: +0.0282  (same sign in 57% of folds)
- taker_buy_share_6h: -0.0275  (same sign in 64% of folds)
- tr_mean_14_rel: +0.0272  (same sign in 71% of folds)
- vol_pct_720: +0.0267  (same sign in 82% of folds)
- chart_pattern_score: +0.0160  (same sign in 79% of folds)
- trades_rel_168h: +0.0076  (same sign in 54% of folds)
- trend_score: -0.0073  (same sign in 50% of folds)

Fold gaps (hours between last fitted row and test start): 26, 26, 623, 26, 26, 26 ...