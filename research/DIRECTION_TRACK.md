# Prospective direction shadow track: registered protocol, version 1.1 (2026-10-15)

**Status: REGISTERED before any collection code exists.** Experiment E034. Master plan Phase 3 (5A and 5B). This file is
the whole test, fixed in advance. It changes only by a dated, versioned amendment written before the data it
affects exists, and never to rescue a result.

**Object under test:** `direction_1h_v1`, a frozen artefact holding E032's eight-input logistic and its two
references. It is scored every hour by its own job step, into its own table.

**Question:** does E032's faint 1-hour probability of an UP move keep beating a base rate on hours that did
not exist when it was fitted?

**What it is not.**
- It is not a signal. It never changes the BUY/HOLD/SELL decision, `move_size_1h_v1`, the move-size shadow
  record or any registered checkpoint.
- It is never combined with the move-size track.
- It never places or simulates an order anywhere outside this analysis. Its economics are arithmetic on
  stored prices.
- It is not declared successful because E032 found a small positive effect. E032 is hypothesis-generating
  (about 30 experiments had seen those periods), and only this prospective record can confirm it.

## 1. Target

- **y = 1 (UP)** if the close of the candle opening at `as_of + 1h` is above the reference close (the close
  of the candle that opened at `as_of`), else 0. A tie counts as not UP. This is E032's target, from
  `agent/research/labels`.
- 1 hour only. E011 found 6h and 24h at chance, and E025 showed longer overlapping targets need far more data.
- The return is also stored, so the economics (section 9) and the discrimination measure can use it.

## 2. Timing: when the prediction is stored, and when the outcome is known

- The reference candle opens at `as_of` and closes at `cutoff_at = as_of + 1h`. Nothing after `cutoff_at`
  may be used as an input.
- The job fetches the most recent 250 closed candles, with their trade count and taker-buy volume, in ONE
  Binance request after `cutoff_at`. The row stores `fetched_at`, which is at or after `cutoff_at`.
- **The outcome becomes known when the target candle closes, at `as_of + 2h`.** A later run grades it by
  timestamp, with the live outcome tracker's own rule (`target_candle_open`). A target candle that never
  appears is marked unavailable after the same grace period.
- **Prospective rule:** a row counts only if `fetched_at < as_of + 2h` and `created_at < as_of + 2h`, that is,
  stored before its outcome candle closed. Rows that fail it are listed as `not_prospective` and never
  evaluated.
- Missing hours are never backfilled. A recomputed probability would not be prospective.
- **The price at prediction time.** The same response also carries the still-open target candle. Its open
  time is checked to equal `cutoff_at`, and its current close, the last trade price at `fetched_at`, is stored
  as `price_at_prediction`. It is **never** a model input (a test enforces this). It exists only so the
  economics can use a price someone could actually have traded at, instead of the reference close, which
  had already passed when the prediction existed.

## 3. The frozen method

One JSON artefact, `agent/direction_shadow/models/direction_1h_v1.json`. It is exported once by a script,
committed, never edited, and its sha256 is pinned by a test. Inference is numpy only. It holds three
probabilities, all computed every hour on the same inputs.

