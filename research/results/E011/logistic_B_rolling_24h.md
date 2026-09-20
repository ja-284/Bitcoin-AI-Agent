# E011 — logistic · rolling · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 19 folds · features: 13 (none)

- overall:     n=34395 acted=1.00 acc=0.514 naive=0.512 brier=0.2571 (base 0.2499) ece=0.062 edge=-0.04% [-0.29, +0.21]
- exploration: n=21291 acted=1.00 acc=0.509 naive=0.500 brier=0.2599 (base 0.2500) ece=0.079 edge=-0.12% [-0.55, +0.29]
- validation:  n=13104 acted=1.00 acc=0.522 naive=0.531 brier=0.2525 (base 0.2490) ece=0.036 edge=-0.14% [-0.48, +0.19]

Per year (acted accuracy / naive / edge %):
- 2021: 0.498 / 0.501 / -0.45
- 2022: 0.529 / 0.531 / -0.47
- 2023: 0.494 / 0.535 / -0.18
- 2024: 0.519 / 0.537 / -0.23
- 2025: 0.529 / 0.519 / +0.21

Baseline scoring 0.1.0 on the same rows: acted=0.70 acc=0.468 edge=-0.01%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- vol_pct_720: +0.1316  (same sign in 89% of folds)
- momentum_score: -0.1311  (same sign in 100% of folds)
- taker_buy_share_1h: -0.0812  (same sign in 100% of folds)
- tnx_chg_5d: -0.0649  (same sign in 74% of folds)
- chart_pattern_score: -0.0517  (same sign in 100% of folds)
- funding_last: -0.0344  (same sign in 74% of folds)
- dxy_ret_5d: -0.0341  (same sign in 95% of folds)
- taker_buy_share_6h: +0.0336  (same sign in 100% of folds)
- tr_mean_14_rel: +0.0303  (same sign in 74% of folds)
- trend_score: -0.0257  (same sign in 53% of folds)
- volume_score: +0.0210  (same sign in 58% of folds)
- premium_mean_24: +0.0192  (same sign in 63% of folds)
- trades_rel_168h: -0.0082  (same sign in 84% of folds)

Fold gaps (hours between last fitted row and test start): 646, 1057, 49, 49, 49, 49 ...