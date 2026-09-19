# E001 — corrected baseline vs trivial baselines

pipeline 0.2.0 / scoring 0.1.0 · snapshot btcusdt_1h_2026-09-19.csv · 68619 hours · technical-only (news absent)

Signal mix — exploration: {'BUY': 0.389937106918239, 'HOLD': 0.2744769422068444, 'SELL': 0.33558595087491666} · validation: {'BUY': 0.4024223034734918, 'HOLD': 0.3020262035344302, 'SELL': 0.295551492992078}

## Horizon 1h

| system | period | n | edge BUY−SELL [95% CI] | bal. acc (3-class, ±0.5%) | acted acc (binary) | coverage |
|---|---|---|---|---|---|---|
| system | exploration | 55463 | +0.01% [-0.01%, +0.02%] | 0.354 | 0.494 | 0.73 |
| always_hold | exploration | 55463 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55463 | n/a [n/a, n/a] | 0.333 | 0.510 | 1.00 |
| random_mix | exploration | 55463 | +0.01% [-0.01%, +0.02%] | 0.332 | 0.497 | 0.73 |
| momentum_24h | exploration | 55463 | +0.01% [-0.01%, +0.02%] | 0.334 | 0.483 | 1.00 |
| ma_200h | exploration | 55463 | +0.01% [-0.00%, +0.02%] | 0.340 | 0.500 | 1.00 |
| buy-and-hold mean 1h return | exploration | 55463 | +0.01% | | | |
| system | validation | 13127 | -0.00% [-0.03%, +0.02%] | 0.350 | 0.481 | 0.70 |
| always_hold | validation | 13127 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13127 | n/a [n/a, n/a] | 0.333 | 0.508 | 1.00 |
| random_mix | validation | 13127 | -0.00% [-0.02%, +0.02%] | 0.331 | 0.498 | 0.73 |
| momentum_24h | validation | 13127 | -0.01% [-0.03%, +0.01%] | 0.336 | 0.476 | 1.00 |
| ma_200h | validation | 13127 | +0.00% [-0.02%, +0.02%] | 0.339 | 0.491 | 1.00 |
| buy-and-hold mean 1h return | validation | 13127 | +0.01% | | | |

Per year (system edge, point [CI]):
2017: -0.11% · 2018: -0.01% · 2019: +0.01% · 2020: +0.02% · 2021: +0.01% · 2022: -0.00% · 2023: +0.01% · 2024: +0.00% · 2025: -0.02%

Confidence as a probability (exploration, acted hours n=40238, hit rate 0.494, ECE 0.368):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.57) | 12 | 0.500 | [0.254, 0.746] (too few) |
| 0.60–0.70 (avg 0.68) | 438 | 0.459 | [0.413, 0.506] |
| 0.70–0.80 (avg 0.76) | 5730 | 0.493 | [0.480, 0.506] |
| 0.80–0.90 (avg 0.86) | 20601 | 0.491 | [0.485, 0.498] |
| 0.90–0.95 (avg 0.91) | 13457 | 0.500 | [0.492, 0.509] |
Brier — constant 0.5: 0.2500 · base rate 0.510: 0.2499 · naive 0.5+score/2: 0.2818

Confidence as a probability (validation, acted hours n=9163, hit rate 0.481, ECE 0.380):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.59) | 3 | 0.667 | [0.208, 0.939] (too few) |
| 0.60–0.70 (avg 0.68) | 177 | 0.452 | [0.380, 0.526] |
| 0.70–0.80 (avg 0.76) | 1405 | 0.463 | [0.437, 0.489] |
| 0.80–0.90 (avg 0.86) | 4433 | 0.491 | [0.476, 0.506] |
| 0.90–0.95 (avg 0.91) | 3145 | 0.476 | [0.459, 0.494] |
Brier — constant 0.5: 0.2500 · base rate 0.508: 0.2499 · naive 0.5+score/2: 0.2807

## Horizon 6h

