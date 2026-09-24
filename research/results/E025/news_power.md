# E025 — how many live hours does the news evaluation need? (planning)

Generated 2026-09-24T17:28 UTC · 97 usable news hours (2026-09-19T20 → 2026-09-24T15), contiguous segments [5, 41, 51].

**Reads the news score only — no return or outcome was touched, so the eventual test stays clean.**

## The news score is a slow-moving series

Mean +0.224, sd 0.133, range -0.032 to +0.552 (5 negative hours); average change per hour 0.042.

| lag (hours) | 1 | 2 | 3 | 6 | 12 | 18 | 23 |
|---|---|---|---|---|---|---|---|
| autocorrelation | +0.88 | +0.83 | +0.78 | +0.56 | +0.22 | +0.18 | -0.02 |
| pairs | 94 | 91 | 88 | 80 | 68 | 56 | 46 |

An AR(1) with φ = 0.884 (the live lag-1 value) reproduces the decay closely enough for planning.

## How much each hour is worth

| horizon | variance inflation (live ACF) | (AR(1) model) | (24h window model) |
|---|---|---|---|
| 1h | 1.0 | 1.0 | 1.0 |
| 6h | 5.0 | 4.8 | 5.5 |
| 24h | 12.1 | 11.0 | 16.0 |

Next-hour returns are close to independent from hour to hour, so at 1h the news score's persistence does **not**
reduce the information per hour (inflation 1.0). At 6h and 24h the forward returns overlap, and a persistent predictor
then counts several times over.

## Smallest correlation the planned test can detect (80% power, two-sided 5%)

| usable news hours | 1h | 6h | 24h |
|---|---|---|---|
| 500 | 0.125 | 0.274 | 0.416 |
| 1,000 | 0.089 | 0.194 | 0.294 |
| 2,000 | 0.063 | 0.137 | 0.208 |
| 3,000 | 0.051 | 0.112 | 0.170 |
| 5,000 | 0.040 | 0.087 | 0.132 |
| 10,000 | 0.028 | 0.061 | 0.093 |

| horizon | hours for ρ = 0.10 | ρ = 0.05 | ρ = 0.03 |
|---|---|---|---|
| 1h | 785 | 3,140 | 8,721 |
| 6h | 3,760 | 15,039 | 41,775 |
| 24h | 8,659 | 34,633 | 96,201 |

## The planned test itself, simulated

400 simulated records per cell; 48h circular block bootstrap (500 resamples); heavy-tailed returns. Share of records whose 95% interval excludes zero:

| cell | share |
|---|---|
| n=500 h=1 rho=0.0 | 10.8% |
| n=500 h=6 rho=0.0 | 10.2% |
| n=500 h=24 rho=0.0 | 10.5% |
| n=2000 h=24 rho=0.0 | 7.0% |
| n=500 h=1 rho=0.05 | 27.0% |
| n=2000 h=1 rho=0.05 | 74.2% |
| n=3000 h=1 rho=0.05 | 88.2% |
| n=500 h=1 rho=0.1 | 71.0% |
| n=2000 h=1 rho=0.1 | 99.5% |
| n=2000 h=24 rho=0.05 | 23.0% |
| n=5000 h=24 rho=0.05 | 41.5% |

Rows with ρ = 0 are the false-positive rate (should be near 5%); the others are power.


## Precision check and pooling (added 2026-09-24 17:30 UTC)

This run (seed 25) repeats the first run's first 200 datasets, so it is pooled only with an
independent precision check (seed 77, the registered 500 resamples):

| cell | independent check | this run | pooled |
|---|---|---|---|
| 500 h, 1h, no effect | 7.3% ± 2.1 (600) | 10.8% (400) | **8.7% ± 1.8** (1,000) |
| 2,000 h, 1h, no effect | 4.3% ± 2.3 (300) | — | 4.3% |
| 5,000 h, 1h, no effect | 4.0% ± 3.1 (150) | — | 4.0% |

**The interval is liberal at 500 hours (about 9% false positives instead of 5%) and nominal from
about 2,000 hours.** The first run's 10–11.5% (200 × 200) is superseded, not deleted (E025 record).
