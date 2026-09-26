# E029 — a sequential calibration-drift detector on the move-size model family (research-only)

Generated 2026-09-26T14:18 UTC · 54,472 development hours · two-sided CUSUM, k = 0.025, h = 17.5 (control: 0.196 alarms per 1,000 h) · never run on live data

## False alarms on the real record (no injection)

0.716 alarms per 1,000 hours over the whole record (39 alarms); control 0.196.

- exploration: 33 alarms in 41,345 h (0.798 per 1,000 h); overall stated − observed +0.0027
- validation: 6 alarms in 13,127 h (0.457 per 1,000 h); overall stated − observed -0.0040

Alarms: 2019-01-12 (over), 2019-01-20 (over), 2019-05-03 (under), 2019-05-10 (under), 2019-07-27 (over), 2020-01-17 (under), 2020-02-29 (under), 2020-06-02 (over), 2020-06-06 (over), 2020-06-10 (over), 2020-06-21 (over), 2020-07-09 (over), 2020-07-13 (over), 2020-07-18 (over), 2020-07-26 (over), 2020-08-30 (under), 2020-09-08 (under), 2020-09-24 (under), 2020-11-17 (under), 2021-09-06 (over), 2021-10-19 (over), 2021-12-11 (under), 2022-04-20 (over), 2022-10-01 (over), 2022-10-15 (over), 2022-10-28 (over), 2022-12-09 (over), 2023-01-21 (over), 2023-04-02 (under), 2023-04-24 (under), 2023-06-28 (under), 2023-11-01 (under), 2023-12-20 (under), 2024-03-20 (under), 2024-06-20 (over), 2024-07-02 (over), 2024-08-17 (over), 2024-10-03 (under), 2024-12-24 (under)

## Detection delay after a persistent offset (hours)

| offset | real: median | real: within 500 / 2,000 | control: median | control: within 500 / 2,000 |
|---|---|---|---|---|
| +0.03 | 773 | 35% / 78% | 836 | 27% / 85% |
| +0.05 | 349 | 60% / 97% | 420 | 61% / 100% |
| +0.10 | 168 | 95% / 100% | 177 | 99% / 100% |
| -0.03 | 722 | 40% / 81% | 789 | 31% / 90% |
| -0.05 | 420 | 60% / 97% | 394 | 62% / 100% |
| -0.10 | 173 | 93% / 100% | 174 | 99% / 100% |

103 windows of 3,000 h (offset from hour 500); control = outcomes simulated from the original probabilities (5 simulations).

## Pre-registered hypotheses

- H_a_false_alarms: **FAILS**
- H_b_detection: **HOLDS**
- H_c_real_like_control: **HOLDS**

*Research-only and hypothesis-generating. Not wired to anything; the registered checkpoints remain the only judgement of the live record, and move_size_1h_v1 is unchanged.*
