# Incident: "All jobs have failed" on the hourly workflow, 2026-09-21 19:31 → 2026-09-22 13:0x UTC

**Severity for the research record: none. Severity for operations: real** — roughly half of
all hourly jobs ended red for ~17 hours, and 8 hours of the new shadow record are missing.

## What the owner saw

Repeated GitHub notifications: *"Hourly Bitcoin analysis: All jobs have failed"*, the
`analyze` job marked failed, recurring around the hourly runs.

## What actually happened

| | |
|---|---|
| Live predictions in the window | **18 of 18 expected hours present, 0 missing** |
| Outcome grading | complete (1h/6h/24h/72h), none overdue |
| Data quality | 0 fallback (synthetic) rows, 0 timestamp-rule violations, prices from Binance every hour |
| Live/research parity after the incident | 62 of 62 hours identical |
| **Shadow record (the research add-on added 2026-09-21 19:12)** | **8 of 19 hours missing** |
| Failed steps | only step 8, *"Shadow move-size probability"*; steps 1–7 (analysis, grading, self-check) succeeded in every single run |

So the hourly job was red while the thing it exists for — the live record — was healthy. The
red came from a research add-on deployed a few minutes earlier.

## Root cause

The Phase G "feature fingerprint" guard (commit `dbeaa45`, deployed 2026-09-21 ~19:0x) stored
a **sha256 of the model's feature values printed to 12 significant digits** and recomputed it
at `load_model()`. The intent was right: old coefficients must never run on changed feature
definitions. The implementation was too strict — it compared *bits*, not *meaning*.

GitHub's runners do not reproduce this machine's floating point exactly (different CPUs
vectorise reductions differently; the C math library differs between platforms). Measured
locally on the real reference series (900 values):

| relative difference | fingerprint changed |
|---|---|
| 1e-16, 1e-15 | 0% of 200 trials |
| **1e-14** | **56%** |
| 1e-13 and larger | 100% |

A difference of 1e-14 is a handful of last bits. So on about half of all runs the recomputed
hash differed, `load_model()` raised `ModelVersionError`, and the step exited 1.

### Evidence

1. **Where it died:** failing shadow steps took **0 s**; successful ones took **4–6 s**. The
   only work before the first network call is `load_model()` → the fingerprint check.
2. **When it started:** the first failure (19:31:46) is the third run after the guard was
   deployed; the step had never failed before.
3. **Intermittent on identical code and identical data:** the same commit `c9b45a6` both
   succeeded and failed, alternating, for 17 hours — inconsistent with a code, data,
   dependency or permissions problem, consistent with per-runner hardware differences.
4. **Not the suspected alternatives:** the pinned `requirements.txt` installed fine every time
   (step 4 green in all runs, including failing ones); `permissions: contents: read` never
   blocked anything; the database and secrets worked (steps 5–7 green); no Binance failure
   could return in 0 s (a network failure needs ≥ 15 s of timeout).
5. Reproduced locally: the shadow step succeeds 5/5 times on this machine — as expected, since
   the artefact's fingerprint was computed on this machine.

GitHub now requires sign-in to read Actions logs even on a public repository, so the exception
text itself could not be read directly; the case above rests on timing, sequence and a
quantitative reproduction of the mechanism. The fix also makes the runner record its own
errors, so any future failure states its reason in the database instead.

## What was affected

- **Live record: nothing.** Every hourly prediction, every outcome, every invariant intact.
- **Shadow record: 8 missing hours** (2026-09-21 19:00; 2026-09-22 01, 02, 04, 05, 07, 09, 11
  UTC). Hours where a later scheduled run happened to succeed were filled by that run.
- **No corrupted data anywhere**: the failure happened before anything was computed or written.

## Recovery decision: no backfill

The missing hours are **not** recreated. The shadow record exists to collect *prospective*
evidence — a probability stored before its outcome exists. Computing those hours now, with
their outcomes already known, would produce numbers that look identical but mean something
entirely different (`research/LIVE_EVALUATION.md`, rule 1). The gap is recorded, the hours
stay missing, and the after-the-fact paper record in the weekly report (§3b) already covers
that period, clearly labelled as after-the-fact.

While fixing this, a related gap was found and closed: the report evaluated *every* graded
shadow row, including any written late by a catch-up run. The prospective rule is now
enforced in code (`fetched_at < as_of + horizon + 1h`), and late rows are shown separately.

## The fix (commit `d222bd7`)

1. **The guard compares values with a tolerance** (`rtol = 1e-6`) instead of hashing digits.
   A changed definition moves a feature by orders of magnitude more than that; platform noise
   is ~1e-14. Regression test: noise from 1e-15 to 1e-9 must not trip it, a 1% change must.
2. **The artefact was regenerated** with the new guard metadata. Every model number and all
   training metadata were verified identical first, so `move_size_1h_v1` is still the same
   model and the prospective record is not split.
3. **A shadow failure is recorded, not crashed on**: new append-only table
   `shadow_run_errors` (stage, error type, message, commit, expected hour). The step exits 0
   once the failure is recorded, and 1 if it cannot be recorded (then it would be invisible).
   The live prediction is saved and self-checked *before* this step either way.
4. **A persistent shadow failure still alarms**: the 3-hourly watchdog now fails when more
   than 2 shadow errors are recorded in 6 hours — a blip is tolerated, a pattern is not.
5. **The weekly report** prints recorded shadow errors, by stage and type, with the latest one.

## Consequence for the readiness assessment

`docs/research/readiness_gate.md` was written hours before this incident and is **reopened**:
the item "failures detectable" was marked *Partial* (no external heartbeat) but should also
have noted that a research add-on could fail the live job; and the fingerprint guard, listed
under "model/version identification reliable", was itself the defect. Both are corrected in
this fix and the gate document now records the incident. The engineering conclusion stands
*after* this fix, not before it.

## Lessons recorded

- A guard on scientific *meaning* must not be implemented as a bit-exact comparison across
  machines. Tolerances belong wherever floating point crosses a machine boundary.
- A new component must not be able to fail the job that carries the primary record. Record
  its failure, alarm on persistence, and keep the primary path green.
- Alert fatigue is a real failure mode: an hourly red mail for a non-critical add-on trains
  the owner to ignore the alarm that matters.
- "Verified working" on one machine is not verification of a distributed job. The first
  GitHub-side run of a new step is part of the verification, and its *variability* across
  runners matters too.
