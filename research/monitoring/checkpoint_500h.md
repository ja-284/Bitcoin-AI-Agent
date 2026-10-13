# Live checkpoint — 500 prospective hours

Hours 2026-09-21T17:00 → 2026-10-12T21:00 UTC — exactly the first 500 prospective graded hours (520 available). Intervals: 48h circular block bootstrap, 500 resamples, seed 17.

**What this checkpoint may conclude (registered 2026-09-21):** first look: skill and calibration points with intervals; NO verdict.

**How often these rules fail by chance at this size (E024):** a model as good as on validation passes E012's Brier part 78%, accuracy 59%, rho 100% of the time at this size; ECE stays under 0.03 only ~10% of the time -- a high ECE here is not evidence.

**Integrity: every judged probability reproduces from its stored inputs with the frozen artefact** (500 rows, max difference 5.6e-16).

| measure | value | registered bar |
|---|---|---|
| Brier gain vs the base rate of these hours | +0.089 [+0.019, +0.137] | ≥ +0.050 (E012) |
| accuracy (large vs small) | 0.698 [0.656, 0.737] | ≥ naive 0.696 + 0.05 (E012) |
| Spearman ρ(p, move size) | +0.324 [+0.143, +0.429] | ≥ 0.10, interval above 0 (E012) |
| ECE | 0.059 [+0.041, +0.093] | ≤ 0.03 (E013) |

| stated | observed | 95% interval | n | counts for E013 (n ≥ 100) | within 0.05 |
|---|---|---|---|---|---|
| 0.09 | 0.08 | [0.02, 0.25] | 25 | no | yes |
| 0.14 | 0.06 | [0.02, 0.12] | 89 | no | NO |
| 0.26 | 0.34 | [0.24, 0.45] | 71 | no | NO |
| 0.35 | 0.34 | [0.27, 0.41] | 155 | yes | yes |
| 0.45 | 0.37 | [0.28, 0.47] | 89 | no | NO |
| 0.54 | 0.44 | [0.32, 0.58] | 54 | no | NO |
| 0.63 | 0.71 | [0.47, 0.87] | 17 | no | NO |

**No verdict at this checkpoint — by registration.**

### Against the free 24h-EWMA rule (E019, pre-committed)

```
{
 "why": "E019: a 24-hour EWMA of 'did recent hours move a lot?' needs no fitting at all and reached 40% of the model's skill on development data. Comparing the model only against the base rate, as E012 did, sets the bar far too low.",
 "hours_compared": 500,
 "model_brier": 0.19273427479662653,
 "reference_brier": 0.20914648335460398,
 "model_skill": 0.08908861352169095,
 "reference_skill": 0.011520325948067955,
 "model_brier_minus_reference": -0.016412208557977453,
 "observed_large_move_share": 0.304,
 "development_expectation": "the model had 2.47x the reference's skill on validation data (E019)",
 "note": "Pre-committed before the live sample was large enough to judge, so the comparison could not be chosen after seeing the answer. Far too few hours to mean anything yet -- this line exists to be read at the 500-hour checkpoint. Both skill figures are measured against a base rate computed on these very hours, which at small n is an ORACLE that knew whether the period turned out calm or wild; it flatters neither side but makes both look worse than they are. The difference between the two Briers is the part that is comparable."
}
```

*Nothing about the model changes because of these numbers (rule 2). A failure demotes the deliverable in every report; it never touches the live signal (rule 6).*
