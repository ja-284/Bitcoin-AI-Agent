# E012 — logistic · rolling · 6h · target: large move (|return| > 0.75%)

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=56258 acted=1.00 acc=0.650 naive=0.579 brier=0.2167 (base 0.2437) ece=0.007 edge=+0.79% [+0.71, +0.87] rho(p,|ret|)=+0.380 [+0.359, +0.400]
- exploration: n=43136 acted=1.00 acc=0.653 naive=0.575 brier=0.2156 (base 0.2443) ece=0.008 edge=+0.82% [+0.73, +0.91] rho(p,|ret|)=+0.392 [+0.369, +0.414]
- validation:  n=13122 acted=1.00 acc=0.639 naive=0.592 brier=0.2203 (base 0.2416) ece=0.038 edge=+0.62% [+0.52, +0.72] rho(p,|ret|)=+0.343 [+0.313, +0.376]

Per year (acted accuracy / naive / edge %):
- 2018: 0.680 / 0.620 / +0.91
- 2019: 0.670 / 0.615 / +0.82
- 2020: 0.620 / 0.562 / +0.90
- 2021: 0.604 / 0.608 / +0.59
- 2022: 0.640 / 0.560 / +0.66
- 2023: 0.718 / 0.718 / +0.51
- 2024: 0.628 / 0.580 / +0.55
- 2025: 0.661 / 0.615 / +0.75

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.482 edge=-0.12%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tr_mean_14_rel: +0.4895  (same sign in 100% of folds)
- trades_rel_24h: +0.3546  (same sign in 93% of folds)
- hour_cos: -0.3509  (same sign in 100% of folds)
- is_weekend: -0.2794  (same sign in 100% of folds)
- trades_rel_168h: -0.1865  (same sign in 68% of folds)
- rv_168: +0.1100  (same sign in 100% of folds)
- rv_24: +0.0687  (same sign in 100% of folds)
- hour_sin: +0.0286  (same sign in 71% of folds)
- vol_ratio_24_168: +0.0045  (same sign in 93% of folds)

Fold gaps (hours between last fitted row and test start): 31, 31, 31, 31, 31, 31 ...