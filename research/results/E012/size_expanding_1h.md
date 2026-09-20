# E012 — logistic · expanding · 1h · target: large move (|return| > 0.25%)

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=56309 acted=1.00 acc=0.649 naive=0.511 brier=0.2159 (base 0.2499) ece=0.016 edge=+0.32% [+0.30, +0.34] rho(p,|ret|)=+0.427 [+0.409, +0.444]
- exploration: n=43182 acted=1.00 acc=0.656 naive=0.506 brier=0.2128 (base 0.2500) ece=0.013 edge=+0.33% [+0.30, +0.36] rho(p,|ret|)=+0.446 [+0.427, +0.465]
- validation:  n=13127 acted=1.00 acc=0.625 naive=0.525 brier=0.2261 (base 0.2494) ece=0.040 edge=+0.26% [+0.23, +0.29] rho(p,|ret|)=+0.363 [+0.338, +0.388]

Per year (acted accuracy / naive / edge %):
- 2018: 0.677 / 0.543 / +0.39
- 2019: 0.637 / 0.527 / +0.30
- 2020: 0.637 / 0.504 / +0.33
- 2021: 0.659 / 0.676 / +0.26
- 2022: 0.640 / 0.514 / +0.28
- 2023: 0.698 / 0.664 / +0.22
- 2024: 0.618 / 0.511 / +0.24
- 2025: 0.638 / 0.552 / +0.31

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.488 edge=-0.06%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tr_mean_14_rel: +0.5679  (same sign in 100% of folds)
- rv_168: +0.2088  (same sign in 100% of folds)
- trades_rel_24h: +0.1620  (same sign in 89% of folds)
- rv_24: +0.1410  (same sign in 100% of folds)
- hour_cos: -0.0924  (same sign in 96% of folds)
- hour_sin: -0.0791  (same sign in 96% of folds)
- is_weekend: -0.0763  (same sign in 79% of folds)
- trades_rel_168h: +0.0445  (same sign in 100% of folds)
- vol_ratio_24_168: -0.0318  (same sign in 100% of folds)

Fold gaps (hours between last fitted row and test start): 26, 26, 26, 26, 26, 26 ...