# E010 — base_rate · rolling · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 4 (none)

- overall:     n=59775 acted=1.00 acc=0.518 naive=0.523 brier=0.2502 (base 0.2495) ece=0.004 edge=+0.00% [-0.27, +0.27]
- exploration: n=46671 acted=1.00 acc=0.516 naive=0.520 brier=0.2503 (base 0.2496) ece=0.008 edge=-0.02% [-0.32, +0.25]
- validation:  n=13104 acted=1.00 acc=0.528 naive=0.531 brier=0.2497 (base 0.2490) ece=0.015 edge=+0.15% [-0.70, +1.06]

Per year (acted accuracy / naive / edge %):
- 2018: 0.462 / 0.538 / +nan
- 2019: 0.521 / 0.521 / +nan
- 2020: 0.582 / 0.582 / +nan
- 2021: 0.522 / 0.522 / +nan
- 2022: 0.469 / 0.531 / +nan
- 2023: 0.503 / 0.527 / +0.33
- 2024: 0.533 / 0.537 / +0.21
- 2025: 0.519 / 0.519 / +nan

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.478 edge=+0.11%


Fold gaps (hours between last fitted row and test start): 49, 49, 49, 49, 49, 49 ...