# E012 — logistic · expanding · 24h · target: large move (|return| > 1.50%)

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=56215 acted=1.00 acc=0.605 naive=0.519 brier=0.2326 (base 0.2496) ece=0.022 edge=+1.10% [+0.95, +1.27] rho(p,|ret|)=+0.311 [+0.281, +0.343]
- exploration: n=43111 acted=1.00 acc=0.616 naive=0.511 brier=0.2302 (base 0.2499) ece=0.024 edge=+1.22% [+1.03, +1.40] rho(p,|ret|)=+0.335 [+0.302, +0.369]
- validation:  n=13104 acted=1.00 acc=0.571 naive=0.547 brier=0.2403 (base 0.2478) ece=0.037 edge=+0.51% [+0.30, +0.72] rho(p,|ret|)=+0.210 [+0.163, +0.261]

Per year (acted accuracy / naive / edge %):
- 2018: 0.609 / 0.552 / +1.32
- 2019: 0.604 / 0.528 / +0.96
- 2020: 0.593 / 0.509 / +1.13
- 2021: 0.645 / 0.656 / +0.96
- 2022: 0.594 / 0.503 / +0.93
- 2023: 0.643 / 0.649 / +0.58
- 2024: 0.559 / 0.529 / +0.35
- 2025: 0.596 / 0.584 / +0.82

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.486 edge=-0.17%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tr_mean_14_rel: +0.6046  (same sign in 100% of folds)
- trades_rel_24h: +0.3611  (same sign in 100% of folds)
- trades_rel_168h: -0.2856  (same sign in 100% of folds)
- is_weekend: -0.1429  (same sign in 100% of folds)
- vol_ratio_24_168: -0.1136  (same sign in 100% of folds)
- rv_168: +0.1059  (same sign in 100% of folds)
- hour_sin: +0.0461  (same sign in 100% of folds)
- hour_cos: -0.0257  (same sign in 100% of folds)
- rv_24: +0.0093  (same sign in 50% of folds)

Fold gaps (hours between last fitted row and test start): 49, 49, 49, 49, 49, 49 ...