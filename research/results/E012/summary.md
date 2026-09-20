# E012 — move-size (uncertainty) model, walk-forward, pre-registered

**Verdict: PASS at 1h (expanding and rolling). No pass at 6h (near-miss) and 24h. No tripwire.**

Question asked: not "which way will Bitcoin go" (E011 showed that is not answerable from
these inputs) but "how big will the next move be". Target: 1 if |return over H| exceeds a
fixed threshold (0.25% at 1h, 0.75% at 6h, 1.5% at 24h — round numbers near the
exploration-period median, fixed before running). Model: L2 logistic regression, C = 0.1,
nine inputs (recent volatility ×4, trade intensity ×2, hour-of-day ×2, weekend), refitted
on each of 28 quarterly folds with purge + embargo (E010-verified bench).

| run | Brier vs base (expl / vali) | accuracy − naive, points (expl / vali) | ρ(p, realised \|move\|) (expl / vali) | pass |
|---|---|---|---|---|
| **1h expanding** | **−14.9% / −9.3%** | **+15.0 / +10.0** | **0.45 / 0.36** (CIs ±0.02) | **YES** |
| 1h rolling | −14.9% / −9.6% | +15.1 / +10.5 | 0.45 / 0.37 | YES |
| 6h expanding | −11.8% / −8.1% | +7.7 / **+4.6** (needs +5.0) | 0.39 / 0.33 | no (near-miss) |
| 6h rolling | −11.8% / −8.8% | +7.8 / +4.7 | 0.39 / 0.34 | no |
| 24h expanding | −7.9% / **−3.0%** | +10.5 / **+2.4** | 0.34 / 0.21 | no |
| 24h rolling | −7.6% / −2.9% | +10.2 / +2.6 | 0.33 / 0.20 | no |

Per year at 1h (accuracy − naive, points): 2018 +13.4, 2019 +11.0, 2020 +13.3, **2021 −1.7**,
2022 +12.6, 2023 +3.4, 2024 +10.7, 2025 +8.6. 2021 is negative in every run at every horizon:
it was volatile all year, the "large move" base rate was highest, and the hindsight naive
rate is then very hard to beat. Validation (2024–25, calmer) is weaker than exploration
everywhere, but the 1h model still clears every bar.

What carries it (1h, last fold, standardised): `tr_mean_14_rel` +0.57 (same sign in 100% of
folds), `rv_168` +0.21, `trades_rel_24h` +0.16, `rv_24` +0.14, `hour_cos` −0.09. The fitted
ρ of 0.45 equals E003's fit-free value for `tr_mean_14_rel` alone, so the model adds little
beyond the single strongest input — which is exactly what a real, unglamorous effect
(volatility clustering) should look like, and not what a leak looks like.

Before any calibration the stated probabilities are already close to honest (ECE 0.013
exploration, 0.040 validation); Phase 11 tests whether a purged-slice calibrator makes them
better or worse, with reliability intervals.

**What this is and is not.** It says *how much* the price is likely to move in the next hour,
not *which way*. It is the basis for a calibrated uncertainty statement and for HOLD-heavy
signals ("expect a large move, direction unknown"). It changes nothing in the live system.
