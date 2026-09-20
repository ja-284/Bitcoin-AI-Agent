# E012 — logistic · rolling · 1h · target: large move (|return| > 0.25%)

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=56309 acted=1.00 acc=0.651 naive=0.511 brier=0.2158 (base 0.2499) ece=0.010 edge=+0.32% [+0.30, +0.34] rho(p,|ret|)=+0.428 [+0.410, +0.445]
- exploration: n=43182 acted=1.00 acc=0.657 naive=0.506 brier=0.2128 (base 0.2500) ece=0.010 edge=+0.33% [+0.30, +0.36] rho(p,|ret|)=+0.445 [+0.427, +0.465]
- validation:  n=13127 acted=1.00 acc=0.630 naive=0.525 brier=0.2255 (base 0.2494) ece=0.044 edge=+0.26% [+0.24, +0.29] rho(p,|ret|)=+0.371 [+0.345, +0.396]

Per year (acted accuracy / naive / edge %):
- 2018: 0.677 / 0.543 / +0.39
- 2019: 0.637 / 0.527 / +0.30
- 2020: 0.633 / 0.504 / +0.33
- 2021: 0.664 / 0.676 / +0.27
- 2022: 0.641 / 0.514 / +0.27
- 2023: 0.701 / 0.664 / +0.23
- 2024: 0.623 / 0.511 / +0.25
- 2025: 0.644 / 0.552 / +0.29

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.488 edge=-0.06%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tr_mean_14_rel: +0.4596  (same sign in 100% of folds)
- trades_rel_24h: +0.3738  (same sign in 79% of folds)
- rv_168: +0.1798  (same sign in 100% of folds)
- is_weekend: -0.1741  (same sign in 82% of folds)
- hour_cos: -0.1674  (same sign in 96% of folds)
- rv_24: +0.1245  (same sign in 100% of folds)
- hour_sin: -0.1046  (same sign in 96% of folds)
- trades_rel_168h: -0.0666  (same sign in 93% of folds)
- vol_ratio_24_168: +0.0221  (same sign in 89% of folds)

Fold gaps (hours between last fitted row and test start): 26, 26, 26, 26, 26, 26 ...