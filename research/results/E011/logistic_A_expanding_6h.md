# E011 — logistic · expanding · 6h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=45702 acted=1.00 acc=0.519 naive=0.515 brier=0.2496 (base 0.2498) ece=0.012 edge=-0.07% [-0.16, +0.02]
- exploration: n=32580 acted=1.00 acc=0.515 naive=0.512 brier=0.2500 (base 0.2498) ece=0.017 edge=-0.17% [-0.33, +0.01]
- validation:  n=13122 acted=1.00 acc=0.529 naive=0.521 brier=0.2488 (base 0.2495) ece=0.004 edge=+0.03% [-0.05, +0.12]

Per year (acted accuracy / naive / edge %):
- 2018: 0.496 / 0.510 / -0.92
- 2019: 0.515 / 0.525 / -0.88
- 2020: 0.548 / 0.544 / +0.89
- 2021: 0.492 / 0.505 / -0.31
- 2022: 0.502 / 0.506 / -0.03
- 2023: 0.523 / 0.513 / -0.01
- 2024: 0.528 / 0.526 / -0.02
- 2025: 0.531 / 0.513 / +0.12

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.483 edge=+0.05%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- momentum_score: -0.0682  (same sign in 100% of folds)
- taker_buy_share_1h: -0.0601  (same sign in 82% of folds)
- vol_pct_720: +0.0498  (same sign in 100% of folds)
- taker_buy_share_6h: +0.0165  (same sign in 71% of folds)
- trend_score: +0.0092  (same sign in 100% of folds)
- volume_score: +0.0045  (same sign in 68% of folds)
- chart_pattern_score: -0.0043  (same sign in 75% of folds)
- tr_mean_14_rel: -0.0035  (same sign in 100% of folds)
- trades_rel_168h: -0.0014  (same sign in 61% of folds)

Fold gaps (hours between last fitted row and test start): 31, 31, 633, 31, 31, 31 ...