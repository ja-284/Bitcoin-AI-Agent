# E010 — base_rate · expanding · 24h

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 28 folds · features: 4 (none)

- overall:     n=59775 acted=1.00 acc=0.523 naive=0.523 brier=0.2497 (base 0.2495) ece=0.002 edge=+nan% 
- exploration: n=46671 acted=1.00 acc=0.520 naive=0.520 brier=0.2499 (base 0.2496) ece=0.004 edge=+nan% 
- validation:  n=13104 acted=1.00 acc=0.531 naive=0.531 brier=0.2492 (base 0.2490) ece=0.009 edge=+nan% 

Per year (acted accuracy / naive / edge %):
- 2018: 0.462 / 0.538 / +nan
- 2019: 0.521 / 0.521 / +nan
- 2020: 0.582 / 0.582 / +nan
- 2021: 0.522 / 0.522 / +nan
- 2022: 0.469 / 0.531 / +nan
- 2023: 0.527 / 0.527 / +nan
- 2024: 0.537 / 0.537 / +nan
- 2025: 0.519 / 0.519 / +nan

Baseline scoring 0.1.0 on the same rows: acted=0.71 acc=0.478 edge=+0.11%


Fold gaps (hours between last fitted row and test start): 49, 49, 49, 49, 49, 49 ...