# E011 — logistic · rolling · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=45660 acted=1.00 acc=0.519 naive=0.523 brier=0.2510 (base 0.2495) ece=0.028 edge=-0.05% [-0.24, +0.13]
- exploration: n=32556 acted=1.00 acc=0.516 naive=0.520 brier=0.2517 (base 0.2496) ece=0.033 edge=-0.08% [-0.31, +0.16]
- validation:  n=13104 acted=1.00 acc=0.526 naive=0.531 brier=0.2492 (base 0.2490) ece=0.016 edge=+0.00% [-0.26, +0.25]

Per year (acted accuracy / naive / edge %):
- 2018: 0.578 / 0.531 / +1.87
- 2019: 0.539 / 0.521 / +0.45
- 2020: 0.546 / 0.598 / +0.10
- 2021: 0.503 / 0.501 / -0.30
- 2022: 0.493 / 0.531 / -0.27
- 2023: 0.506 / 0.535 / -0.05
- 2024: 0.524 / 0.537 / -0.08
- 2025: 0.532 / 0.519 / +0.25

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.472 edge=-0.01%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- momentum_score: -0.1329  (same sign in 96% of folds)
- vol_pct_720: +0.1246  (same sign in 89% of folds)
- taker_buy_share_1h: -0.0796  (same sign in 82% of folds)
- tr_mean_14_rel: +0.0471  (same sign in 57% of folds)
- taker_buy_share_6h: +0.0354  (same sign in 82% of folds)
- chart_pattern_score: -0.0350  (same sign in 100% of folds)
- trend_score: -0.0250  (same sign in 71% of folds)
- volume_score: +0.0192  (same sign in 68% of folds)
- trades_rel_168h: -0.0111  (same sign in 86% of folds)

Fold gaps (hours between last fitted row and test start): 49, 49, 645, 49, 49, 49 ...