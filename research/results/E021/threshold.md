# E021 -- a fixed threshold, or one that adapts?

Generated 2026-09-22T19:31:46.748746+00:00  |  pipeline 0.2.0  |  snapshot btcusdt_1h_2026-09-19.csv
F: |1h return| > 0.25%.   V: |1h return| > 1.0 x the median of the last 720h of completed returns.
27 folds; both candidates on the same 64180 hours (0 dropped where V's threshold was unavailable). V's median threshold was 0.256%.

## Validation

| target | positive rate | Brier | skill | ECE | worst bucket | rho with realised move |
|---|---|---|---|---|---|---|
| F_fixed_incumbent | 0.475 | 0.22487 | +0.0983 | 0.014 | 0.029 | +0.360 |
| V_vol_scaled | 0.495 | 0.23157 | +0.0736 | 0.012 | 0.048 | +0.338 |

Raw Brier is deliberately not compared between the rows: they are different events. Skill and rho are.

The E019 no-fitting reference, scored against each target on the same validation rows:

- F_fixed_incumbent: reference skill +0.0398 (model +0.0983)
- V_vol_scaled: reference skill +0.0003 (model +0.0736)

## Per year: does the target keep meaning the same thing?

| year | F positive rate | V positive rate | F skill | V skill | F ECE | V ECE |
|---|---|---|---|---|---|---|
| 2018 | 0.669 | 0.488 | +0.0113 | +0.0203 | 0.029 | 0.038 |
| 2019 | 0.473 | 0.481 | +0.1097 | +0.0112 | 0.014 | 0.051 |
| 2020 | 0.496 | 0.508 | +0.1064 | +0.0512 | 0.012 | 0.013 |
| 2021 | 0.676 | 0.493 | +0.0426 | +0.0227 | 0.008 | 0.025 |
| 2022 | 0.514 | 0.476 | +0.1279 | +0.0580 | 0.022 | 0.013 |
| 2023 | 0.336 | 0.508 | +0.1213 | +0.0693 | 0.015 | 0.045 |
| 2024 | 0.489 | 0.502 | +0.0907 | +0.0681 | 0.013 | 0.019 |
| 2025 | 0.448 | 0.481 | +0.1097 | +0.0838 | 0.019 | 0.012 |

Spread of the yearly positive rate (years with >= 500 rows): F 0.340, V 0.032.

## Verdict (pre-registered, all four parts required)

| check | F | V | passes? |
|---|---|---|---|
| (i) predictability: skill_V >= 0.90 x skill_F | +0.0983 | +0.0736 (0.75x) | FAIL |
| (ii) calibration: ECE <= 0.03, buckets within 0.05 | — | ECE 0.012, worst 0.048 | PASS |
| (iii) ranking: rho_V within 0.02 of rho_F | +0.360 | +0.338 | FAIL |
| (iv) stability: V's yearly spread at least 2x smaller | 0.340 | 0.032 | PASS |

Tripwire (V more than 1.5x F's skill -> investigate for leakage): not fired

**the volatility-scaled definition does not clear the pre-registered bars -- the fixed target stands.**

## What this actually shows: where the model's skill comes from

The volatility-scaled threshold divides the recent volatility level OUT of the target. Whatever
survives that is skill at picking which hour inside a regime will be big, rather than skill at
knowing how lively the market is at all. Reading the two targets side by side splits the skill in two:

| | against the fixed target | against the volatility-scaled target |
|---|---|---|
| the no-fitting EWMA reference (E019) | +0.0398 | +0.0003 |
| the model | +0.0983 | +0.0736 |
| model / reference | 2.47x | 227x |

The reference is a pure level-tracker, and once the level is divided out it knows **nothing**
(+0.0003). The model keeps +0.0736, so it is not merely re-reading the volatility level -- but most of
its skill against the fixed target (+0.0983) *is* the level, which is available for free.

This also gives the 2026-09-22 live watch item a plausible mechanism. The fixed target's positive
rate ranges from 0.336 to 0.676 across years -- it is a different question in a calm year than in a
wild one -- so a model trained across the mixture will over-state large moves during a quiet
stretch, which is exactly what those 18 hours looked like. That remains a mechanism, not a finding:
n was 18.

## Exploration (reported, not used for the verdict)

| target | positive rate | skill | ECE | rho |
|---|---|---|---|---|
| F_fixed_incumbent | 0.499 | +0.1457 | 0.004 | +0.440 |
| V_vol_scaled | 0.493 | +0.0435 | 0.021 | +0.310 |
