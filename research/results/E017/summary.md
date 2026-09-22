# E017 — corrected baseline vs trivial baselines

pipeline 0.2.0 / scoring 0.2.0 · snapshot btcusdt_1h_2026-09-19.csv · 68619 hours · technical-only (news absent)

Signal mix — exploration: {'BUY': 0.382206123515525, 'HOLD': 0.2815051089365843, 'SELL': 0.33628876754789067} · validation: {'BUY': 0.4024223034734918, 'HOLD': 0.3020262035344302, 'SELL': 0.295551492992078}

## Horizon 1h

| system | period | n | edge BUY−SELL [95% CI] | bal. acc (3-class, ±0.5%) | acted acc (binary) | coverage |
|---|---|---|---|---|---|---|
| system | exploration | 55463 | +0.00% [-0.01%, +0.02%] | 0.354 | 0.493 | 0.72 |
| always_hold | exploration | 55463 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55463 | n/a [n/a, n/a] | 0.333 | 0.510 | 1.00 |
| random_mix | exploration | 55463 | +0.01% [-0.01%, +0.02%] | 0.331 | 0.497 | 0.72 |
| momentum_24h | exploration | 55463 | +0.01% [-0.01%, +0.02%] | 0.334 | 0.483 | 1.00 |
| ma_200h | exploration | 55463 | +0.00% [-0.01%, +0.02%] | 0.331 | 0.499 | 0.91 |
| buy-and-hold mean 1h return | exploration | 55463 | +0.01% | | | |
| system | validation | 13127 | -0.00% [-0.03%, +0.02%] | 0.350 | 0.481 | 0.70 |
| always_hold | validation | 13127 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13127 | n/a [n/a, n/a] | 0.333 | 0.508 | 1.00 |
| random_mix | validation | 13127 | -0.00% [-0.02%, +0.02%] | 0.331 | 0.498 | 0.73 |
| momentum_24h | validation | 13127 | -0.01% [-0.03%, +0.01%] | 0.336 | 0.476 | 1.00 |
| ma_200h | validation | 13127 | +0.00% [-0.02%, +0.02%] | 0.339 | 0.491 | 1.00 |
| buy-and-hold mean 1h return | validation | 13127 | +0.01% | | | |

Per year (system edge, point [CI]):
2017: -0.12% · 2018: -0.02% · 2019: +0.01% · 2020: +0.03% · 2021: -0.00% · 2022: -0.00% · 2023: +0.01% · 2024: +0.00% · 2025: -0.02%

Confidence as a probability (exploration, acted hours n=39849, hit rate 0.493, ECE 0.357):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.00–0.50 (avg 0.39) | 110 | 0.518 | [0.426, 0.609] |
| 0.50–0.60 (avg 0.57) | 170 | 0.447 | [0.374, 0.522] |
| 0.60–0.70 (avg 0.66) | 1345 | 0.471 | [0.444, 0.497] |
| 0.70–0.80 (avg 0.76) | 7500 | 0.492 | [0.481, 0.503] |
| 0.80–0.90 (avg 0.86) | 18561 | 0.491 | [0.484, 0.499] |
| 0.90–0.95 (avg 0.91) | 12163 | 0.500 | [0.491, 0.509] |
Brier — constant 0.5: 0.2500 · base rate 0.510: 0.2499 · naive 0.5+score/2: 0.2819

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
| system | exploration | 55402 | +0.08% [-0.01%, +0.16%] | 0.344 | 0.491 | 0.72 |
| always_hold | exploration | 55402 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55402 | n/a [n/a, n/a] | 0.333 | 0.515 | 1.00 |
| random_mix | exploration | 55402 | +0.01% [-0.03%, +0.05%] | 0.333 | 0.500 | 0.72 |
| momentum_24h | exploration | 55402 | +0.03% [-0.04%, +0.09%] | 0.321 | 0.475 | 1.00 |
| ma_200h | exploration | 55402 | +0.04% [-0.04%, +0.11%] | 0.327 | 0.494 | 0.91 |
| buy-and-hold mean 6h return | exploration | 55402 | +0.04% | | | |
| system | validation | 13122 | -0.01% [-0.13%, +0.11%] | 0.330 | 0.476 | 0.70 |
| always_hold | validation | 13122 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13122 | n/a [n/a, n/a] | 0.333 | 0.521 | 1.00 |
| random_mix | validation | 13122 | -0.00% [-0.06%, +0.05%] | 0.331 | 0.495 | 0.73 |
| momentum_24h | validation | 13122 | -0.04% [-0.13%, +0.05%] | 0.315 | 0.469 | 1.00 |
| ma_200h | validation | 13122 | +0.00% [-0.10%, +0.11%] | 0.328 | 0.489 | 1.00 |
| buy-and-hold mean 6h return | validation | 13122 | +0.05% | | | |

