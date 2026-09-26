# Live evaluation protocol for the move-size model (Backend Phase H) — pre-registered 2026-09-21

**Object under test:** `move_size_1h_v1` (E012 inputs, E013 Platt calibration, frozen JSON
artefact), scored every hour by the shadow job (`agent/shadow`) into `shadow_move_size`.
**Question:** does P(next-hour move > 0.25%) keep meaning what it says on data that did not
exist when the model was fitted?

## Rules

1. **Prospective only.** A shadow row counts only if its probability was stored before its
   outcome candle closed (`fetched_at < as_of + horizon + 1h`, and the outcome written by the
   grading step later). The after-the-fact "paper record" of earlier live hours is reported
   separately and never merged into the prospective statistics.
   *Enforced in code since 2026-09-22* (`agent/research/weekly_report.py::shadow_record`): until
   then this rule was documented but not applied, and a row written by a late catch-up run
   would have been evaluated. Rows that fail the rule are listed as `not_prospective` and
   excluded from the evaluation.
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

## Clarifications registered 2026-09-23 ~20:00 UTC — before any checkpoint data exists (42 of 500 hours)

Rules 1–7 above are unchanged. These settle three things they left open, now, while no checkpoint
can yet be computed, so none of them can be chosen after seeing an answer. Implemented in
`agent/research/live_checkpoint.py` (`python -m agent.research.live_checkpoint`), tested in
`tests/test_live_checkpoint.py`.

8. **A checkpoint reads a fixed prefix.** The N-hour checkpoint uses exactly the first N prospective
   graded hours in time order — not however many exist on the day it is run. Reading "whenever it
   looks good" would be optional stopping; a fixed prefix is reproducible and cannot be picked.
   Later hours belong to the next checkpoint. The script refuses to compute a checkpoint early.
9. **The pass rules are E024's code.** `e013_passes` and the E012 bars are imported from
   `agent/research/checkpoint_power.py`, the study of these rules' own error rates, so the rule that
   is judged and the rule whose chance-failure rate was measured are one implementation. The rho part
   of E012 passes only with its interval (48 h blocks, **500 resamples** as rule 3 says, seed 17).
10. **The 5,000-hour regime cut points are frozen now:** `research/monitoring/regime_terciles_v1.json`
    — terciles of `rv_168` (realised volatility of the previous 168 h) on the development period,
    **0.004759 and 0.006966**. Built by the model's own feature code from candles loaded up to the
    holdout boundary (the holdout was not read), and written only after it reproduced the frozen drift
    reference's `rv_168` quartiles exactly (n = 64,206, identical). Never recomputed, never fitted to
    live data.

11. **An integrity precondition is reported with every checkpoint** (added 2026-09-26, 103 of 500 hours,
    before any checkpoint data): each judged probability is recomputed from that hour's stored raw inputs
    with the frozen artefact, and the reading states whether all of them reproduce (difference ≤ 1e-9)
    and all belong to that artefact. It changes no number and no rule; a failure is printed as an
    INTEGRITY WARNING at the top of the reading. First run over all 106 stored rows: max difference 5e-16.

## Operating characteristics of these rules (measured 2026-09-23, E024) — read every checkpoint against them

**No rule above is changed.** These are the rules' own error rates, measured before any checkpoint
data exists, so that a checkpoint result is read for what it is. Method: every contiguous N-hour
window of the validation out-of-sample record (a live record is a contiguous stretch with its own
regime), assuming the live model is exactly as good as it was on validation. If it is worse, passes
are rarer than shown.

| live hours | model ahead of the free EWMA rule | E012 passes (Brier / accuracy / rho point) | E013 ECE passes | E013 buckets pass | a *perfectly calibrated* forecaster passes E013 |
|---|---|---|---|---|---|
| 18 | 75% | 13% / 19% / 52% | 2% | 100% | 1% |
| 100 | 92% | 39% / 31% / 89% | 1% | 100% | 1% |
| 500 | 100% | 78% / 59% / 100% | 10% | 46% | 16% |
| 2,000 | 100% | 100% / 98% / 100% | 62% | 37% | 30% |
| 5,000 | 100% | 100% / 100% / 100% | 100% | 73% | 92% |

What that means for each checkpoint:

- **500 hours (first look, no verdict).** Expect ECE above 0.03 — a good model stays under it in only
  about 10% of 500-hour stretches, because ECE is inflated by sampling noise at that size. A high ECE
  here is not evidence of anything. Skill below the E012 bar also happens about one time in five.
- **2,000 hours (E012 verdict).** Sound: a model as good as on validation passes every part in about
  98% of stretches. A fail here means something.
- **5,000 hours (E013 verdict).** The ECE part is sound. The bucket part fails a perfectly calibrated
  forecaster 8% of the time from noise alone, and fails the real model in 27% of stretches, because
  its calibration moves with the market regime. So a fail means "worse than a one-in-four event for a
  model as good as on validation" — worth reporting, not proof of miscalibration — and the report
  must show the bucket-by-bucket numbers with intervals so the reader can see which case it is.
