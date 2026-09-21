# E013 — logistic · expanding · 1h · target: large move (|return| > 0.25%) · calibrator: isotonic

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 27 folds · features: 9 (none)

- overall:     n=54472 acted=0.99 acc=0.650 naive=0.506 brier=0.2191 (base 0.2500) ece=0.021 edge=+0.30% [+0.28, +0.32] rho(p,|ret|)=+0.419 [+0.402, +0.433]
- exploration: n=41345 acted=1.00 acc=0.657 naive=0.501 brier=0.2169 (base 0.2500) ece=0.024 edge=+0.32% [+0.30, +0.35] rho(p,|ret|)=+0.436 [+0.417, +0.454]
- validation:  n=13127 acted=0.99 acc=0.625 naive=0.525 brier=0.2258 (base 0.2494) ece=0.014 edge=+0.23% [+0.21, +0.26] rho(p,|ret|)=+0.356 [+0.331, +0.381]

Per year (acted accuracy / naive / edge %):
- 2018: 0.670 / 0.669 / +0.07
- 2019: 0.638 / 0.527 / +0.32
- 2020: 0.632 / 0.504 / +0.32
- 2021: 0.674 / 0.676 / +0.18
- 2022: 0.642 / 0.514 / +0.27
- 2023: 0.696 / 0.664 / +0.21
- 2024: 0.620 / 0.511 / +0.22
- 2025: 0.637 / 0.552 / +0.25

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.487 edge=-0.06%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tr_mean_14_rel: +0.5743  (same sign in 100% of folds)
- rv_168: +0.2104  (same sign in 100% of folds)
- trades_rel_24h: +0.1520  (same sign in 89% of folds)
- rv_24: +0.1420  (same sign in 100% of folds)
- hour_cos: -0.0891  (same sign in 96% of folds)
- hour_sin: -0.0787  (same sign in 96% of folds)
- is_weekend: -0.0753  (same sign in 78% of folds)
- trades_rel_168h: +0.0457  (same sign in 100% of folds)
- vol_ratio_24_168: -0.0335  (same sign in 100% of folds)

Fold gaps (hours between last fitted row and test start): 26, 26, 26, 26, 26, 29 ...