| name | what | from |
|---|---|---|
| `p_model` (M) | L2 logistic, C = 0.1, standardised inputs, **no calibration layer** (E032's design; its validation calibration slope was 1.02) | E032's eight inputs: `trend_score`, `momentum_score`, `volume_score`, `chart_pattern_score`, `tr_mean_14_rel`, `trades_rel_168h`, `taker_buy_share_1h`, `taker_buy_share_6h` |
| `p_one_feature` (F) | the same logistic on `taker_buy_share_1h` alone, the simple taker-buy-share signal | E032's one-feature reference |
| `p_base` (B) | a constant: the share of UP hours in the fitting rows | E032's leak-free base rate, frozen |

- **Fitting data:** E032's rows (development only, `build_frame` → `load_bars(end=HOLDOUT.start)`), all of
  them up to `HOLDOUT.start − (1h + 24h)`, the same purge the move-size export used. No calibration slice.
  No holdout candle, no buffer hour, no live hour.
- **The inputs are computed by the research code itself:**
  - the four category scores by `agent.research.replay.analyze_window_detailed` on the 250 fetched candles.
    That is the function the historical replay used, and it calls the live scoring code (scoring 0.2.0);
  - the four microstructure and volatility inputs by `agent/shadow/features.feature_row`, the move-size
    shadow's own feature code.

  So live and research cannot drift apart silently.
- **Definition guards** (the lesson of 2026-09-21/22: a tolerance, never a bit-exact hash):
  - the artefact stores every input's values on a fixed synthetic candle series, the category scores
    included, and loading refuses to run if today's code produces different values (rtol 1e-6);
  - the artefact pins `scoring_version = 0.2.0`, and a row is stored `unavailable` if the scoring code
    reports another version.
- **Missing inputs:** if any input is missing (a gap inside a window, a zero-volume candle, an unavailable
  category), the row is stored `unavailable` with the reason and **no** probability. All three probabilities
  exist on exactly the same rows.
- **What each row keeps:**
  - the raw inputs, the three probabilities, the model version, the artefact sha256, the pipeline and scoring
    versions and the code commit;
  - `live_close_match`: the reference close against the live prediction's close for that hour, read-only;
  - `live_scores_match`: the four category scores against the live prediction's, read-only. It is a parity
    signal and it changes nothing;
  - `regime_rv_168`, the previous 168 hours' realised volatility. It is descriptive, never an input.

## 4. Storage and isolation (5B)

- **Its own tables:**
  - `shadow_direction`, one row per hour (`UNIQUE (as_of)`);
  - `shadow_direction_errors` for operational failures, append-only.
- **Immutable once written.** Only the outcome columns may be filled, exactly once, from NULL. Deletes are
  refused. Triggers enforce this, as on `shadow_move_size`.
- **Access:**
  - RLS on with no policy for the API roles, and every privilege of `anon` / `authenticated` revoked;
  - the job role `bitcoin_agent` gets INSERT and SELECT on both tables, and UPDATE on `shadow_direction`
    for grading (the trigger limits it to the outcome columns);
  - the security check, the role check (`docs/ops/least_privilege_role.sql`), `python -m agent.migrate` and
    the integration drift check all cover them.
- **It cannot cost the live record an hour.** Its step runs after the live prediction is saved and
  self-checked, and after the move-size shadow step:
  - a failure is recorded in `shadow_direction_errors` and the step exits 0;
  - only a failure to record the failure fails the step, because then it would be invisible.
- **It reads nothing the live decision writes,** except the two read-only cross-checks above. It writes
  nothing anywhere else.
- **Never:** a change to weights, inputs or probabilities because of outcomes it has collected; a refit; a
  threshold; a combination with move-size; any order.

## 5. What is evaluated, and how

- **Eligible rows:** `model_version = direction_1h_v1`, `status = ok`, prospective (section 2), and
  `outcome_status = ok`, in time order.
- **A reading uses a fixed prefix:** exactly the first N eligible rows, never "however many exist today".
  Later rows belong to the next reading. The code refuses to compute a reading early.
- **Every comparison uses identical rows,** since all three probabilities exist on every eligible row.
- **Uncertainty:**
  - every interval is a 95% circular block bootstrap with 48-hour blocks (hour-to-hour dependence, the
    method of every live evaluation here), 2,000 resamples, seed 33;
  - no adjective ("better", "calibrated") is attached to a number without its interval;
  - E025 and E033 found this interval liberal below about 3,000 hours, so every reading below that is
    labelled optimistic.

**Registered measures, at every reading:**

| kind | measure |
|---|---|
| probabilistic loss (primary) | Brier score of M, F and B; **the paired Brier differences B − M (primary), F − M and B − F**, each with its interval; Brier skill against B |
| probabilistic loss | log loss of each, and the paired log-loss differences |
| discrimination | AUC of M and F for y; Spearman ρ(p, the 1h return) for M and F, each with an interval |
| calibration | calibration-in-the-large (mean stated − observed UP share) with an interval; ECE; reliability buckets of width 0.02 over the range used, with Wilson intervals; the calibration intercept and slope with intervals |
| classification (descriptive) | accuracy at 0.5 against the majority share of the same rows |
| slices (descriptive) | by six-hour UTC block; by volatility regime (the frozen development terciles of `rv_168`, `research/monitoring/regime_terciles_v1.json`); week by week |
| integrity | every stored probability recomputed from its stored inputs; the stored inputs against a research recomputation from history candles; the prospective rule; the artefact sha256 |
| economics (descriptive, section 9) | gross and net returns of the registered rules at the registered costs |

## 6. Readings, and what each may conclude

Sized by E033 (`research/results/E033/`), which assumed the development effect, so these sizes are, if
anything, too small.

| eligible hours | reading | may conclude |
|---|---|---|
| **1,000** | first look | integrity only (reproducibility, parity, the prospective rule, coverage), plus every registered measure as points with optimistic intervals. **No verdict of any kind.** E033 power ≈ 0.2–0.3 |
| **3,000** | interim look | the same; **no verdict.** E033 power ≈ 0.56, and centred false positives up to 9% |
| **6,500** | **the verdict** | the criteria in section 7. E033: ≈ 80% power under the larger (validation) requirement, 6,421 h; simulated 0.95 at 6,000 h in both periods |

- **Expected dates,** at about 23.4 eligible hours a day from a start on about 2026-10-16: 1,000 hours ≈ late
  November 2026; 3,000 ≈ late February 2027; 6,500 ≈ late July 2027. A calm market could make even 6,500
  hours too few (E033: the calm-tercile gain in validation is about half the average). That would be read as
  "insufficient evidence", never answered by extending the count after looking.
- **By 2026-12-14 (the move-size 2,000-hour reading)** the track will hold about 1,380 hours. That is a first
  look only, and no directional conclusion is possible then.
- Each reading writes `research/monitoring/direction_checkpoint_<N>h.md/.json` once and never rewrites it.

## 7. Criteria at the 6,500-hour verdict (fixed now)

**Primary: M against the base rate.** D = Brier(B) − Brier(M) over the 6,500 hours, with its interval
[lo, hi].

| verdict | rule |
|---|---|
| **IMPROVEMENT** | lo > 0, AND the calibration guard holds: \|mean stated − observed UP share\| ≤ 0.03 and ECE ≤ 0.03 (E033: a development-like model fails this guard in under 5% of windows from 5,000 h) |
| **SKILL, BUT MISCALIBRATED** (not an improvement) | lo > 0 and the calibration guard fails |
| **NO IMPROVEMENT** | hi < 0.0005, so the interval excludes a gain half the development size (E032: 0.00094 / 0.00107). If hi < 0, it is also recorded as **worse than the base rate** |
| **INSUFFICIENT EVIDENCE** | anything else. E033: if there is no real effect, this is the most likely result at this size |

**Secondary, with the same rule and never in place of the primary:**
- **M against F**, "is it more than one feature?" (E032's H_b, prospectively). E033 found it needs 15,000 to
  188,000 hours, so **insufficient evidence is the expected result, stated now.**
- **F against B,** the one feature alone.

**Pre-decided consequences:**
- **IMPROVEMENT:** a faint, calibrated 1h directional probability holds on new data. That is still not
  usefulness (section 9). The next step, at most, is a written proposal to the user. It never makes an
  automatic change to anything, and it never combines with move-size until each component has credible
  prospective evidence.
- **NO IMPROVEMENT or worse:** close the directional track on free candle data, until genuinely new
  information exists (`research/DIRECTIONAL_ASSESSMENT_2026-10-14.md`).
- **SKILL, BUT MISCALIBRATED:** recorded. Any recalibration is a new registered experiment on development
  data and a new prospective record from zero.
- **INSUFFICIENT EVIDENCE:** recorded as exactly that. Collection may continue to one further pre-registered
  size only if that size is registered before the 6,500-hour reading is computed. Otherwise the track stops.
- **In every case,** the live BUY/HOLD/SELL signal, scoring 0.2.0, `move_size_1h_v1`, its shadow record, its
  checkpoints and the holdout are untouched.

## 8. Things that are never done with this record

- **No tuning, ever:** no refit, no new input, no threshold, no recalibration of `direction_1h_v1`. A
  replacement is a new experiment on development data, a new artefact version and a new record from zero.
- **No early stopping:** no reading before its size, no verdict at 1,000 or 3,000 hours, and no adding a look
  because one would be convenient.
- **No regime switching:** the slices are descriptive.
- **No holdout:** nothing in this track reads the sealed holdout (2025-07-01 → 2026-08-19), and
  `research/HOLDOUT_ACCESS.log` must not exist.

## 9. Economics: descriptive only, and never a criterion

**The question, asked plainly:** would acting on M have covered realistic costs? E032 says almost certainly
not. Its gross edge was 1–13% of a 0.10% round trip.

**Rules:**
- **long/flat, the primary description:** hold BTC for that hour if p_model > 0.5, otherwise hold nothing.
  This is possible on a spot account.
- **sign, reported for comparison only:** long if p > 0.5, short if p < 0.5. Shorting needs derivatives,
  whose funding costs are not modelled here.
- **The same two rules for F.**

**Prices:**
- each traded hour is one round trip, entered at `price_at_prediction` (section 2) and closed at the target
  candle's close;
- every traded hour pays the full round trip. Holding across consecutive hours is not credited, which is
  conservative;
- buy-and-hold over the same hours is shown alongside.

**Costs, one way:** fee + half-spread + slippage.
- **Standard:** 0.10% taker fee + 0.01% spread and slippage = **0.11%**, 0.22% a round trip.
- **Discounted:** 0.075% (taker with the exchange's fee-token discount) + 0.01% = **0.085%**.
- **Optimistic lower bound:** **0.02%**, below what a retail account pays.
- The fee figures are the exchange's published standard spot rates for regular accounts, as understood when
  this was written. They are re-checked at each reading and never changed to rescue a result. BTCUSDT's
  quoted spread is about one tick, so 0.01% is a generous allowance for spread plus slippage on a small order.

**Reported for each rule and cost:**
- the gross and net mean return per traded hour, with an interval;
- the number of traded hours;
- the gross return needed per trade to break even;
- the same over all hours against buy-and-hold.

**"Economically useful"** may be written only if three things hold at the 6,500-hour verdict: the primary
verdict is IMPROVEMENT, AND long/flat's net mean per traded hour at the **standard** cost has an interval
above zero, AND it beats buy-and-hold over the same hours. Otherwise the record says "not shown to be
economically useful", whatever the statistics say.

## 10. Implementation order (each step its own commit, tested, before collection starts)

1. This registration.
2. The artefact export, development data only, with its sha256 pinned.
3. The storage (schema, role, security check, migration), applied live and verified.
4. The hourly step and grading, isolated as section 4 says, with tests and mutation guards.
5. The reading code (`agent/research/direction_checkpoint.py`), written and tested on synthetic data before
   1,000 eligible hours exist. It reads no outcome early.

Collection starts with the first hourly run after step 4 is deployed and verified. The first eligible hour
is whatever that run stores. Nothing earlier exists, and nothing is backfilled.

## Amendments

An amendment is dated and versioned (1.1, 1.2, …), says which rows it affects, and is committed before those rows
exist. One that changes a criterion after any reading is computed is not allowed.

### Amendment 1.1 (2026-10-15, before any row exists): the readings are blind

**Affects:** every row, since none exists yet. It changes no criterion, size or measure. It only restricts what
may be looked at before each reading.

**Why:** the move-size 500-hour reading was not blind. Its running record had been reviewed in weekly reports and
an audit before it was computed (`research/DIAGNOSIS_2026-10-15.md`, row 4). That cannot be undone there, but it can
be avoided here from the first hour.

**The rule:** until each registered reading (1,000 / 3,000 / 6,500 eligible hours) is computed, every routine report
shows only **operational** figures for this track:
- rows written, status counts and unavailable reasons;
- coverage against the expected hours, and errors;
- prospective-rule violations;
- the integrity checks (recomputation from stored inputs, the artefact sha256, the live cross-check flags);
- graded and pending counts.

**Never an outcome-based figure:** no Brier score, accuracy, hit share, calibration, return, or comparison with the
base rate or the one feature. The weekly report, the reporting layer and ad hoc queries are all covered. A reading's
figures appear first in its own write-once file. Each reading is computed, and its figures first seen, at the first
session after its size is reached, exactly as registered.
