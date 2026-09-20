# E012 — logistic · expanding · 6h · target: large move (|return| > 0.75%)

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=56258 acted=1.00 acc=0.649 naive=0.579 brier=0.2170 (base 0.2437) ece=0.011 edge=+0.82% [+0.73, +0.92] rho(p,|ret|)=+0.378 [+0.356, +0.397]
- exploration: n=43136 acted=1.00 acc=0.652 naive=0.575 brier=0.2155 (base 0.2443) ece=0.005 edge=+0.85% [+0.75, +0.94] rho(p,|ret|)=+0.391 [+0.368, +0.413]
- validation:  n=13122 acted=1.00 acc=0.638 naive=0.592 brier=0.2220 (base 0.2416) ece=0.037 edge=+0.66% [+0.56, +0.77] rho(p,|ret|)=+0.332 [+0.296, +0.364]

Per year (acted accuracy / naive / edge %):
- 2018: 0.680 / 0.620 / +0.91
- 2019: 0.669 / 0.615 / +0.82
- 2020: 0.622 / 0.562 / +0.84
- 2021: 0.598 / 0.608 / +0.64
- 2022: 0.636 / 0.560 / +0.70
- 2023: 0.719 / 0.718 / +0.54
- 2024: 0.625 / 0.580 / +0.58
- 2025: 0.664 / 0.615 / +0.84

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.482 edge=-0.12%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tr_mean_14_rel: +0.4866  (same sign in 100% of folds)
- rv_168: +0.2242  (same sign in 100% of folds)
- trades_rel_24h: +0.1872  (same sign in 96% of folds)
- hour_cos: -0.1657  (same sign in 100% of folds)
- is_weekend: -0.1526  (same sign in 100% of folds)
- rv_24: +0.1284  (same sign in 100% of folds)
- vol_ratio_24_168: -0.0702  (same sign in 100% of folds)
- trades_rel_168h: -0.0490  (same sign in 68% of folds)
- hour_sin: +0.0260  (same sign in 100% of folds)

Fold gaps (hours between last fitted row and test start): 31, 31, 31, 31, 31, 31 ...