Per year (system edge, point [CI]):
2017: -0.25% · 2018: -0.02% · 2019: +0.19% · 2020: +0.16% · 2021: -0.07% · 2022: -0.01% · 2023: +0.11% · 2024: +0.02% · 2025: -0.09%

Confidence as a probability (exploration, acted hours n=39811, hit rate 0.491, ECE 0.358):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.00–0.50 (avg 0.39) | 110 | 0.409 | [0.322, 0.503] |
| 0.50–0.60 (avg 0.57) | 170 | 0.476 | [0.403, 0.551] |
| 0.60–0.70 (avg 0.66) | 1343 | 0.471 | [0.445, 0.498] |
| 0.70–0.80 (avg 0.76) | 7489 | 0.486 | [0.475, 0.497] |
| 0.80–0.90 (avg 0.86) | 18548 | 0.493 | [0.486, 0.500] |
| 0.90–0.95 (avg 0.91) | 12151 | 0.494 | [0.485, 0.503] |
Brier — constant 0.5: 0.2500 · base rate 0.515: 0.2498 · naive 0.5+score/2: 0.2817

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
| system | exploration | 55372 | +0.08% [-0.22%, +0.37%] | 0.329 | 0.475 | 0.72 |
| always_hold | exploration | 55372 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55372 | n/a [n/a, n/a] | 0.333 | 0.521 | 1.00 |
| random_mix | exploration | 55372 | +0.07% [+0.01%, +0.14%] | 0.335 | 0.504 | 0.72 |
| momentum_24h | exploration | 55372 | -0.03% [-0.25%, +0.19%] | 0.310 | 0.469 | 1.00 |
| ma_200h | exploration | 55372 | +0.07% [-0.22%, +0.32%] | 0.320 | 0.483 | 0.91 |
| buy-and-hold mean 24h return | exploration | 55372 | +0.17% | | | |
| system | validation | 13104 | -0.10% [-0.49%, +0.32%] | 0.323 | 0.481 | 0.70 |
| always_hold | validation | 13104 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13104 | n/a [n/a, n/a] | 0.333 | 0.531 | 1.00 |
| random_mix | validation | 13104 | -0.01% [-0.11%, +0.11%] | 0.330 | 0.492 | 0.73 |
| momentum_24h | validation | 13104 | -0.05% [-0.33%, +0.22%] | 0.320 | 0.478 | 1.00 |
| ma_200h | validation | 13104 | -0.04% [-0.41%, +0.32%] | 0.326 | 0.488 | 1.00 |
| buy-and-hold mean 24h return | validation | 13104 | +0.20% | | | |

Per year (system edge, point [CI]):
2017: -1.09% · 2018: -0.14% · 2019: +0.27% · 2020: +0.18% · 2021: -0.42% · 2022: -0.23% · 2023: +0.26% · 2024: -0.02% · 2025: -0.30%

Confidence as a probability (exploration, acted hours n=39790, hit rate 0.475, ECE 0.374):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.00–0.50 (avg 0.39) | 110 | 0.336 | [0.255, 0.429] |
| 0.50–0.60 (avg 0.57) | 170 | 0.541 | [0.466, 0.614] |
| 0.60–0.70 (avg 0.66) | 1345 | 0.457 | [0.430, 0.483] |
| 0.70–0.80 (avg 0.76) | 7488 | 0.482 | [0.471, 0.493] |
| 0.80–0.90 (avg 0.86) | 18540 | 0.479 | [0.471, 0.486] |
| 0.90–0.95 (avg 0.91) | 12137 | 0.469 | [0.460, 0.478] |
Brier — constant 0.5: 0.2500 · base rate 0.521: 0.2496 · naive 0.5+score/2: 0.2859

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
| system | exploration | 55363 | +0.40% [-0.37%, +1.14%] | 0.334 | 0.490 | 0.72 |
| always_hold | exploration | 55363 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55363 | n/a [n/a, n/a] | 0.333 | 0.530 | 1.00 |
| random_mix | exploration | 55363 | +0.12% [-0.02%, +0.26%] | 0.336 | 0.508 | 0.72 |
| momentum_24h | exploration | 55363 | +0.32% [-0.11%, +0.76%] | 0.329 | 0.496 | 1.00 |
| ma_200h | exploration | 55363 | +0.14% [-0.61%, +0.90%] | 0.316 | 0.485 | 0.91 |
| buy-and-hold mean 72h return | exploration | 55363 | +0.51% | | | |
| system | validation | 13056 | -0.40% [-1.32%, +0.56%] | 0.325 | 0.485 | 0.70 |
| always_hold | validation | 13056 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 13056 | n/a [n/a, n/a] | 0.333 | 0.543 | 1.00 |
| random_mix | validation | 13056 | -0.02% [-0.26%, +0.21%] | 0.331 | 0.507 | 0.73 |
| momentum_24h | validation | 13056 | +0.09% [-0.42%, +0.66%] | 0.323 | 0.485 | 1.00 |
| ma_200h | validation | 13056 | -0.29% [-1.17%, +0.55%] | 0.322 | 0.490 | 1.00 |
| buy-and-hold mean 72h return | validation | 13056 | +0.59% | | | |

