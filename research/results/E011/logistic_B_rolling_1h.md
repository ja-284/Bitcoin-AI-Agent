# E011 — logistic · rolling · 1h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 19 folds · features: 13 (none)

- overall:     n=34425 acted=1.00 acc=0.529 naive=0.505 brier=0.2492 (base 0.2500) ece=0.009 edge=+0.01% [-0.00, +0.02]
- exploration: n=21298 acted=1.00 acc=0.529 naive=0.504 brier=0.2493 (base 0.2500) ece=0.005 edge=+0.00% [-0.01, +0.02]
- validation:  n=13127 acted=1.00 acc=0.531 naive=0.508 brier=0.2491 (base 0.2499) ece=0.015 edge=+0.02% [+0.00, +0.04]

Per year (acted accuracy / naive / edge %):
- 2021: 0.520 / 0.503 / +0.00
- 2022: 0.527 / 0.503 / +0.00
- 2023: 0.535 / 0.514 / -0.00
- 2024: 0.531 / 0.511 / +0.01
- 2025: 0.531 / 0.502 / +0.04

Baseline scoring 0.1.0 on the same rows: acted=0.70 acc=0.485 edge=+0.00%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- taker_buy_share_1h: -0.1318  (same sign in 100% of folds)
- momentum_score: -0.0780  (same sign in 100% of folds)
- vol_pct_720: +0.0334  (same sign in 100% of folds)
- taker_buy_share_6h: -0.0321  (same sign in 63% of folds)
- volume_score: +0.0282  (same sign in 63% of folds)
- premium_mean_24: +0.0182  (same sign in 68% of folds)
- chart_pattern_score: +0.0166  (same sign in 68% of folds)
- trend_score: -0.0159  (same sign in 53% of folds)
- tr_mean_14_rel: +0.0141  (same sign in 63% of folds)
- tnx_chg_5d: -0.0138  (same sign in 58% of folds)
- trades_rel_168h: +0.0087  (same sign in 63% of folds)
- funding_last: +0.0071  (same sign in 74% of folds)
- dxy_ret_5d: +0.0044  (same sign in 74% of folds)

Fold gaps (hours between last fitted row and test start): 624, 1034, 26, 26, 26, 26 ...