# E032 — does the faint 1h probability of UP carry measurable, calibrated, stable skill? (research-only)

Generated 2026-10-14T15:14 UTC · 56,309 development hours, identical rows for every candidate · 28 folds · directional track only · hypothesis-generating (validation wear) · measurable skill is not usefulness

## exploration (43,182 hours; UP share 0.509)

| measure | model (8 inputs) | one-feature (taker-buy share 1h) |
|---|---|---|
| Brier (base rate 0.24995) | 0.24901 | 0.24947 |
| Brier skill vs the leak-free base rate | +0.00375 | +0.00190 |
| log loss | 0.69117 | 0.69209 |
| ECE · E013 buckets | 0.006 · yes | 0.007 · yes |
| calibration intercept / slope | -0.039 / 1.22 | -0.124 / 2.50 |
| Spearman ρ(p, 1h return) | +0.0459 | +0.0429 |
| accuracy at 0.5 (naive 0.509) | 0.525 | 0.514 |
| return edge, p>0.5 minus p<0.5 (descriptive) | -0.0040% [-0.0184, +0.0099] | -0.0199% [-0.0431, +0.0020] |
| gross signed return per hour vs a 0.10% round trip (descriptive) | +0.0009% | +0.0027% |

Brier(base rate) − Brier(model): +0.000937 [+0.000720, +0.001138] · Brier(one-feature) − Brier(model): +0.000461 [+0.000277, +0.000633] (positive = model better)

Per year, model skill vs the base rate: 2018 +0.0017; 2019 +0.0024; 2020 +0.0036; 2021 +0.0029; 2022 +0.0036; 2023 +0.0067

## validation (13,127 hours; UP share 0.508)

| measure | model (8 inputs) | one-feature (taker-buy share 1h) |
|---|---|---|
| Brier (base rate 0.24994) | 0.24887 | 0.24898 |
| Brier skill vs the leak-free base rate | +0.00428 | +0.00384 |
| log loss | 0.69088 | 0.69110 |
| ECE · E013 buckets | 0.004 · yes | 0.005 · yes |
| calibration intercept / slope | -0.017 / 1.02 | -0.036 / 1.30 |
| Spearman ρ(p, 1h return) | +0.0543 | +0.0535 |
| accuracy at 0.5 (naive 0.508) | 0.527 | 0.526 |
| return edge, p>0.5 minus p<0.5 (descriptive) | +0.0095% [-0.0091, +0.0294] | +0.0239% [+0.0073, +0.0417] |
| gross signed return per hour vs a 0.10% round trip (descriptive) | +0.0069% | +0.0134% |

Brier(base rate) − Brier(model): +0.001070 [+0.000570, +0.001573] · Brier(one-feature) − Brier(model): +0.000110 [-0.000179, +0.000405] (positive = model better)

Per year, model skill vs the base rate: 2024 +0.0047; 2025 +0.0034

## Pre-registered hypotheses

- H_a_skill_beyond_the_base_rate: **HOLDS**
- H_b_more_than_one_reversal_feature: **FAILS**
- H_c_calibrated: **HOLDS**
- H_d_stable: **HOLDS**
- (years with positive skill: 8 of 8)

*Research-only and hypothesis-generating: about ten directional experiments, E011 above all, have seen these rows. Whatever the verdict, the live BUY/HOLD/SELL signal, scoring 0.2.0, move_size_1h_v1 and the checkpoints are unchanged, and nothing is combined with the move-size track.*
