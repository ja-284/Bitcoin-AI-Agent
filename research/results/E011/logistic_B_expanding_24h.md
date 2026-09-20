# E011 — logistic · expanding · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 19 folds · features: 13 (none)

- overall:     n=34395 acted=1.00 acc=0.526 naive=0.512 brier=0.2546 (base 0.2499) ece=0.048 edge=+0.06% [-0.19, +0.32]
- exploration: n=21291 acted=1.00 acc=0.518 naive=0.500 brier=0.2583 (base 0.2500) ece=0.068 edge=-0.03% [-0.39, +0.33]
- validation:  n=13104 acted=1.00 acc=0.538 naive=0.531 brier=0.2485 (base 0.2490) ece=0.016 edge=+0.08% [-0.32, +0.41]

Per year (acted accuracy / naive / edge %):
- 2021: 0.498 / 0.501 / -0.45
- 2022: 0.529 / 0.531 / -0.61
- 2023: 0.518 / 0.535 / -0.24
- 2024: 0.539 / 0.537 / +0.04
- 2025: 0.535 / 0.519 / +0.36

Baseline scoring 0.1.0 on the same rows: acted=0.70 acc=0.468 edge=-0.01%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tnx_chg_5d: -0.1103  (same sign in 100% of folds)
- vol_pct_720: +0.0964  (same sign in 89% of folds)
- momentum_score: -0.0906  (same sign in 100% of folds)
- chart_pattern_score: -0.0850  (same sign in 100% of folds)
- dxy_ret_5d: -0.0806  (same sign in 100% of folds)
- funding_last: -0.0533  (same sign in 68% of folds)
- taker_buy_share_1h: -0.0529  (same sign in 100% of folds)
- taker_buy_share_6h: +0.0386  (same sign in 100% of folds)
- premium_mean_24: -0.0175  (same sign in 100% of folds)
- trend_score: -0.0108  (same sign in 79% of folds)
- volume_score: +0.0101  (same sign in 63% of folds)
- trades_rel_168h: -0.0042  (same sign in 84% of folds)
- tr_mean_14_rel: +0.0034  (same sign in 53% of folds)

Fold gaps (hours between last fitted row and test start): 646, 1057, 49, 49, 49, 49 ...