# E010 — last_label · expanding · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 4 (none)

- overall:     n=59775 acted=1.00 acc=0.510 naive=0.523 brier=0.4899 (base 0.2495) ece=0.490 edge=+0.07% [-0.14, +0.29]
- exploration: n=46671 acted=1.00 acc=0.509 naive=0.520 brier=0.4907 (base 0.2496) ece=0.491 edge=+0.08% [-0.24, +0.36]
- validation:  n=13104 acted=1.00 acc=0.513 naive=0.531 brier=0.4873 (base 0.2490) ece=0.487 edge=+0.05% [-0.37, +0.45]

Per year (acted accuracy / naive / edge %):
- 2018: 0.462 / 0.538 / +nan
- 2019: 0.530 / 0.521 / +0.24
- 2020: 0.524 / 0.582 / +0.08
- 2021: 0.499 / 0.522 / +0.42
- 2022: 0.493 / 0.531 / -0.20
- 2023: 0.516 / 0.527 / -0.05
- 2024: 0.496 / 0.537 / -0.17
- 2025: 0.546 / 0.519 / +0.38

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.478 edge=+0.11%


Fold gaps (hours between last fitted row and test start): 49, 49, 49, 49, 49, 49 ...