# Live evaluation protocol for the move-size model (Backend Phase H) — pre-registered 2026-09-21

**Object under test:** `move_size_1h_v1` (E012 inputs, E013 Platt calibration, frozen JSON
artefact), scored every hour by the shadow job (`agent/shadow`) into `shadow_move_size`.
**Question:** does P(next-hour move > 0.25%) keep meaning what it says on data that did not
exist when the model was fitted?

## Rules

1. **Prospective only.** A shadow row counts only if its probability was stored before its
   outcome candle closed (`fetched_at < as_of + 2h`, and the outcome written by the grading
   step later). The after-the-fact "paper record" of earlier live hours is reported separately
   and never merged into the prospective statistics.
2. **No tuning on the judging data.** Nothing about the artefact changes because of these
   numbers. If the model degrades, that is recorded; a replacement is a new experiment on
   development data, a new artefact version, and a new prospective record starting from zero.
3. **Uncertainty first.** Intervals are 95% circular block bootstrap (48-hour blocks, 500
   resamples), reported only once ≥ 192 prospective hours exist; before that, points are shown
   with "no intervals yet". No adjective ("reliable", "calibrated", "degraded") is attached to
   a number without its interval.
4. **Criteria are the ones already pre-registered**, copied unchanged:
   - E012 (skill): Brier ≥ 5% below the base-rate Brier of the same hours; large/small accuracy
     ≥ naive + 5 points; Spearman ρ(p, |move|) ≥ 0.10 with the interval excluding zero.
   - E013 (calibration): ECE ≤ 0.03 and every bucket with ≥ 100 rows within 0.05 of its
     observed frequency.
5. **Reporting checkpoints** (prospective hours): **500** (first look: skill + calibration
   points and intervals; no verdict), **2,000** (verdict on E012 criteria; calibration by
   bucket with intervals; by weekday/weekend and by hour-of-day block), **5,000** (≈ 7 months:
   verdict on E013 calibration; by month; by volatility regime of the previous 168h — low/mid/
   high terciles defined on the development period, not on live data; drift comparison
   against the development distributions).
6. **What a failure means.** Failing E012 at 2,000 hours or E013 at 5,000 hours demotes the
   deliverable to "uncalibrated heuristic" in every report until a new version passes on
   development data *and* prospectively. It does not trigger any change to the live signal.
7. **Regime slices are descriptive**, never the basis for switching models on the fly.

## What is checked every week regardless of sample size (weekly report §3)

Coverage (rows vs expected hours), honest blanks and their reasons, reference-close agreement
with the live prediction (`live_close_match`), outcome coverage, the current point values,
and the latest probabilities.

## Boundaries between data sets (kept clean)

| data | role | may influence the model? |
|---|---|---|
| 2017-08 → 2025-03-30 | fit | already used (frozen) |
| 2025-03-31 → 2025-06-29 | calibration slice | already used (frozen) |
| 2025-07-01 → 2026-08-19 | sealed holdout | **never**, until the one-time Phase 12 |
| 2026-08-20 → 2026-09-19 | contaminated buffer | no confirmatory use |
| 2026-09-19 → 2026-09-21 17:00 | live, before the shadow existed | after-the-fact paper record only |
| 2026-09-21 17:00 → | **prospective shadow record** | judges the model; never tunes it |
