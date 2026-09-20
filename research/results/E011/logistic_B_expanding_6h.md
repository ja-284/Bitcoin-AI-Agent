# E011 — logistic · expanding · 6h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 19 folds · features: 13 (none)

- overall:     n=34413 acted=1.00 acc=0.517 naive=0.509 brier=0.2508 (base 0.2499) ece=0.024 edge=+0.01% [-0.05, +0.08]
- exploration: n=21291 acted=1.00 acc=0.513 naive=0.501 brier=0.2519 (base 0.2500) ece=0.031 edge=-0.02% [-0.11, +0.07]
- validation:  n=13122 acted=1.00 acc=0.525 naive=0.521 brier=0.2490 (base 0.2495) ece=0.013 edge=+0.04% [-0.05, +0.13]

Per year (acted accuracy / naive / edge %):
- 2021: 0.497 / 0.505 / -0.19
- 2022: 0.502 / 0.506 / -0.14
- 2023: 0.534 / 0.513 / +0.02
- 2024: 0.522 / 0.526 / -0.00
- 2025: 0.531 / 0.513 / +0.16

Baseline scoring 0.1.0 on the same rows: acted=0.70 acc=0.478 edge=+0.03%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- taker_buy_share_1h: -0.0862  (same sign in 100% of folds)
- momentum_score: -0.0732  (same sign in 100% of folds)
- tnx_chg_5d: -0.0636  (same sign in 95% of folds)
- vol_pct_720: +0.0625  (same sign in 89% of folds)
- trend_score: -0.0187  (same sign in 100% of folds)
- volume_score: +0.0186  (same sign in 89% of folds)
- premium_mean_24: -0.0185  (same sign in 100% of folds)
- dxy_ret_5d: -0.0171  (same sign in 95% of folds)
- funding_last: -0.0122  (same sign in 63% of folds)
- chart_pattern_score: -0.0119  (same sign in 79% of folds)
- taker_buy_share_6h: +0.0062  (same sign in 74% of folds)
- tr_mean_14_rel: -0.0061  (same sign in 89% of folds)
- trades_rel_168h: -0.0010  (same sign in 68% of folds)

Fold gaps (hours between last fitted row and test start): 628, 1039, 31, 31, 31, 31 ...