- **Short readings.** An 18-hour stretch shows the model behind the free rule one time in four even
  when it is genuinely better. That is what happened on 2026-09-22.

**The intervals themselves (E025, 2026-09-24, simulated — no rule changed).** Rule 3's 48-hour block
bootstrap was simulated under *no* effect: at **500 hours** (about ten blocks) its 95% interval excludes
zero about **9% of the time** instead of 5% (8.7% ± 1.8 on the 1h test, about 10% at 6h and 24h); at
**2,000 and 5,000 hours** it is at the nominal rate (4.3% ± 2.3 and 4.0% ± 3.1). So intervals shown
between 192 and ~2,000 hours are **optimistic** — the weekly report now says so next to them. The
checkpoints are unaffected: the 500-hour reading gives no verdict, and the verdicts sit at 2,000 and
5,000 hours, where the interval behaves.

## Context results from development data (recorded 2026-09-26, before any checkpoint): no rule changed

These are background for *reading* the checkpoints. None of them changes rules 1–11, a pass bar, the
selection rule or the order of the checkpoints. None used a prospective outcome.

- **E026:** the model family was calibrated within calm, normal and volatile regimes historically, except
  a narrow +0.021 over-statement in volatile markets on validation. A *persistent* live over-statement in a
  calm market would therefore be a genuine deviation, to be seen at the registered checkpoints, never tuned.
- **E027:** good overall calibration hides offsetting intraday miscalibration. Nights (00–06 UTC) are
  over-stated (+0.047 / +0.022) and the US session (12–18 UTC) is under-stated (−0.022 / −0.057). Its
  pre-registered consequence: the 2,000-hour hour-of-day and weekday/weekend slices (rule 5, descriptive,
  rule 7) are read against these development offsets, not against zero.
- **E028 (negative):** a second calendar harmonic does not remove that pattern. It is not the mechanism.
  Nothing adopted.
- **E029 (research-only; the detector is not used):** the family's calibration wanders in multi-week runs
  beyond ±0.025 about three to four times a year, in both directions. So a few weeks of live over- or
  under-statement is ordinary for this family. Only the registered 2,000 / 5,000-hour verdicts judge
  persistence.

## The 500-hour procedure in one place (a restatement of the rules above, not a new rule)

1. **When:** at the first working session after the prospective record holds 500 graded hours.
   `python -m agent.research.live_checkpoint` prints the count before then and writes nothing.
2. **Command:** `python -m agent.research.live_checkpoint`.
3. **Data:** exactly the first 500 prospective graded hours in time order (rules 1 and 8). Hours after the
   500th are never used for this reading, and the script cannot be pointed at another window. No holdout
   performance is computed, shown or used, and no research loader touches the holdout.
   *Stated precisely (found 2026-09-26 while checking this sentence):* the free 24h-EWMA reference downloads
   raw candles as warm-up (`ewma_reference_series`: 800 hours before the live start, plus the length of
   the record). At the 500-hour checkpoint that reaches back into roughly the last three to four weeks of
   the holdout period (to about 2026-07-26). The weekly reports have done the same since 2026-09-22, reaching into its last few
   days. Only the rule's values at the checkpoint's own live hours are used. There, those old candles
   carry a weight below 2e-10: a 24-hour half-life over the ≥ 780 hours between the holdout's end and the
   first shadow hour, with a quantity bounded by 0 and 1. It is left unchanged because it is registered
   checkpoint code and the effect is below any printed digit. Clipping the warm-up at the buffer's start
   would be a separate, dated decision.
4. **Rules:** unchanged. The E012/E013 bars come from `checkpoint_power.py` (rule 9), with intervals as
   rule 3 says. The integrity line comes first (clarification 11).
5. **Meaning:** a first look, **no verdict** (rule 5). It is read against E024's and E025's operating
   characteristics above. A computed checkpoint is never recomputed or rewritten.
6. **Afterwards:** the strict final readiness audit and a plain report of what is proven and what is
   uncertain (the user's instruction of 2026-09-25, `docs/ops/STATUS.md`). A good reading never hides
   another problem; a weak one is investigated, never tuned against. The weekly reports show the running
   record descriptively in between. They are not checkpoints, and nothing is decided on them (rule 2).

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

**Gap in the prospective record:** 8 hours are missing (2026-09-21 19:00; 2026-09-22 01, 02,
04, 05, 07, 09, 11 UTC) because the shadow step failed on about half of all runs until
2026-09-22 13:0x UTC (`docs/ops/incident_2026-09-21_shadow_step.md`). They are deliberately
**not** backfilled: a probability computed after its outcome exists is not prospective
evidence, whatever it looks like in the table. The hours simply do not count, and the
checkpoint thresholds (500 / 2,000 / 5,000 hours) count only rows that do.
