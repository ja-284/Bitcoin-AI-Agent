# E011 — logistic · expanding · 6h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 8 (none)

- overall:     n=56258 acted=1.00 acc=0.516 naive=0.514 brier=0.2497 (base 0.2498) ece=0.011 edge=-0.08% [-0.17, -0.01]
- exploration: n=43136 acted=1.00 acc=0.513 naive=0.512 brier=0.2498 (base 0.2499) ece=0.015 edge=-0.15% [-0.27, -0.03]
- validation:  n=13122 acted=1.00 acc=0.525 naive=0.521 brier=0.2491 (base 0.2495) ece=0.004 edge=+0.02% [-0.06, +0.10]

Per year (acted accuracy / naive / edge %):
- 2018: 0.496 / 0.510 / -0.26
- 2019: 0.517 / 0.524 / -0.32
- 2020: 0.545 / 0.543 / +0.07
- 2021: 0.493 / 0.502 / -0.35
- 2022: 0.498 / 0.506 / +0.05
- 2023: 0.521 / 0.510 / -0.09
- 2024: 0.526 / 0.526 / -0.03
- 2025: 0.523 / 0.513 / +0.11

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.486 edge=+0.08%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- momentum_score: -0.0579  (same sign in 100% of folds)
- taker_buy_share_1h: -0.0501  (same sign in 82% of folds)
- tr_mean_14_rel: +0.0168  (same sign in 57% of folds)
- taker_buy_share_6h: -0.0124  (same sign in 100% of folds)
- trend_score: +0.0111  (same sign in 100% of folds)
- trades_rel_168h: +0.0097  (same sign in 86% of folds)
- volume_score: +0.0049  (same sign in 79% of folds)
- chart_pattern_score: +0.0028  (same sign in 100% of folds)

Fold gaps (hours between last fitted row and test start): 31, 31, 31, 31, 31, 31 ...