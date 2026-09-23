# E014 — DRY RUN on validation: 2024-01-01 → 2025-07-01

pipeline 0.2.0 / scoring 0.2.0 · snapshot btcusdt_1h_2026-09-19.csv · candles in window 13128

## A — scoring 0.1.0 (the live signal), direction

| label | acted accuracy | naive | edge (95% CI) | buy-and-hold mean | 3-class balanced acc. | pass |
|---|---|---|---|---|---|---|
| binary_1h | 0.481 (n=9163) | 0.508 | -0.00% [-0.03%, +0.02%] | +0.01% | 0.350 vs best baseline 0.339 | no |
| binary_6h | 0.476 (n=9163) | 0.521 | -0.01% [-0.13%, +0.11%] | +0.05% | 0.330 vs best baseline 0.333 | no |
| binary_24h | 0.481 (n=9150) | 0.531 | -0.10% [-0.49%, +0.32%] | +0.20% | 0.323 vs best baseline 0.333 | no |
| binary_72h | 0.485 (n=9104) | 0.543 | -0.40% [-1.32%, +0.56%] | +0.59% | 0.325 vs best baseline 0.333 | no |
| binary_168h | 0.474 (n=9059) | 0.561 | -1.08% [-2.67%, +0.55%] | +1.39% | 0.325 vs best baseline 0.333 | no |

Signal mix in window: {'BUY': 5283, 'HOLD': 3965, 'SELL': 3880}

## B — E011 direction model (1h, set A): the null result

acted accuracy 0.527 vs naive 0.508 · edge +0.01% [-0.01%, +0.03%] · Brier 0.2489 vs base 0.2499 · **pass: no**

## C — E012 move-size model (1h), raw

Brier 0.2264 vs base 0.2494 (+9.2%) · accuracy 0.624 vs naive 0.525 (+9.9 pts) · ρ(p, |move|) +0.362 [+0.337, +0.387] · ECE 0.0429 · worst bucket 0.061
**E012 criterion: PASS · E013 calibrated: no**

| stated | observed | 95% interval | n |
|---|---|---|---|
| 0.08 | 0.05 | [0.02, 0.15] | 56 |
| 0.16 | 0.17 | [0.14, 0.19] | 847 |
| 0.25 | 0.28 | [0.26, 0.31] | 1906 |
| 0.35 | 0.41 | [0.40, 0.43] | 2921 |
| 0.45 | 0.50 | [0.48, 0.52] | 2991 |
| 0.55 | 0.60 | [0.58, 0.62] | 2276 |
| 0.64 | 0.67 | [0.65, 0.70] | 1372 |
| 0.74 | 0.73 | [0.69, 0.76] | 644 |
| 0.83 | 0.81 | [0.73, 0.88] | 108 |
| 0.91 | 1.00 | [0.61, 1.00] | 6 |

Per year (accuracy − naive, points / ECE): 2024: +10.6 / 0.042 · 2025: +8.5 / 0.046
Folds (test start → gap hours): 2024-01-01 → 26, 2024-03-31 → 26, 2024-06-29 → 26, 2024-09-27 → 26, 2024-12-26 → 26, 2025-03-26 → 26, 2025-06-24 → 26

## D — E012 + Platt (the chosen deliverable)

Brier 0.2250 vs base 0.2494 (+9.8%) · accuracy 0.628 vs naive 0.525 (+10.3 pts) · ρ(p, |move|) +0.360 [+0.334, +0.385] · ECE 0.0142 · worst bucket 0.031
**E012 criterion: PASS · E013 calibrated: YES**

| stated | observed | 95% interval | n |
|---|---|---|---|
| 0.09 | 0.08 | [0.02, 0.26] | 24 |
| 0.16 | 0.15 | [0.12, 0.18] | 536 |
| 0.25 | 0.24 | [0.22, 0.26] | 1469 |
| 0.35 | 0.38 | [0.36, 0.40] | 2491 |
| 0.45 | 0.46 | [0.44, 0.48] | 3015 |
| 0.55 | 0.55 | [0.54, 0.57] | 2630 |
| 0.65 | 0.64 | [0.62, 0.66] | 1762 |
| 0.74 | 0.71 | [0.68, 0.74] | 920 |
| 0.83 | 0.80 | [0.75, 0.85] | 262 |
| 0.92 | 0.83 | [0.61, 0.94] | 18 |

Per year (accuracy − naive, points / ECE): 2024: +10.8 / 0.014 · 2025: +9.2 / 0.024
Folds (test start → gap hours): 2024-01-01 → 26, 2024-03-31 → 26, 2024-06-29 → 26, 2024-09-27 → 26, 2024-12-26 → 26, 2025-03-26 → 26, 2025-06-24 → 26

## E023 — secondary hypotheses (registered before unsealing; they cannot change E014's verdict)

*Dry run on the already-seen validation period: these numbers prove the code and should sit close to the development values in E023 -- they are NOT evidence.*

Identical rows for every comparison: 13127 (13127 with the free-rule reference).

| # | hypothesis | measured | pass |
|---|---|---|---|
| H1 | model ≥ 1.10× the free rule's skill, interval excluding zero | +0.0976 vs +0.0398 (2.45×), lead +0.01443 [+0.01249, +0.01631] | YES |
| H2 | fixed target more predictable than volatility-scaled | +0.0976 vs +0.0724 | YES |
| H3 | free rule's skill on the scaled target < 0.01 | +0.0003 | YES |
| H4 | `trades_rel_168h` best single input on the scaled target; volatility group < 40% of its skill | best `trades_rel_168h`; volatility cost 18% | YES |
| H5 | six inputs keep ≥ 95% of the nine-input skill | 99.2% | YES |

Held: 5 of 5 (H1, H2, H3, H4, H5).