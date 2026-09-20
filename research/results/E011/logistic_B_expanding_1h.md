# E011 — logistic · expanding · 1h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 19 folds · features: 13 (none)

- overall:     n=34425 acted=1.00 acc=0.527 naive=0.505 brier=0.2490 (base 0.2500) ece=0.007 edge=+0.00% [-0.01, +0.02]
- exploration: n=21298 acted=1.00 acc=0.527 naive=0.504 brier=0.2491 (base 0.2500) ece=0.004 edge=+0.00% [-0.01, +0.02]
- validation:  n=13127 acted=1.00 acc=0.528 naive=0.508 brier=0.2488 (base 0.2499) ece=0.012 edge=+0.01% [-0.01, +0.03]

Per year (acted accuracy / naive / edge %):
- 2021: 0.520 / 0.503 / +0.00
- 2022: 0.524 / 0.503 / -0.00
- 2023: 0.535 / 0.514 / -0.01
- 2024: 0.529 / 0.511 / +0.00
- 2025: 0.524 / 0.502 / +0.02

Baseline scoring 0.1.0 on the same rows: acted=0.70 acc=0.485 edge=+0.00%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- taker_buy_share_1h: -0.1078  (same sign in 100% of folds)
- momentum_score: -0.0967  (same sign in 100% of folds)
- vol_pct_720: +0.0342  (same sign in 100% of folds)
- tnx_chg_5d: -0.0150  (same sign in 89% of folds)
- volume_score: +0.0133  (same sign in 100% of folds)
- funding_last: -0.0114  (same sign in 58% of folds)
- chart_pattern_score: +0.0091  (same sign in 100% of folds)
- taker_buy_share_6h: -0.0091  (same sign in 63% of folds)
- tr_mean_14_rel: -0.0077  (same sign in 89% of folds)
- trades_rel_168h: +0.0075  (same sign in 100% of folds)
- trend_score: +0.0053  (same sign in 53% of folds)
- dxy_ret_5d: +0.0004  (same sign in 79% of folds)
- premium_mean_24: +0.0002  (same sign in 95% of folds)

Fold gaps (hours between last fitted row and test start): 624, 1034, 26, 26, 26, 26 ...