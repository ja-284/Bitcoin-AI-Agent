# E011 — logistic · rolling · 6h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 19 folds · features: 13 (none)

- overall:     n=34413 acted=1.00 acc=0.513 naive=0.509 brier=0.2519 (base 0.2499) ece=0.034 edge=+0.00% [-0.06, +0.07]
- exploration: n=21291 acted=1.00 acc=0.507 naive=0.501 brier=0.2525 (base 0.2500) ece=0.039 edge=-0.04% [-0.14, +0.06]
- validation:  n=13122 acted=1.00 acc=0.524 naive=0.521 brier=0.2509 (base 0.2495) ece=0.025 edge=+0.03% [-0.05, +0.11]

Per year (acted accuracy / naive / edge %):
- 2021: 0.497 / 0.505 / -0.19
- 2022: 0.503 / 0.506 / -0.15
- 2023: 0.516 / 0.513 / +0.01
- 2024: 0.524 / 0.526 / -0.01
- 2025: 0.524 / 0.513 / +0.13

Baseline scoring 0.1.0 on the same rows: acted=0.70 acc=0.478 edge=+0.03%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- taker_buy_share_1h: -0.1111  (same sign in 100% of folds)
- momentum_score: -0.0850  (same sign in 100% of folds)
- tnx_chg_5d: -0.0666  (same sign in 74% of folds)
- vol_pct_720: +0.0614  (same sign in 89% of folds)
- trend_score: -0.0533  (same sign in 53% of folds)
- volume_score: +0.0470  (same sign in 68% of folds)
- funding_last: +0.0271  (same sign in 63% of folds)
- chart_pattern_score: -0.0118  (same sign in 74% of folds)
- tr_mean_14_rel: +0.0096  (same sign in 63% of folds)
- taker_buy_share_6h: -0.0095  (same sign in 58% of folds)
- dxy_ret_5d: -0.0081  (same sign in 68% of folds)
- premium_mean_24: -0.0048  (same sign in 84% of folds)
- trades_rel_168h: +0.0024  (same sign in 53% of folds)

Fold gaps (hours between last fitted row and test start): 628, 1039, 31, 31, 31, 31 ...