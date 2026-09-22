# E022 -- which inputs carry the part of the skill that is ours?

Generated 2026-09-22T19:46:23.312118+00:00  |  pipeline 0.2.0  |  27 folds, 96 variants evaluated

Identical machinery, identical rows, identical folds -- only the target definition differs.
**Exploratory.** Nothing here is adopted; the three predictions exist so the run can be wrong.

## The two targets

| target | validation base rate | Brier | skill | ECE | rho |
|---|---|---|---|---|---|
| fixed 0.25% | 0.475 | 0.22487 | +0.0983 | 0.014 | +0.360 |
| volatility-scaled | 0.495 | 0.23157 | +0.0736 | 0.012 | +0.338 |

Tripwire (this run must reproduce E021's scaled-target skill of +0.07363): difference 0.00000, not fired.

## The order features get picked, and how much each target needs them

| feature | picked at k (fixed) | picked at k (scaled) | moved |
|---|---|---|---|
| `tr_mean_14_rel` (level) | 1 | 2 | **later** (+1) |
| `rv_24` (level) | 8 | 8 | **same** |
| `rv_168` (level) | 3 | 3 | **same** |
| `vol_ratio_24_168` (relative) | 9 | 7 | **earlier** (-2) |
| `trades_rel_24h` (relative) | 2 | 9 | **later** (+7) |
| `trades_rel_168h` (relative) | 7 | 1 | **earlier** (-6) |
| `hour_sin` (relative) | 5 | 5 | **same** |
| `hour_cos` (relative) | 4 | 6 | **later** (+2) |
| `is_weekend` (relative) | 6 | 4 | **earlier** (-2) |

## What each group is worth to each target

| group removed | skill lost against fixed | skill lost against scaled |
|---|---|---|
| volatility | 61% | 14% |
| trade_intensity | 18% | 23% |
| calendar | 6% | 7% |

## The three pre-registered predictions

| # | prediction | outcome |
|---|---|---|
| P1 | a level feature is picked later AND a relative one earlier | **HOLDS** — later: ['tr_mean_14_rel']; earlier: ['vol_ratio_24_168', 'trades_rel_168h', 'is_weekend'] |
| P2 | the volatility group costs under 40% of skill | **HOLDS** — 61% against fixed, 14% against scaled |
| P3 | the first pick is not `tr_mean_14_rel` | **HOLDS** — first pick is `trades_rel_168h` |

**3 of 3 held: the inputs that carry within-regime timing differ from the ones that carry the headline skill.**

## Coefficient signs (all nine, against each target)

| feature | median coef (fixed) | sign agreement | median coef (scaled) | sign agreement |
|---|---|---|---|---|
| `tr_mean_14_rel` | +0.644 | 1.00 | +0.394 | 1.00 |
| `rv_24` | +0.110 | 1.00 | -0.055 | 1.00 |
| `rv_168` | +0.177 | 1.00 | -0.087 | 1.00 |
| `vol_ratio_24_168` | -0.060 | 1.00 | +0.031 | 1.00 |
| `trades_rel_24h` | +0.035 | 0.89 | -0.149 | 0.96 |
| `trades_rel_168h` | +0.082 | 1.00 | +0.277 | 1.00 |
| `hour_sin` | -0.039 | 0.96 | -0.042 | 0.93 |
| `hour_cos` | -0.066 | 0.96 | -0.057 | 0.93 |
| `is_weekend` | -0.024 | 0.78 | -0.034 | 0.96 |

## Skill by feature count (validation)

| k | fixed | scaled |
|---|---|---|
| 1 | +0.0582 | +0.0645 |
| 2 | +0.0856 | +0.0722 |
| 3 | +0.0898 | +0.0697 |
| 4 | +0.0939 | +0.0713 |
| 5 | +0.0957 | +0.0733 |
| 6 | +0.0977 | +0.0746 |
| 7 | +0.0979 | +0.0745 |
| 8 | +0.0983 | +0.0745 |
| 9 | +0.0983 | +0.0736 |
