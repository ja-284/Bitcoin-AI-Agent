# E011 — logistic · expanding · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 8 (none)

- overall:     n=56215 acted=1.00 acc=0.524 naive=0.522 brier=0.2491 (base 0.2495) ece=0.009 edge=+0.07% [-0.10, +0.23]
- exploration: n=43111 acted=1.00 acc=0.523 naive=0.519 brier=0.2493 (base 0.2496) ece=0.011 edge=+0.07% [-0.13, +0.31]
- validation:  n=13104 acted=1.00 acc=0.527 naive=0.531 brier=0.2485 (base 0.2490) ece=0.014 edge=+0.06% [-0.18, +0.29]

Per year (acted accuracy / naive / edge %):
- 2018: 0.519 / 0.526 / +0.42
- 2019: 0.527 / 0.527 / +0.16
- 2020: 0.551 / 0.588 / -0.01
- 2021: 0.514 / 0.508 / +0.59
- 2022: 0.498 / 0.531 / +0.10
- 2023: 0.529 / 0.525 / -0.02
- 2024: 0.530 / 0.537 / +0.07
- 2025: 0.520 / 0.519 / +0.05

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.474 edge=+0.04%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- chart_pattern_score: -0.0974  (same sign in 100% of folds)
- momentum_score: -0.0861  (same sign in 100% of folds)
- trend_score: +0.0567  (same sign in 100% of folds)
- tr_mean_14_rel: +0.0567  (same sign in 100% of folds)
- taker_buy_share_1h: -0.0311  (same sign in 100% of folds)
- volume_score: +0.0184  (same sign in 100% of folds)
- trades_rel_168h: +0.0064  (same sign in 68% of folds)
- taker_buy_share_6h: +0.0055  (same sign in 50% of folds)

Fold gaps (hours between last fitted row and test start): 49, 49, 49, 49, 49, 49 ...