Per year (system edge, point [CI]):
2017: -1.65% · 2018: +0.19% · 2019: +0.58% · 2020: -0.30% · 2021: -0.59% · 2022: -0.36% · 2023: +0.80% · 2024: -0.17% · 2025: -0.96%

Confidence as a probability (exploration, acted hours n=39769, hit rate 0.490, ECE 0.360):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.00–0.50 (avg 0.39) | 109 | 0.477 | [0.386, 0.570] |
| 0.50–0.60 (avg 0.57) | 170 | 0.529 | [0.455, 0.603] |
| 0.60–0.70 (avg 0.66) | 1343 | 0.547 | [0.521, 0.574] |
| 0.70–0.80 (avg 0.76) | 7482 | 0.501 | [0.490, 0.512] |
| 0.80–0.90 (avg 0.86) | 18526 | 0.494 | [0.486, 0.501] |
| 0.90–0.95 (avg 0.91) | 12139 | 0.472 | [0.463, 0.481] |
Brier — constant 0.5: 0.2500 · base rate 0.530: 0.2491 · naive 0.5+score/2: 0.2808

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
| system | exploration | 55363 | +0.61% [-0.86%, +2.24%] | 0.331 | 0.487 | 0.72 |
| always_hold | exploration | 55363 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | exploration | 55363 | n/a [n/a, n/a] | 0.333 | 0.533 | 1.00 |
| random_mix | exploration | 55363 | +0.09% [-0.13%, +0.33%] | 0.331 | 0.503 | 0.72 |
| momentum_24h | exploration | 55363 | +0.63% [+0.00%, +1.27%] | 0.328 | 0.492 | 1.00 |
| ma_200h | exploration | 55363 | +0.09% [-1.38%, +1.69%] | 0.319 | 0.480 | 0.91 |
| buy-and-hold mean 168h return | exploration | 55363 | +1.23% | | | |
| system | validation | 12960 | -1.08% [-2.67%, +0.55%] | 0.325 | 0.474 | 0.70 |
| always_hold | validation | 12960 | n/a [n/a, n/a] | 0.333 | nan | 0.00 |
| majority | validation | 12960 | n/a [n/a, n/a] | 0.333 | 0.561 | 1.00 |
| random_mix | validation | 12960 | -0.09% [-0.47%, +0.26%] | 0.327 | 0.504 | 0.73 |
| momentum_24h | validation | 12960 | -0.41% [-1.17%, +0.42%] | 0.328 | 0.496 | 1.00 |
| ma_200h | validation | 12960 | -1.02% [-2.51%, +0.49%] | 0.310 | 0.472 | 1.00 |
| buy-and-hold mean 168h return | validation | 12960 | +1.39% | | | |

Per year (system edge, point [CI]):
2017: -1.21% · 2018: -1.03% · 2019: +0.81% · 2020: -0.47% · 2021: -0.24% · 2022: -1.45% · 2023: +0.29% · 2024: -0.97% · 2025: -1.47%

Confidence as a probability (exploration, acted hours n=39769, hit rate 0.487, ECE 0.363):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.00–0.50 (avg 0.39) | 105 | 0.486 | [0.392, 0.580] |
| 0.50–0.60 (avg 0.57) | 170 | 0.512 | [0.437, 0.586] |
| 0.60–0.70 (avg 0.66) | 1345 | 0.506 | [0.479, 0.532] |
| 0.70–0.80 (avg 0.76) | 7484 | 0.500 | [0.489, 0.512] |
| 0.80–0.90 (avg 0.86) | 18525 | 0.487 | [0.480, 0.494] |
| 0.90–0.95 (avg 0.91) | 12140 | 0.476 | [0.467, 0.485] |
Brier — constant 0.5: 0.2500 · base rate 0.533: 0.2489 · naive 0.5+score/2: 0.2823

Confidence as a probability (validation, acted hours n=9059, hit rate 0.474, ECE 0.387):
| stated conf. | n | observed hit rate | 95% interval |
|---|---|---|---|
| 0.50–0.60 (avg 0.59) | 3 | 0.667 | [0.208, 0.939] (too few) |
| 0.60–0.70 (avg 0.68) | 174 | 0.477 | [0.404, 0.551] |
| 0.70–0.80 (avg 0.76) | 1390 | 0.472 | [0.446, 0.498] |
| 0.80–0.90 (avg 0.86) | 4396 | 0.481 | [0.466, 0.496] |
| 0.90–0.95 (avg 0.91) | 3096 | 0.465 | [0.447, 0.482] |
Brier — constant 0.5: 0.2500 · base rate 0.561: 0.2463 · naive 0.5+score/2: 0.2808
