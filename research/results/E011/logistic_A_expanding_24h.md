# E011 — logistic · expanding · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=45660 acted=1.00 acc=0.525 naive=0.523 brier=0.2492 (base 0.2495) ece=0.013 edge=+0.08% [-0.14, +0.24]
- exploration: n=32556 acted=1.00 acc=0.521 naive=0.520 brier=0.2497 (base 0.2496) ece=0.020 edge=+0.05% [-0.18, +0.28]
- validation:  n=13104 acted=1.00 acc=0.534 naive=0.531 brier=0.2479 (base 0.2490) ece=0.010 edge=+0.13% [-0.14, +0.38]

Per year (acted accuracy / naive / edge %):
- 2018: 0.578 / 0.531 / +1.87
- 2019: 0.539 / 0.521 / +0.45
- 2020: 0.541 / 0.598 / -0.02
- 2021: 0.511 / 0.501 / +1.09
- 2022: 0.492 / 0.531 / -0.11
- 2023: 0.528 / 0.535 / -0.00
- 2024: 0.537 / 0.537 / +0.13
- 2025: 0.527 / 0.519 / +0.12

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.472 edge=-0.01%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- chart_pattern_score: -0.0998  (same sign in 100% of folds)
- momentum_score: -0.0825  (same sign in 96% of folds)
- vol_pct_720: +0.0810  (same sign in 89% of folds)
- trend_score: +0.0417  (same sign in 100% of folds)
- taker_buy_share_1h: -0.0360  (same sign in 82% of folds)
- taker_buy_share_6h: +0.0315  (same sign in 93% of folds)
- tr_mean_14_rel: +0.0188  (same sign in 96% of folds)
- volume_score: +0.0126  (same sign in 96% of folds)
- trades_rel_168h: -0.0101  (same sign in 100% of folds)

Fold gaps (hours between last fitted row and test start): 49, 49, 645, 49, 49, 49 ...