| system | period | n | edge BUY−SELL [95% CI] | bal. acc (3-class, ±0.5%) | acted acc (binary) | coverage |
|---|---|---|---|---|---|---|
| system | exploration | 55402 | +0.09% [+0.00%, +0.17%] | 0.345 | 0.494 | 0.73 |
| always_hold | exploration | 55402 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55402 | n/a [n/a, n/a] | 0.333 | 0.515 | 1.00 |
| random_mix | exploration | 55402 | +0.01% [-0.03%, +0.05%] | 0.333 | 0.500 | 0.73 |
| momentum_24h | exploration | 55402 | +0.03% [-0.04%, +0.09%] | 0.321 | 0.475 | 1.00 |
| ma_200h | exploration | 55402 | +0.07% [-0.01%, +0.14%] | 0.334 | 0.498 | 1.00 |
| buy-and-hold mean 6h return | exploration | 55402 | +0.04% | | | |
| system | validation | 13122 | -0.01% [-0.13%, +0.11%] | 0.330 | 0.476 | 0.70 |
| always_hold | validation | 13122 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13122 | n/a [n/a, n/a] | 0.333 | 0.521 | 1.00 |
| random_mix | validation | 13122 | -0.00% [-0.06%, +0.05%] | 0.332 | 0.497 | 0.73 |
| momentum_24h | validation | 13122 | -0.04% [-0.13%, +0.05%] | 0.315 | 0.469 | 1.00 |
| ma_200h | validation | 13122 | +0.00% [-0.10%, +0.11%] | 0.328 | 0.489 | 1.00 |
| buy-and-hold mean 6h return | validation | 13122 | +0.05% | | | |

Per year (system edge, point [CI]):
2017: -0.15% · 2018: +0.05% · 2019: +0.11% · 2020: +0.16% · 2021: +0.04% · 2022: -0.01% · 2023: +0.10% · 2024: +0.02% · 2025: -0.09%

Confidence as a probability (exploration, acted hours n=40199, hit rate 0.494, ECE 0.368):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.57) | 12 | 0.500 | [0.254, 0.746] (too few) |
| 0.60–0.70 (avg 0.68) | 437 | 0.465 | [0.418, 0.511] |
| 0.70–0.80 (avg 0.76) | 5721 | 0.493 | [0.480, 0.506] |
| 0.80–0.90 (avg 0.86) | 20587 | 0.496 | [0.490, 0.503] |
| 0.90–0.95 (avg 0.91) | 13442 | 0.493 | [0.485, 0.502] |
Brier — constant 0.5: 0.2500 · base rate 0.515: 0.2498 · naive 0.5+score/2: 0.2809

Confidence as a probability (validation, acted hours n=9163, hit rate 0.476, ECE 0.385):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.59) | 3 | 0.667 | [0.208, 0.939] (too few) |
| 0.60–0.70 (avg 0.68) | 177 | 0.441 | [0.370, 0.514] |
| 0.70–0.80 (avg 0.76) | 1405 | 0.462 | [0.436, 0.488] |
| 0.80–0.90 (avg 0.86) | 4433 | 0.490 | [0.475, 0.504] |
| 0.90–0.95 (avg 0.91) | 3145 | 0.466 | [0.449, 0.484] |
Brier — constant 0.5: 0.2500 · base rate 0.521: 0.2495 · naive 0.5+score/2: 0.2811

## Horizon 24h

| system | period | n | edge BUY−SELL [95% CI] | bal. acc (3-class, ±0.5%) | acted acc (binary) | coverage |
|---|---|---|---|---|---|---|
| system | exploration | 55372 | +0.18% [-0.13%, +0.50%] | 0.330 | 0.481 | 0.73 |
| always_hold | exploration | 55372 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55372 | n/a [n/a, n/a] | 0.333 | 0.521 | 1.00 |
| random_mix | exploration | 55372 | +0.08% [+0.01%, +0.15%] | 0.335 | 0.505 | 0.73 |
| momentum_24h | exploration | 55372 | -0.03% [-0.25%, +0.19%] | 0.310 | 0.469 | 1.00 |
| ma_200h | exploration | 55372 | +0.19% [-0.07%, +0.45%] | 0.327 | 0.489 | 1.00 |
| buy-and-hold mean 24h return | exploration | 55372 | +0.17% | | | |
| system | validation | 13104 | -0.10% [-0.49%, +0.32%] | 0.323 | 0.481 | 0.70 |
| always_hold | validation | 13104 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13104 | n/a [n/a, n/a] | 0.333 | 0.531 | 1.00 |
| random_mix | validation | 13104 | -0.00% [-0.11%, +0.11%] | 0.331 | 0.493 | 0.73 |
| momentum_24h | validation | 13104 | -0.05% [-0.33%, +0.22%] | 0.320 | 0.478 | 1.00 |
| ma_200h | validation | 13104 | -0.04% [-0.41%, +0.32%] | 0.326 | 0.488 | 1.00 |
| buy-and-hold mean 24h return | validation | 13104 | +0.20% | | | |

