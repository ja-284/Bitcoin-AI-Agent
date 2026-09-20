# E011 — logistic · rolling · 6h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=45702 acted=1.00 acc=0.521 naive=0.515 brier=0.2497 (base 0.2498) ece=0.012 edge=-0.01% [-0.07, +0.04]
- exploration: n=32580 acted=1.00 acc=0.520 naive=0.512 brier=0.2499 (base 0.2498) ece=0.011 edge=-0.03% [-0.11, +0.04]
- validation:  n=13122 acted=1.00 acc=0.522 naive=0.521 brier=0.2493 (base 0.2495) ece=0.017 edge=+0.03% [-0.04, +0.11]

Per year (acted accuracy / naive / edge %):
- 2018: 0.496 / 0.510 / -0.92
- 2019: 0.515 / 0.525 / -0.88
- 2020: 0.543 / 0.544 / +0.02
- 2021: 0.487 / 0.505 / -0.29
- 2022: 0.518 / 0.506 / +0.06
- 2023: 0.531 / 0.513 / +0.05
- 2024: 0.520 / 0.526 / +0.00
- 2025: 0.527 / 0.513 / +0.11

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.483 edge=+0.05%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- taker_buy_share_1h: -0.1085  (same sign in 82% of folds)
- momentum_score: -0.0894  (same sign in 100% of folds)
- vol_pct_720: +0.0463  (same sign in 100% of folds)
- volume_score: +0.0440  (same sign in 61% of folds)
- tr_mean_14_rel: +0.0404  (same sign in 82% of folds)
- trend_score: -0.0375  (same sign in 54% of folds)
- chart_pattern_score: -0.0060  (same sign in 50% of folds)
- taker_buy_share_6h: -0.0027  (same sign in 54% of folds)
- trades_rel_168h: -0.0002  (same sign in 57% of folds)

Fold gaps (hours between last fitted row and test start): 31, 31, 633, 31, 31, 31 ...