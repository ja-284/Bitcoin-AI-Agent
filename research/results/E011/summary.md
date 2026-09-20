# E011 — one fitted directional model (Phase 9), walk-forward, pre-registered

**Verdict: no pass at any horizon, in any layout (0 of 15 runs). No tripwire fired.**

The model: L2 logistic regression, C = 0.1 fixed in advance, standardised on each fold's
training rows only, refitted on each of the 28 (set A) / 19 (set B) quarterly folds with a
purge of H hours + 24h embargo (E010-verified bench). Three horizons, two pre-registered
feature sets, expanding (primary) and rolling 730d (robustness), plus one supplementary
coverage check (set A without `vol_pct_720`) declared before it ran.

| run | rows | acc vs naive (expl / vali) | return edge CI excludes 0? (expl / vali) | Brier < base? (expl / vali) | pass |
|---|---|---|---|---|---|
| A expanding 1h | 45,740 | 0.523 > 0.508 / 0.527 > 0.508 | no / no | yes / yes | **no** |
| A expanding 6h | 45,702 | 0.515 > 0.512 / 0.529 > 0.521 | no / no | no / yes | no |
| A expanding 24h | 45,660 | 0.521 > 0.520 / 0.534 > 0.531 | no / no | no / yes | no |
| B expanding 1h | 34,425 | 0.527 > 0.504 / 0.528 > 0.508 | no / no | yes / yes | **no** |
| B expanding 6h | 34,413 | 0.513 > 0.501 / 0.525 > 0.521 | no / no | no / yes | no |
| B expanding 24h | 34,395 | 0.518 > 0.500 / 0.538 > 0.531 | no / no | **no** (0.258 vs 0.250) / yes | no |
| A rolling 1h | 45,740 | 0.528 / 0.530 above naive | no / yes (+0.016% [+0.000, +0.036]) | yes / yes | no |
| A rolling 6h, 24h; B rolling 1h, 6h, 24h | | mixed; 24h rolling worse than base rate on Brier in both periods | no | | no |
| A− (no vol_pct_720) 1h / 6h / 24h | 56,309 / 56,258 / 56,215 | same picture as A | 6h exploration edge **negative** and CI excludes 0 (−0.148% [−0.266, −0.029]) | | no |

## What the 1-hour result actually is

At 1h every layout (five of five) gets direction right ~2 points more often than the
majority-guess rate, in both periods, and in 7 of 8 years (all years for the A− and B
layouts). The coefficients that carry it are `taker_buy_share_1h` and `momentum_score`,
both negative in 100% of folds: the short-horizon *reversal* family from E002/E008, now
fitted rather than hand-tested. Brier improves by 0.0009 (0.4%).

And it is worth nothing in return terms. Broken down by move size (A expanding 1h):

| next-hour move size | model accuracy | naive | n |
|---|---|---|---|
| smallest 25% | 0.512 | 0.500 | 11,435 |
| 25–50% | 0.534 | 0.507 | 11,435 |
| 50–75% | 0.552 | 0.514 | 11,435 |
| 75–90% | 0.521 | 0.514 | 6,861 |
| **largest 10%** | **0.465** | 0.509 | 4,574 |

The model earns its accuracy on small moves and is *wrong more often than chance on the
largest ones*: after an hour of heavy aggressive buying the next hour usually drifts down a
little, but when it does not, it moves up a lot. Mean |return| when correct 0.369% vs 0.403%
when wrong; edge +0.006% − +0.010% ≈ 0; even the 20% most confident calls (accuracy 0.553)
have an edge of +0.005%. Accuracy is not profitability — rule 8 in numerical form.

## Other observations (not findings)

- The model calls UP 72% of the time at 1h (base rate 51%): the fitted intercept inherits the
  training years' up-bias, which is why "always UP" is such a strong benchmark and why the
  hindsight naive rate beats a training-prior model in bear years (E010).
- Set B (adds funding, premium, dollar, yield) does not improve on set A anywhere; at 24h it is
  *worse* than the base rate on Brier in exploration (`tnx_chg_5d` dominates with a coefficient
  that does not generalise). Fewer rows (from 2019-12) and more inputs = more overfitting.
- The coverage check (A−) reproduces A's conclusion, so the 24% of 2018–2021 hours blanked by
  `vol_pct_720` do not change anything.
- Consistency across years at 1h (accuracy − naive, points): A− 2018 +0.7, 2019 +1.4, 2020 +0.5,
  2021 +1.2, 2022 +2.1, 2023 +2.4, 2024 +1.7, 2025 +2.0 — small, stable, growing slightly.

## Consequence

A combinable directional signal does **not** exist among the inputs available for free with
trustworthy timestamps. Phase 10 (re-weighting scoring 0.1.0) is therefore not justified:
there is nothing to re-weight towards. The honest directional statement is P(up over H) ≈ the
base rate, i.e. HOLD. The research effort now goes to what *is* predictable — move size
(E003, E008) — as an uncertainty model (E012) and its calibration (Phase 11).