Per year (system edge, point [CI]):
2017: -0.57% · 2018: +0.13% · 2019: +0.12% · 2020: +0.31% · 2021: -0.12% · 2022: -0.23% · 2023: +0.26% · 2024: -0.02% · 2025: -0.30%

Confidence as a probability (exploration, acted hours n=40175, hit rate 0.481, ECE 0.381):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.57) | 12 | 0.583 | [0.320, 0.807] (too few) |
| 0.60–0.70 (avg 0.68) | 438 | 0.418 | [0.373, 0.465] |
| 0.70–0.80 (avg 0.76) | 5721 | 0.491 | [0.478, 0.504] |
| 0.80–0.90 (avg 0.86) | 20576 | 0.485 | [0.478, 0.492] |
| 0.90–0.95 (avg 0.91) | 13428 | 0.473 | [0.465, 0.482] |
Brier — constant 0.5: 0.2500 · base rate 0.521: 0.2496 · naive 0.5+score/2: 0.2847

Confidence as a probability (validation, acted hours n=9150, hit rate 0.481, ECE 0.380):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.59) | 3 | 0.667 | [0.208, 0.939] (too few) |
| 0.60–0.70 (avg 0.68) | 176 | 0.386 | [0.318, 0.460] |
| 0.70–0.80 (avg 0.76) | 1403 | 0.482 | [0.456, 0.508] |
| 0.80–0.90 (avg 0.86) | 4424 | 0.484 | [0.469, 0.498] |
| 0.90–0.95 (avg 0.91) | 3144 | 0.483 | [0.465, 0.500] |
Brier — constant 0.5: 0.2500 · base rate 0.531: 0.2490 · naive 0.5+score/2: 0.2820

## Horizon 72h

| system | period | n | edge BUY−SELL [95% CI] | bal. acc (3-class, ±0.5%) | acted acc (binary) | coverage |
|---|---|---|---|---|---|---|
| system | exploration | 55363 | +0.75% [-0.07%, +1.54%] | 0.341 | 0.500 | 0.73 |
| always_hold | exploration | 55363 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55363 | n/a [n/a, n/a] | 0.333 | 0.530 | 1.00 |
| random_mix | exploration | 55363 | +0.12% [-0.02%, +0.25%] | 0.336 | 0.508 | 0.73 |
| momentum_24h | exploration | 55363 | +0.32% [-0.11%, +0.76%] | 0.329 | 0.496 | 1.00 |
| ma_200h | exploration | 55363 | +0.51% [-0.23%, +1.24%] | 0.329 | 0.496 | 1.00 |
| buy-and-hold mean 72h return | exploration | 55363 | +0.51% | | | |
| system | validation | 13056 | -0.40% [-1.32%, +0.56%] | 0.325 | 0.485 | 0.70 |
| always_hold | validation | 13056 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13056 | n/a [n/a, n/a] | 0.333 | 0.543 | 1.00 |
| random_mix | validation | 13056 | -0.02% [-0.26%, +0.22%] | 0.332 | 0.508 | 0.73 |
| momentum_24h | validation | 13056 | +0.09% [-0.42%, +0.66%] | 0.323 | 0.485 | 1.00 |
| ma_200h | validation | 13056 | -0.29% [-1.17%, +0.55%] | 0.322 | 0.490 | 1.00 |
| buy-and-hold mean 72h return | validation | 13056 | +0.59% | | | |

Per year (system edge, point [CI]):
2017: -0.51% · 2018: +0.68% · 2019: +0.65% · 2020: +0.62% · 2021: -0.10% · 2022: -0.36% · 2023: +0.75% · 2024: -0.17% · 2025: -0.96%

Confidence as a probability (exploration, acted hours n=40159, hit rate 0.500, ECE 0.363):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.57) | 12 | 0.750 | [0.468, 0.911] (too few) |
| 0.60–0.70 (avg 0.68) | 438 | 0.534 | [0.487, 0.580] |
| 0.70–0.80 (avg 0.76) | 5714 | 0.501 | [0.488, 0.514] |
| 0.80–0.90 (avg 0.86) | 20566 | 0.505 | [0.498, 0.512] |
| 0.90–0.95 (avg 0.91) | 13429 | 0.489 | [0.481, 0.498] |
Brier — constant 0.5: 0.2500 · base rate 0.530: 0.2491 · naive 0.5+score/2: 0.2784

