# E018 -- how many features does the 1h move-size model need?

Generated 2026-09-22T18:43:33.874231+00:00  |  pipeline 0.2.0  |  snapshot btcusdt_1h_2026-09-19.csv
Target: |1h return| > 0.25%.  Settings identical to E013 except the feature list.
Folds: 27; every variant scored on the same 64180 hours.

## Q1 -- redundancy among the nine inputs (exploration, descriptive)

| input | variance inflation | most like |
|---|---|---|
| `tr_mean_14_rel` | 10.4 | `rv_24` (rho +0.92) |
| `rv_24` | exactly determined by the others | `tr_mean_14_rel` (rho +0.92) |
| `rv_168` | exactly determined by the others | `tr_mean_14_rel` (rho +0.81) |
| `vol_ratio_24_168` | exactly determined by the others | `rv_24` (rho +0.57) |
| `trades_rel_24h` | 6.2 | `trades_rel_168h` (rho +0.78) |
| `trades_rel_168h` | 7.9 | `trades_rel_24h` (rho +0.78) |
| `hour_sin` | 1.0 | `trades_rel_24h` (rho -0.14) |
| `hour_cos` | 1.2 | `trades_rel_24h` (rho -0.26) |
| `is_weekend` | 1.1 | `trades_rel_168h` (rho -0.26) |

Highest absolute correlations: `tr_mean_14_rel`/`rv_24` 0.92, `tr_mean_14_rel`/`rv_168` 0.81, `rv_24`/`rv_168` 0.78, `trades_rel_24h`/`trades_rel_168h` 0.78, `rv_24`/`vol_ratio_24_168` 0.57, `tr_mean_14_rel`/`vol_ratio_24_168` 0.42

**One input is not new information at all.** `log(vol_ratio_24_168) == log(rv_24) - log(rv_168)`, to floating point (largest disagreement 1.0e-15 over 51053 hours). After the declared log transforms the nine inputs carry **eight** independent pieces of information; the ninth is their arithmetic. L2 regularisation keeps the predictions well behaved, but the individual coefficients of the three volatility terms cannot be read separately.

## Q2 -- group ablation (paired against all nine)

| variant | validation Brier | skill | Brier minus full | in SEs | carries information? |
|---|---|---|---|---|---|
| all nine | 0.22487 | +0.0983 | -- | -- | -- |
| without volatility | 0.23982 | +0.0383 | +0.01495 | +8.9 | YES |
| without trade_intensity | 0.22923 | +0.0808 | +0.00436 | +10.5 | YES |
| without calendar | 0.22631 | +0.0925 | +0.00145 | +6.5 | YES |

## Q3 -- forward selection (order fixed on exploration only)

| k | added | exploration Brier | validation Brier | validation skill | ECE | rho | within 1 SE of best? |
|---|---|---|---|---|---|---|---|
| 1 | `tr_mean_14_rel` | 0.21722 | 0.23488 | +0.0582 | 0.018 | +0.268 | no |
| 2 | `trades_rel_24h` | 0.21536 | 0.22803 | +0.0856 | 0.015 | +0.333 | no |
| 3 | `rv_168` | 0.21441 | 0.22699 | +0.0898 | 0.016 | +0.343 | no |
| 4 | `hour_cos` | 0.21401 | 0.22596 | +0.0939 | 0.015 | +0.351 | no |
| 5 | `hour_sin` | 0.21379 | 0.22551 | +0.0957 | 0.017 | +0.356 | no |
| 6 | `is_weekend` | 0.21362 | 0.22502 | +0.0977 | 0.016 | +0.359 | no |
| 7 | `trades_rel_168h` | 0.21356 | 0.22496 | +0.0979 | 0.015 | +0.360 | no |
| 8 | `rv_24` | 0.21357 | 0.22488 | +0.0983 | 0.014 | +0.360 | no |
| 9 | `vol_ratio_24_168` | 0.21357 | 0.22487 | +0.0983 | 0.014 | +0.360 | yes |

## Decision (pre-registered one-standard-error rule)

- best validation skill at **k = 9**: `tr_mean_14_rel`, `trades_rel_24h`, `rv_168`, `hour_cos`, `hour_sin`, `is_weekend`, `trades_rel_168h`, `rv_24`, `vol_ratio_24_168`
- smallest k within 1 SE: **k = 9** -> `tr_mean_14_rel`, `trades_rel_24h`, `rv_168`, `hour_cos`, `hour_sin`, `is_weekend`, `trades_rel_168h`, `rv_24`, `vol_ratio_24_168`
- validation Brier 0.22487, skill +0.0983, ECE 0.014, rho +0.360
- C1 calibrated: **PASS**; C2 ranking preserved (within 0.02 of the nine-feature rho +0.360): **PASS**
- relative Brier vs all nine: +0.00% (tripwire at +3%: not fired)

## Secondary analysis -- NOT pre-registered, and why it was added

The pre-registered rule compares two models with a **paired** bootstrap, whose standard
error shrinks as fast as the difference it is measuring. At k = 8 the validation Brier is
worse by 0.00001 -- 0.005% relative -- with a paired standard error of 0.000005, so the rule
calls it two standard errors worse. It is answering *are these two models statistically
distinguishable on 13,127 paired rows?* (nearly always yes) rather than *does the extra
feature matter?*. Breiman's classical one-standard-error rule uses the standard error of the
best model's own estimate, unpaired. Both variants below are secondary; the pre-registered
answer above stands as the primary result.

| view | answer | validation Brier | skill |
|---|---|---|---|
| pre-registered, paired | k = 9 | 0.22487 | +0.0983 |
| classical one-SE (unpaired SE = 0.00197) | k = 4 | 0.22596 | +0.0939 |
| smallest k with >= 99% of the best skill | k = 6 | | |
| smallest k with >= 95% of the best skill | k = 4 | | |

Dropping the mathematically redundant input (`vol_ratio_24_168`), leaving eight:
validation Brier 0.22488 (+0.0045% relative to all nine), skill +0.0983, ECE 0.014, rho +0.360.

## Q4 -- coefficient sign stability across folds (all nine)

| input | sign agreement | median coefficient |
|---|---|---|
| `tr_mean_14_rel` | 1.00 | +0.644 |
| `rv_24` | 1.00 | +0.110 |
| `rv_168` | 1.00 | +0.177 |
| `vol_ratio_24_168` | 1.00 | -0.060 |
| `trades_rel_24h` | 0.89 | +0.035 |
| `trades_rel_168h` | 1.00 | +0.082 |
| `hour_sin` | 0.96 | -0.039 |
| `hour_cos` | 0.96 | -0.066 |
| `is_weekend` | 0.78 | -0.024 |
