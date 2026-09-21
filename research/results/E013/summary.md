# E013 — calibrating the 1h move-size model (Phase 11), pre-registered

**Verdict: Platt scaling chosen by the pre-registered rule. Raw fails; isotonic fails.**

What was calibrated: the E012 model's probability that the next hour's move exceeds 0.25%.
Three variants scored on identical out-of-sample rows (27 quarterly folds, 54,472 hours):
the model's own output (raw), a two-parameter re-map fitted on each fold's purged 90-day
calibration slice (Platt), and a step-function re-map on the same slice (isotonic).

| variant | validation ECE | worst bucket (n ≥ 100) | validation Brier | log loss | ρ(p, \|move\|) | C1 calibrated? | C2 ranking kept? |
|---|---|---|---|---|---|---|---|
| raw | 0.043 | 0.060 off | 0.2264 | 0.643 | 0.362 | **no** | — |
| **Platt** | **0.014** | **0.029 off** | **0.2249** | **0.640** | 0.360 | **yes** | **yes** |
| isotonic | 0.014 | 0.100 off | 0.2258 | 0.658 | 0.356 | **no** | yes |

Pre-registered bars: ECE ≤ 0.03 and every bucket with ≥ 100 rows within 0.05 (C1); ρ within
0.02 of raw (C2); choose the simplest variant meeting both unless a more complex one lowers
validation Brier by ≥ 1% (C3). Platt is the simplest that passes.

## What the calibration is actually fixing

In 2024–25 the raw model **under-states** the chance of a large move: it says 0.434 on average
when the observed share is 0.475. (The pre-registered hypothesis expected the opposite; the
data said otherwise — recorded as such.) Platt's intercept drifts from ≈ −0.2 in 2018–19 folds
to ≈ +0.2 in 2024–25 folds: the re-map follows the regime the raw model, trained mostly on
older years, lags behind. Isotonic is sharper in the middle but wrecks the tails (a 90-day slice
is too small for a step function: exact 0/1 outputs, log loss 0.76 in exploration).

Validation reliability, Platt (stated → observed [95% interval], n):
0.16 → 0.16 [0.13, 0.19] 557 · 0.26 → 0.24 [0.21, 0.26] 1,419 · 0.35 → 0.38 [0.36, 0.39] 2,491 ·
0.45 → 0.46 [0.45, 0.48] 3,041 · 0.55 → 0.56 [0.54, 0.57] 2,695 · 0.65 → 0.64 [0.62, 0.67] 1,774 ·
0.74 → 0.71 [0.68, 0.74] 901 · 0.83 → 0.80 [0.74, 0.85] 206.

Per-year ECE, Platt: 2018 0.029 · 2019 0.014 · 2020 0.012 · 2021 0.008 · 2022 0.022 · 2023 0.015 ·
2024 0.013 · 2025 0.019 — under 0.03 in every year; raw is worst exactly in the regime-shift
years (2021, 2024, 2025).

## Guards

Calibrator sees only the purged slice (unit-tested with a recording calibrator); every fold
is fit rows | 25 h | calibration rows | 25 h | test rows; the tripwires (validation ECE < 0.005,
Brier gain > 5%) did not fire — a calibrator cannot add information, and it didn't.

## What this means

The research deliverable is now a **calibrated uncertainty statement**: "P(next-hour move
> 0.25%) = x", where x has meant x in every year since 2018 out of sample. It says nothing
about direction. Phase 12 judges this exact object once on the sealed holdout. The live
system is unchanged: its confidence number stays the labelled heuristic until a separate,
validated decision wires this probability in.