Confidence as a probability (validation, acted hours n=9104, hit rate 0.485, ECE 0.376):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.59) | 3 | 0.667 | [0.208, 0.939] (too few) |
| 0.60–0.70 (avg 0.68) | 176 | 0.494 | [0.421, 0.568] |
| 0.70–0.80 (avg 0.76) | 1395 | 0.489 | [0.463, 0.515] |
| 0.80–0.90 (avg 0.86) | 4414 | 0.487 | [0.472, 0.502] |
| 0.90–0.95 (avg 0.91) | 3116 | 0.479 | [0.461, 0.496] |
Brier — constant 0.5: 0.2500 · base rate 0.543: 0.2482 · naive 0.5+score/2: 0.2796

## Horizon 168h

| system | period | n | edge BUY−SELL [95% CI] | bal. acc (3-class, ±0.5%) | acted acc (binary) | coverage |
|---|---|---|---|---|---|---|
| system | exploration | 55363 | +1.20% [-0.36%, +2.85%] | 0.337 | 0.495 | 0.73 |
| always_hold | exploration | 55363 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55363 | n/a [n/a, n/a] | 0.333 | 0.533 | 1.00 |
| random_mix | exploration | 55363 | +0.09% [-0.14%, +0.32%] | 0.332 | 0.504 | 0.73 |
| momentum_24h | exploration | 55363 | +0.63% [+0.00%, +1.27%] | 0.328 | 0.492 | 1.00 |
| ma_200h | exploration | 55363 | +0.82% [-0.56%, +2.30%] | 0.326 | 0.491 | 1.00 |
| buy-and-hold mean 168h return | exploration | 55363 | +1.23% | | | |
| system | validation | 12960 | -1.08% [-2.67%, +0.55%] | 0.325 | 0.474 | 0.70 |
| always_hold | validation | 12960 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 12960 | n/a [n/a, n/a] | 0.333 | 0.561 | 1.00 |
| random_mix | validation | 12960 | -0.08% [-0.47%, +0.27%] | 0.329 | 0.506 | 0.73 |
| momentum_24h | validation | 12960 | -0.41% [-1.17%, +0.42%] | 0.328 | 0.496 | 1.00 |
| ma_200h | validation | 12960 | -1.02% [-2.51%, +0.49%] | 0.310 | 0.472 | 1.00 |
| buy-and-hold mean 168h return | validation | 12960 | +1.39% | | | |

Per year (system edge, point [CI]):
2017: -0.20% · 2018: -0.16% · 2019: +1.53% · 2020: +0.80% · 2021: +0.37% · 2022: -1.45% · 2023: +0.26% · 2024: -0.97% · 2025: -1.47%

Confidence as a probability (exploration, acted hours n=40160, hit rate 0.495, ECE 0.367):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.57) | 12 | 0.750 | [0.468, 0.911] (too few) |
| 0.60–0.70 (avg 0.68) | 438 | 0.495 | [0.449, 0.542] |
| 0.70–0.80 (avg 0.76) | 5719 | 0.500 | [0.487, 0.513] |
| 0.80–0.90 (avg 0.86) | 20559 | 0.498 | [0.491, 0.505] |
| 0.90–0.95 (avg 0.91) | 13432 | 0.489 | [0.480, 0.497] |
Brier — constant 0.5: 0.2500 · base rate 0.533: 0.2489 · naive 0.5+score/2: 0.2800

Confidence as a probability (validation, acted hours n=9059, hit rate 0.474, ECE 0.387):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.59) | 3 | 0.667 | [0.208, 0.939] (too few) |
| 0.60–0.70 (avg 0.68) | 174 | 0.477 | [0.404, 0.551] |
| 0.70–0.80 (avg 0.76) | 1390 | 0.472 | [0.446, 0.498] |
| 0.80–0.90 (avg 0.86) | 4396 | 0.481 | [0.466, 0.496] |
| 0.90–0.95 (avg 0.91) | 3096 | 0.465 | [0.447, 0.482] |
Brier — constant 0.5: 0.2500 · base rate 0.561: 0.2463 · naive 0.5+score/2: 0.2808
