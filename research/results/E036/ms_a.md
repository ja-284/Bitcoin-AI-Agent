# E036 (MS-A): do amihud_rel_168 and trade_size_rel_24 add move-size information? Verdict: **NOT_SUPPORTED**

Generated 2026-10-17T10:08 UTC · code 909e00a · development data only · hypothesis-generating (about 35 experiments have seen these periods) · statistics, not economics

Rows: 63,988 common frame rows (E013: 64,180; 192 hours lost because a new input is undefined there); 54,286 out-of-sample rows in 27 folds; EWMA unavailable on 0 rows.

| validation (exploration) | reference (9 inputs) | candidate (11 inputs) | EWMA rule |
|---|---|---|---|
| Brier | 0.22486 (0.21341) | 0.22510 (0.21334) | 0.23946 (0.21944) |
| skill vs in-period base rate | +0.09836 (+0.14637) | +0.09740 (+0.14663) | +0.03979 (+0.12223) |
| log loss | 0.64020 (0.61432) | 0.64071 (0.61416) | 0.67185 (0.62896) |
| ECE | 0.0137 (0.0044) | 0.0144 (0.0046) | 0.0239 (0.0128) |
| Spearman rho(p, |r|) | +0.3603 (+0.4411) | +0.3587 (+0.4415) | +0.2350 (+0.4052) |
| E013 bucket rule (validation) | True | True | |

**Primary:** validation d = Brier(reference) − Brier(candidate) = -0.000240 [-0.000424, -0.000068] (95%), bootstrap p 0.0120 (one comparison in its family). Practical threshold 0.002453; exploration d +0.000063 [+0.000010, +0.000116].

d per year: 2018 +0.00000; 2019 -0.00003; 2020 +0.00007; 2021 +0.00007; 2022 -0.00001; 2023 +0.00021; 2024 -0.00025; 2025 -0.00021

| registered criterion | result |
|---|---|
| S1_difference_positive_and_significant | False |
| S2_practical | False |
| S3_exploration_point_estimate_positive | True |
| S4_calibration | True |
| S5_years_positive | 4 |
| S5_at_least_6_of_8_years | False |
| S6_ranking_not_worse | True |

Candidate skill / reference skill: 0.9902 (bar 1.10; tripwire 1.5)

Candidate coefficients (median across folds, share of folds with the median's sign): amihud_rel_168 -0.0123 (0.74); trade_size_rel_24 +0.0317 (0.93)
