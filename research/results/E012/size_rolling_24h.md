# E012 — logistic · rolling · 24h · target: large move (|return| > 1.50%)

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 9 (none)

- overall:     n=56215 acted=1.00 acc=0.604 naive=0.519 brier=0.2332 (base 0.2496) ece=0.015 edge=+1.10% [+0.95, +1.27] rho(p,|ret|)=+0.305 [+0.277, +0.337]
- exploration: n=43111 acted=1.00 acc=0.613 naive=0.511 brier=0.2309 (base 0.2499) ece=0.024 edge=+1.20% [+1.01, +1.38] rho(p,|ret|)=+0.330 [+0.295, +0.365]
- validation:  n=13104 acted=1.00 acc=0.573 naive=0.547 brier=0.2405 (base 0.2478) ece=0.032 edge=+0.56% [+0.35, +0.79] rho(p,|ret|)=+0.203 [+0.157, +0.251]

Per year (acted accuracy / naive / edge %):
- 2018: 0.609 / 0.552 / +1.32
- 2019: 0.604 / 0.528 / +0.96
- 2020: 0.591 / 0.509 / +1.15
- 2021: 0.642 / 0.656 / +0.94
- 2022: 0.594 / 0.503 / +0.94
- 2023: 0.636 / 0.649 / +0.56
- 2024: 0.558 / 0.529 / +0.42
- 2025: 0.604 / 0.584 / +0.86

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.486 edge=-0.17%

Coefficients (standardised features, last fold's training range; sign agreement across folds):

- tr_mean_14_rel: +0.4713  (same sign in 100% of folds)
- trades_rel_24h: +0.4605  (same sign in 100% of folds)
- trades_rel_168h: -0.3597  (same sign in 100% of folds)
- is_weekend: -0.1147  (same sign in 100% of folds)
- hour_sin: +0.0410  (same sign in 100% of folds)
- hour_cos: -0.0312  (same sign in 68% of folds)
- vol_ratio_24_168: +0.0165  (same sign in 89% of folds)
- rv_168: -0.0129  (same sign in 89% of folds)
- rv_24: +0.0060  (same sign in 54% of folds)

Fold gaps (hours between last fitted row and test start): 49, 49, 49, 49, 49, 49 ...