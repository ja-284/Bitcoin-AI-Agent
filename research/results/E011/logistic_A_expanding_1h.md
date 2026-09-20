# E011 — logistic · expanding · 1h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=45740 acted=1.00 acc=0.524 naive=0.508 brier=0.2490 (base 0.2499) ece=0.007 edge=-0.00% [-0.02, +0.01]
- exploration: n=32613 acted=1.00 acc=0.523 naive=0.508 brier=0.2491 (base 0.2499) ece=0.007 edge=-0.01% [-0.03, +0.01]
- validation:  n=13127 acted=1.00 acc=0.527 naive=0.508 brier=0.2488 (base 0.2499) ece=0.005 edge=+0.01% [-0.01, +0.03]

Per year (acted accuracy / naive / edge %):
- 2018: 0.485 / 0.512 / -0.02
- 2019: 0.520 / 0.519 / -0.03
- 2020: 0.520 / 0.515 / -0.02
- 2021: 0.511 / 0.503 / -0.03
- 2022: 0.523 / 0.503 / +0.01
- 2023: 0.536 / 0.514 / -0.01
- 2024: 0.528 / 0.511 / +0.00
- 2025: 0.525 / 0.502 / +0.02

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.487 edge=+0.01%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- taker_buy_share_1h: -0.0958  (same sign in 100% of folds)
- momentum_score: -0.0945  (same sign in 100% of folds)
- taker_buy_share_6h: +0.0255  (same sign in 100% of folds)
- chart_pattern_score: +0.0202  (same sign in 100% of folds)
- vol_pct_720: +0.0166  (same sign in 61% of folds)
- trend_score: +0.0053  (same sign in 50% of folds)
- trades_rel_168h: +0.0038  (same sign in 71% of folds)
- tr_mean_14_rel: -0.0024  (same sign in 89% of folds)
- volume_score: +0.0014  (same sign in 50% of folds)

Fold gaps (hours between last fitted row and test start): 26, 26, 623, 26, 26, 26 ...