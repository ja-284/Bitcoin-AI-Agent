# Backend readiness gate

> **Current score (2026-10-13, revision 3, the strict readiness audit after the 500-hour first look):
> 19 PASS, 3 PARTIAL, 0 FAIL, 0 UNKNOWN.** The three PARTIALs are row 8 (calibration: not yet confirmed
> prospectively, counted strictly from this revision), row 18 (observability: a single missed hour can
> still pass with no alarm) and row 21 (prospective monitoring: the calendar). Status: **RELEASE
> CANDIDATE, not FINAL.** Revision 3 is the first section below. The next paragraph is the previous
> score, kept as it was written.

> **Current score (unchanged since 2026-09-25, confirmed 2026-09-26): 21 PASS, 1 PARTIAL, 0 FAIL,
> 0 UNKNOWN.** The one PARTIAL is row 21, prospective monitoring, closed only by the calendar (the
> 500 / 2,000 / 5,000-hour checkpoints). Rows 16 (heartbeat) and 17 (least-privilege role) became PASS on
> 2026-09-25; see that section below. This file is a dated log. The revision-2 table and the older
> checklist further down show those two rows as open *as they were then*. **"Backend finished" is not
> claimed.** That waits for the registered checkpoints and the strict final readiness audit after the
> 500-hour reading.

*Assessed 2026-09-21; reopened and revised 2026-09-22 after an incident; **revision 2 the same evening**, scoring the master plan's 22 categories (jump to it below).*

> **Reopened after an incident.** Hours after this assessment was written, the hourly workflow
> began failing on roughly half of all runs for ~17 hours. The live record was never affected
> (18 of 18 predictions, parity 62/62), but the assessment below had two things wrong: it
> listed the feature-definition guard as evidence of good version control when that guard was
> itself the defect, and it did not notice that a research add-on could fail the job carrying
> the live record. Both are fixed (`docs/ops/incident_2026-09-21_shadow_step.md`,
> commit `d222bd7`); the affected rows are corrected below and dated. The engineering
> conclusion holds **after** that fix, not before it. Nothing about the research conclusions
> or the sealed holdout changed.

## Revision 3 — 2026-10-13: the strict readiness audit after the 500-hour first look

This is the audit that `research/LIVE_EVALUATION.md` (the 500-hour procedure, item 6) and
`docs/ops/STATUS.md` ("After it, in order", item 1) prescribe. It is added here; every other section of
this file is history and is left as written. Figures come from commands run on 2026-10-13 between about
19:30 and 19:50 UTC, unless a row names another date.

### The reading this audit follows

- `python -m agent.research.live_checkpoint` was run once, from 19:32:58 to 19:33:10 UTC. It wrote
  `research/monitoring/checkpoint_500h.md` and `.json`, which are committed unchanged (`ed96b2a`).
  Running it again prints "already computed" and changes nothing (checked: both files byte-identical).
- **Selection: exactly the first 500 graded prospective hours**, 2026-09-21 17:00 → 2026-10-12 21:00 UTC
  (520 were available). Checked independently: the span holds 509 hours, and the 9 left out are exactly
  the hours with no shadow row (2026-09-21 19:00; 09-22 01, 02, 04, 05, 07 and 09; 10-05 19:00;
  10-07 14:00). The large-move share (0.304) and the mean stated probability (0.3345) recompute to the
  values in the JSON.
- **Integrity: all 500 judged probabilities reproduce** from their stored inputs with the frozen artefact
  (largest difference 5.6e-16).

| measure | 500-hour value | registered bar | met at this size? | a model as good as on validation meets it (E024) |
|---|---|---|---|---|
| Brier gain vs these hours' base rate | +0.089 [+0.019, +0.137] | ≥ +0.050 (E012) | yes | 78% of 500-hour stretches |
| accuracy, large vs small move | 0.698 [0.656, 0.737]; "always small" scores 0.696 | ≥ 0.696 + 0.05 (E012) | **no** | 59% |
| Spearman ρ(probability, move size) | +0.324 [+0.143, +0.429] | ≥ 0.10, interval above 0 (E012) | yes | 100% |
| ECE | 0.059 [0.041, 0.093] | ≤ 0.03 (E013) | **no** | about 10% |
| buckets with n ≥ 100 within 0.05 | one bucket qualifies: stated 0.35, observed 0.34 (n = 155) | every qualifying bucket (E013) | yes, on a single bucket | 46% |
| against the free 24h-EWMA rule (E019) | Brier 0.1927 vs 0.2091, a difference of −0.0164 | a comparison, not a bar | the model is ahead | 100% |

**No verdict, by registration.** The E012 verdict comes at 2,000 hours and the E013 verdict at 5,000.

What the reading says, in plain words:

- **The probabilities rank hours well.** Hours the model called likelier to move did move more
  (ρ +0.32). By Brier it beats both the base rate and the free EWMA rule: skill +0.089 against the rule's
  +0.012. That points the same way as development, where it had 2.47 times the rule's skill.
- **As a yes/no call at 0.5, it is no better than "always small" in this calm market** (0.698 vs 0.696).
  This is the weakest figure in the reading. E024 makes missing this bar at 500 hours a roughly
  four-in-ten event for a model as good as on validation, so it is not evidence on its own. The
  2,000-hour verdict decides it.
- **Calibration is not confirmed.**
  - The model stated 0.335 on average, and large moves happened in 0.304 of these hours: about 0.03 too
    high overall.
  - By bucket, it over-states at 0.14 (observed 0.06), 0.45 (0.37) and 0.54 (0.44), and under-states at
    0.26 (0.34) and 0.63 (0.71).
  - An ECE of 0.059 is ordinary noise at this size (E024), and E029 found that this family's calibration
    wanders for weeks at a time three to four times a year.
  - This is the E026 watch item (possible over-statement in a calm market). It stays a watch item, not a
    finding. Only the 2,000- and 5,000-hour readings judge whether it persists, and nothing is tuned on it.

Limits on every figure above:

- **All 500 hours are in the low-volatility regime** of the frozen development terciles (`rv_168` at most
  0.00451, below the cut at 0.00476). The reading says nothing about normal or volatile markets.
- **It is not blind.** 400 of the 500 hours were reviewed in aggregate in the 2026-10-08 audit, and the
  weekly reports show the running record by design.
- **The intervals are optimistic at this size.** E025 measured about 9% false positives instead of 5%.
- **Both skill figures use the base rate of these very hours**, which knew in hindsight how calm the
  period was. The difference between the model's and the rule's Brier is the comparable part.

### The 22 categories, re-scored

| # | category | 2026-10-13 | evidence |
|---|---|---|---|
| 1 | Research correctness | **PASS** | E000–E029 pre-registered, with negative results kept. The 2026-10-08 formal audit found research integrity clean. Two of that audit's own claims were wrong (the experiment index, and the scope of the edge-interval defect); both were corrected with dated notes (§18), and the experiment log's completeness is now tested (`c6ad88a`) |
| 2 | Point-in-time safety | **PASS** | 0 timestamp-rule violations in 575 live hours; 0 of 2,605 outcomes graded before their candle closed; the checkpoint used prospective rows only (its rule is in code) |
| 3 | Validation | **PASS** | unchanged (E010). Validation wear (E022) still binds: validation results are hypothesis-generating only |
| 4 | Target/label correctness | **PASS** | unchanged; the outcome tracker and research labels agree in parity (571/571, weekly report 2026-10-13) |
| 5 | Feature quality | **PASS** | unchanged. Drift flags are descriptive: two inputs sit below the development 1st percentile in about 12% of live hours (2026-10-05). That limits coverage (row 22); it is not a defect |
| 6 | Feature redundancy | **PASS** | unchanged (E018, E022) |
| 7 | Model behaviour | **PASS** | the development evidence stands (E019, E020). Over the 500 prospective hours the model is ahead of the free EWMA rule (Brier −0.0164), as E024 expects in every 500-hour stretch |
| 8 | Calibration | **PARTIAL** (counted as PASS until now) | Validation ECE 0.014 (E013) stands. Prospectively: ECE 0.059, about 0.03 over-stated overall, five of seven buckets more than 0.05 from what happened. By E024 none of this is evidence against the model, but none of it confirms calibration either. **The row is counted PARTIAL from this revision because prospective evidence now exists and does not yet confirm the validation result.** That is a stricter count, not a newly found defect; under the old count the score would be 20 PASS, 2 PARTIAL. Only the 5,000-hour E013 verdict closes it |
| 9 | Live/research parity | **PASS** | 571/571 hours; shadow inputs 521 × 9 agree with research; the checkpoint's 500 probabilities all reproduce (5.6e-16) |
| 10 | Data quality | **PASS** | all 575 live hours from Binance, 0 synthetic; gaps flagged, never filled; 18 hours without news and 1 without an explanation, every one marked in its row |
| 11 | Failure recovery | **PASS** | unchanged. The 2026-10-05 runner outage and the 2026-09-29 AI provider error were both visible and left no wrong record |
| 12 | Idempotency | **PASS** | integration 36/36 on real Postgres, including the idempotency tests |
| 13 | Database integrity | **PASS** | integration drift check: the live database matches what the repository builds; append-only triggers; schema version 4 |
| 14 | Reproducibility | **PASS** | the checkpoint's integrity line (500 of 500 reproduce) and parity 571/571 |
| 15 | Versioning | **PASS** | every shadow row is `move_size_1h_v1` (521 rows, one version); no version has changed since 2026-09-22; `tests/test_status_docs.py` keeps the docs and the code's versions in agreement |
| 16 | Automation | **PASS, with a stated limit** | 562 of 564 hours recorded since the trigger fix (from the 2026-09-20 07:00 hour). The two losses, 2026-10-05 19:00 and 2026-10-07 14:00, came when GitHub started no run at all, backup slots included. 177/177 GitHub runs succeeded since 2026-10-11 18:00. The heartbeat sits outside GitHub. A lost hour is recorded as missing, never backfilled |
| 17 | Security | **PASS** | security check OK (only the three reporting tables are reachable, viewer only); role check OK (`bitcoin_agent` with exactly its proven rights; 121 of 121 hours since 2026-10-08 18:00 written by it); dependency audit: 0 known vulnerabilities in 43 packages |
| 18 | Observability | **PARTIAL** (was PASS) | (a) A single missed hour can pass with no alarm at all: on 2026-10-07 the heartbeat pings were 87 min apart against a 90-min allowance, and the self-check, by design, fails only a run whose own hour was not saved. (b) Why a dispatch failed cannot be found out after about 6 h, because `pg_net` drops GitHub's answer; the 2026-10-07 cause is therefore unknown. (c) Two weekly-report defects went unseen for days: the 7-day health line read "0 of 167" from 2026-09-26 to 10-08 (fixed, `c05ee3c`), and the edge interval was erased in five reports (fixed, `4ec90ea`). Nothing in the record was lost or wrong, and a missed hour does show afterwards (weekly report, `backend_state`, stats incident history). (a) and (b) are the first two operational changes the user approved for after this audit |
| 19 | Performance | **PASS** | analysis median 25.3 s, longest 34.6 s (last 7 days); database 28 MB of 500 MB |
| 20 | Maintainability | **PASS** | 561 unit tests with no database reachable, 36 integration tests, 79/79 mutation guards with both controls held (2026-10-11 at `3ae0265`; no code has changed since) |
| 21 | Prospective monitoring | **PARTIAL, by the calendar** | The 500-hour first look is done. 520 of 2,000 graded hours. The E012 verdict is due ≈ 2026-12-14 if no hour is lost (each lost hour adds one; 2 were lost since 2026-09-20). The E013 verdict comes at 5,000 hours (≈ spring 2027) |
| 22 | Known limitations | **PASS** | documented, now including this reading's own: low volatility only, not blind, optimistic intervals. Holdout-period candles were used as inputs: the holdout is sealed for evaluation, not untouched (`research/AUDIT_2026-10-08.md` §18.2) |

**Score: 19 PASS, 3 PARTIAL, 0 FAIL, 0 UNKNOWN** (rows 8, 18 and 21).

### Hard gates, re-checked

| hard gate | status | evidence, 2026-10-13 |
|---|---|---|
| correctness | PASS | rows 1, 4, 9 |
| point-in-time safety / leakage | PASS | row 2; the checkpoint read prospective rows only |
| data integrity | PASS | row 13 |
| critical security | PASS | row 17 |
| reproducibility | PASS | row 14 |
| required tests | PASS | 561 unit, 36 integration, 79 mutation guards; GitHub's test workflow green |
| live/research consistency | PASS | parity 571/571 |
| no known critical regression | PASS | the last code changes were `4ec90ea` and `c6ad88a` (2026-10-09); every commit since adds documents or checkpoint files only |

### Release status, 2026-10-13: RELEASE CANDIDATE, not FINAL

Every hard gate passes and nothing critical is open. It is **not FINAL** because three PARTIALs remain,
and because the one deliverable that might work, the calibrated move-size probability, has a first look
and no verdict. **"Backend finished" is not claimed.** The one engineering gap (row 18) is known, and its
fix is first in the user's queue.

### Is the backend ready for a frontend?

**Yes, for a read-only display that shows the research state truthfully.** Contract v1 and the private
stats read model already label every number. A frontend must show three things as they are:

- the BUY/HOLD/SELL signal has **no demonstrated predictive value** (still true: at 1h it matched 0.500
  of 348 graded hours against a 0.509 baseline, weekly report 2026-10-13);
- the move-size probability is calibrated on development data. Live it has a first look at 500 hours,
  with no verdict, in calm markets only;
- confidence is a labelled heuristic, not a probability.

**No, for anything else:** presenting the move-size probability as validated live, presenting the signal
as advice, or writing anything back.

### Holdout readiness, 2026-10-13: still NOT READY

- **Prospective monitoring:** the 500-hour first look now exists. E024 places the first sound verdict at
  2,000 hours, so the protocol's own logic still points to waiting.
- **A precondition recorded 2026-10-11:** the E000 backtest runner fetches candles directly, so it is not
  covered by the `load_bars` holdout guard. That must be fixed before any E014 or E023 run.
- **Its state, stated exactly:** sealed for evaluation (no holdout score has been computed or used, and
  `research/HOLDOUT_ACCESS.log` does not exist), but not untouched. Raw candles from its last weeks were
  fetched as warm-up inputs, and the 2026-09-19 snapshot stores the whole period (`research/AUDIT_2026-10-08.md`
  §18.2). Opening it remains the user's explicit decision.

### What is proven, and what is not

**Proven, for the system as a measuring instrument:**
- it ran unattended for 24 days with 11 documented hours missing (9 before the trigger fix), none
  backfilled, and nothing fabricated;
- every row is timestamped honestly, append-only, and reproducible from its stored inputs;
- the 500-hour reading used exactly the registered rows, and every judged probability reproduces;
- it has been secure since 2026-09-25 (least privilege; nothing reachable from outside except the
  viewer-only reporting tables).

**Not proven:**
- that the move-size probability is calibrated live (a first look shows about 0.03 over-statement in a
  calm market; the verdict comes at 5,000 hours);
- that it beats "always small" as a yes/no call (0.698 vs 0.696; decided at 2,000 hours);
- anything about normal or volatile markets: none of the 500 hours was in either;
- any value in the BUY/HOLD/SELL signal: none has been demonstrated.

### Next, in the order the user set on 2026-10-11

1. The single-missed-hour alarm (row 18a).
2. Keeping GitHub's answers to the dispatch (row 18b).
3. A separate review of news cost and value, with no change to the live weights or the model.

They come one at a time, each with tests and its own commit. Meanwhile the frozen model continues
untouched to the 2,000-hour reading. The registered news first look (descriptive) has enough hours
(553 usable, weekly report 2026-10-13), and it waits for the user's go-ahead.

## Revision 2 — 2026-09-22 evening: the 22 categories of the master plan, scored

The master plan (section 50) names 22 categories and requires each to be marked **PASS**,
**PARTIAL**, **FAIL** or **UNKNOWN**, with no PARTIAL or UNKNOWN hidden behind a general
"ready". Here they are. The detailed evidence for most rows is in the sections further down;
rows changed by the work of 2026-09-22 say so.

| # | category | status | why |
|---|---|---|---|
| 1 | Research correctness | **PASS** | E000–E020: every experiment pre-registered with a falsifiable criterion, negative results recorded and kept (E001, E011, E015, E017, E020), methodology changes documented before acting |
| 2 | Point-in-time safety | **PASS** | cutoff enforced by CHECK constraints; news limited to the cutoff; perturbation tests (garble the future, the past must not move) in `test_point_in_time.py`, `test_features_point_in_time.py` and now `test_simple_baselines.py`; 0 timestamp violations in 72 live rows |
| 3 | Validation | **PASS** | E010 verified the walk-forward bench against 5 pre-registered checks on real data; purge = horizon plus a 24h embargo on both sides of any fitted slice |
| 4 | Target/label correctness | **PASS** | `test_labels.py`, `test_horizon_lookup.py`; the live outcome tracker equals the research label rule across a data gap (`test_parity.py`, 46/46 hours to 1e-16) |
| 5 | Feature quality | **PASS** | 55 candidate features tested fit-free across eight groups; each judged by a pre-registered rank-correlation bar in two separate periods; nothing adopted on a single period |
| 6 | Feature redundancy | **PASS (new, 2026-09-22)** | **Was UNKNOWN until today.** E018 measured it: one of the nine model inputs is exactly arithmetic (`vol_ratio_24_168` = `rv_24` − `rv_168`, 1.0e-15 over 51,053 hours), and six inputs carry 99.4% of the model's skill |
| 7 | Model behaviour | **PASS (new, 2026-09-22)** | E019: the model beats the best non-fitted rule by 2.47× on validation, and still by 2.33× after that rule is given the same calibration. E020: gradient-boosted trees and an interaction model were tried once with fixed settings and did not clear the bars. The complexity is defended, not assumed |
| 8 | Calibration | **PASS on validation, PARTIAL prospectively** | E013: Platt chosen by a pre-registered rule, validation ECE 0.014, ≤ 0.03 every year. Prospectively it is 18 hours old — the first checkpoint is at 500 |
| 9 | Live/research parity | **PASS** | `agent/research/parity.py`: every live hour re-analysed from candles and committed code; 64/64 identical at the last weekly audit |
| 10 | Data quality | **PASS** | candle validation (impossible data raises, gaps flagged and never filled), schema checks, staleness rule, fallback flagged per row; 0 synthetic rows live |
| 11 | Failure recovery | **PASS** | `test_failure_modes.py`, `test_data_hardening.py`, `test_llm_robustness.py`; `docs/research/failure_modes.md`; proven in production by the 2026-09-21/22 incident, where the failure was loud and the live record untouched |
| 12 | Idempotency | **PASS** | early exit before the AI call; `ON CONFLICT DO NOTHING` throughout; proven against real Postgres in a scratch schema (`tests/integration`, 8/8) |
| 13 | Database integrity | **PASS** | UNIQUE keys, CHECK constraints for the cutoff and fetch rules, append-only triggers on all four tables, schema version pinned to the code |
| 14 | Reproducibility | **PASS** | `docs/research/reproducibility.md`; and today, unplanned but strong: E018's nine-feature run reproduced E013 **to the digit** from an independently written evaluation path |
| 15 | Versioning | **PASS after a correction** | golden scoring pin, feature reference values, artefact hash, schema version, git SHA per row. The 2026-09-21 feature guard was bit-exact across machines and broke the live shadow job; it now compares with a tolerance, with regression tests in both directions |
| 16 | Automation | **PARTIAL** | Supabase `pg_cron` dispatch at :12 plus GitHub's own slots as backup; self-check, 3-hourly watchdog, tests on every push; 0 missing hours in the last 48. **The external heartbeat alarm is still not set up** — every alarm currently lives inside GitHub, so GitHub going quiet looks like success. User action, five minutes: `docs/ops/open_user_actions.md` |
| 17 | Security | **PARTIAL** | secrets absent from git and logs (scanned), workflow permissions `contents: read`, pinned requirements, no execution code anywhere. **The job still connects as the project's `postgres` role**; the exact grants a restricted role needs are written out in `docs/ops/open_user_actions.md`. Mitigated by append-only triggers |
| 18 | Observability | **PASS** | every degradation lands in `run_meta`; shadow failures recorded in their own table and alarmed only when persistent; weekly report with health, record, parity and drift; and now `agent/api/state.py`, which reports health and problems in words |
| 19 | Performance | **PASS** | `docs/ops/performance.md`; a full hourly run takes about 40 seconds, dominated by two AI calls; no bottleneck worth optimising |
| 20 | Maintainability | **PASS** | narrow, swappable modules; README module map; 266 tests, each guard with a test that fails when the guard is removed |
| 21 | Prospective monitoring | **PARTIAL — by the calendar, not by a defect** | the shadow record is running correctly and is 18 hours old; the checkpoints are 500 / 2,000 / 5,000 hours. Nothing can make this PASS faster than time passes |
| 22 | Known limitations | **PASS** | documented in the README, the data-source and failure-mode docs, every experiment summary — and now machine-readable in contract v1, so a frontend receives them rather than having to look them up |

**Score: 19 PASS, 3 PARTIAL, 0 FAIL, 0 UNKNOWN.** The three PARTIALs are the heartbeat (yours,
five minutes), the database role (yours, ten minutes) and the prospective record (nobody's —
it needs 500 hours of elapsed time).

### Addendum, later the same evening

Three rows strengthened after revision 2 was written, and are recorded here rather than edited
into the table above, so the sequence stays readable:

- **11 Failure recovery** — the last scenario from the master plan's list that had no test now
  has one: a database on an older schema stops the run before anything is written
  (`assert_schema_current`). Version 3 is what added the CHECK constraints and append-only
  triggers, so an older database would have accepted rows this project believes are impossible.
- **18 Observability** — every failure handler in the live path was read against one standard and
  tabulated (`docs/ops/observability.md`). One invisible failure was found and fixed: a *partial*
  news failure produced a number indistinguishable from a healthy hour.
- **20 Maintainability** — the suite is now provably free of hidden database dependencies: CI runs
  it with an unreachable `DATABASE_URL`, after the schema guard revealed five tests that had
  quietly started needing one and still passed locally.

**Feature redundancy (6) and model behaviour (7) also gained E022 and E021** as evidence, though
both were already PASS.

The score is unchanged at **19 PASS, 3 PARTIAL, 0 FAIL, 0 UNKNOWN**, and so is the judgement.

### CORRECTION, 2026-09-23 — row 17 (Security) was wrong: it should have been FAIL

Row 17 above scored Security **PARTIAL**, naming only the least-privilege database role as a gap.
That was wrong, and it is left unedited above so the sequence stays honest. On 2026-09-23 Supabase's
own security advisor flagged what the audit behind this row had never checked: **every table in the
database was readable and writable through Supabase's public API** (Row Level Security off, full
privileges for the `anon` role that any holder of the public anon key acts as). The 2026-09-21 audit
looked at secrets, logs, workflow permissions and the trading boundary, and not at what the database
itself exposes. That is a critical item, and a critical item is a FAIL whatever the other rows say.

The exposure is now closed and verified (`docs/ops/security_2026-09-23_public_api_exposure.md`):
two independent layers on every table, 48 of 48 anonymous probes refused, each layer proven on its
own against real Postgres, schema version 4, and a detector the watchdog runs every three hours. No
sign in the data of any outside write; whether anything was *read* can only be answered from
Supabase's API logs.

**Row 17 now: PARTIAL again — for honest reasons.** The critical exposure is closed. Still open:
the least-privilege database role (user action, and — found while fixing this — it now also needs
the hourly job to stop re-applying schema DDL, since only a table's owner can); and the API-log
check for past reads (user, dashboard only).

**Revised score: 19 PASS, 3 PARTIAL, 0 FAIL, 0 UNKNOWN** — the same numbers as before, reached for
a different and truer reason. Between 2026-09-21 and 2026-09-23 the real score was 18 PASS,
3 PARTIAL, **1 FAIL**, and the gate did not know it. The lesson recorded for every future audit:
**check what a service exposes by default, not only what this code does** — a platform's defaults
are part of the attack surface even when the code never touches them.

### Release status, 2026-09-23 — RELEASE CANDIDATE, not FINAL

The master-plan addendum separates these on purpose, and so does this gate.

**Hard gates** (must all be PASS before "backend complete" may be said):

| hard gate | status | evidence |
|---|---|---|
| correctness | PASS | rows 1, 4, 9; parity every week |
| point-in-time safety / leakage | PASS | rows 2, 3; perturbation tests in every feature and label module |
| data integrity | PASS | row 13; append-only triggers; and since 2026-09-23 no public-API writes are possible |
| critical security | PASS | the public-API exposure is closed and proven by behaviour; detected every 3 h |
| reproducibility | PASS | row 14; and since 2026-09-23 one command (`python -m agent.migrate`) builds the whole schema |
| required tests | PASS | 334 unit tests with no database reachable, 11 integration tests on real Postgres, CI on GitHub's runners |
| live/research consistency | PASS | parity 64/64 at the last weekly audit |
| no known critical regression | PASS | every change today verified before the next was pushed |

**Every PARTIAL, classified (addendum §8):**

| item | critical? | fixable now? | why it is not PASS |
|---|---|---|---|
| **16 Automation** — no alarm outside GitHub | not critical to integrity (a missed hour is recorded as missed, never fabricated) but it is the one silent failure left | no — needs a healthchecks.io account (user) | if GitHub stops running jobs entirely, nothing reports it |
| **17 Security** — least-privilege DB role | not critical (defence in depth; the secret is not exposed, the record is append-only, the public API is closed) | not by me — creating a login role with a password is an account-creation step (user); its prerequisite, no DDL on the hourly path, is done (verified in a scheduled run 2026-09-23 15:09 UTC) | the job still connects as the owner role |
| **17 Security** — was the exposure used to READ data? | not critical to integrity (no write occurred; the data is non-secret research output of a public project) | **partly answered 2026-09-23 ~18:20 UTC (user):** API Gateway logs searched for `rest/v1` over the last 24 hours, the most the Free plan keeps — **no results**; `graphql` searched too, nothing reported — so no API reads in the last ~19 hours of the exposure (≈ 2026-09-22 18:00 → 2026-09-23 13:45 UTC) | the earlier days (2026-09-19 → 2026-09-22 ~18:00) had already left the 1-day log and stay **UNKNOWN permanently** |
| **21 Prospective monitoring** | not critical to the engineering; **critical to any claim that the move-size model works** | no — it needs elapsed time (37 of 500 shadow hours on 2026-09-23) | the calendar |

**Verdict: RELEASE CANDIDATE.** Every hard gate passes; nothing critical is open. It is **not
FINAL** because three PARTIALs remain and one fact is UNKNOWN, none of which can be closed from the
repository. A frontend can be built against it now; "backend complete" is not claimed, and a model
that "works" is not claimed either.

### Evening security review, 2026-09-23 — root cause closed; one more fact is UNKNOWN

Re-opened on the user's instruction to resolve the public-access issue properly (full record:
`docs/ops/security_2026-09-23_public_api_exposure.md` → "Evening review").

- **Closed:** the *root cause*. Supabase's default privileges granted every NEW table, view, sequence
  and function in `public` to the public API roles (24 standing grants); the morning's fix had locked
  only the tables that existed. Removed by the schema files, applied live (24 → 0), proven on live in
  a rolled-back transaction and on real Postgres with a control; the drift check now compares default
  privileges and failed before the migration, passes after.
- **Widened:** the detector now also reports views readable by the API (views ignore RLS), functions
  callable at `/rest/v1/rpc`, and standing default grants — each check broken on purpose and caught
  (mutation testing 31 of 31).
- **Not closable by this project:** Supabase's admin role grants the API roles full rights on `net`
  (which holds each hourly dispatch request, GitHub token included, for seconds), on
  `extensions.pg_stat_statements` and on `realtime.subscription`. Revoking was tried and refused by
  Postgres. They are reachable only if listed under *Exposed schemas* (default: not). **That setting
  is a second UNKNOWN fact** — a user check of ten seconds, and now the single control over `net`.
- Checked and fine: no secret in 2,081 stored query texts (the one token-shaped match is the setup
  script's placeholder, and differs from the Vault token); no Realtime publication; no storage bucket;
  `cron`/`vault` not enterable by the API roles; no Auth users.

**Row 17 stays PARTIAL** (least-privilege role: user step). **Hard gate "critical security": PASS,
with a stated condition** — it rests on Supabase's default exposed-schemas list, which is unverified
until the user looks. Everything the project's own role can close is closed and watched.
**Update 2026-09-24 ~17:50 UTC: the condition is met.** The user checked the dashboard: *Exposed
schemas* lists only `public` and `graphql_public`. "Critical security" is now PASS without a
condition; the only open security item is the least-privilege role (defence in depth, row 17).

### 2026-09-25 — row 17 Security: PARTIAL → **PASS**; row 16 Automation: heartbeat set up

- **Row 17:** the hourly job and the watchdog now connect as `bitcoin_agent`, which holds exactly what
  `docs/ops/least_privilege_role.sql` grants (`role_check` OK). Verified by behaviour on the 19:12 UTC
  run: the prediction is stamped `db_role = bitcoin_agent`, and an outcome insert, a shadow grading, a
  shadow insert and the snapshot publish all succeeded; every step green. A leaked `DATABASE_URL` is now
  bounded to reading and appending the record. The one residue, stated plainly: Supabase grants the
  `net` queue to PUBLIC (unrevocable by the project), kept off the internet by *Exposed schemas*.
- **Row 16:** the heartbeat secret is set and the 19:12 run's ping step ran. It moves to PASS once the
  first ping is seen on healthchecks.io itself (the step cannot prove delivery: it is
  `continue-on-error` by design). **→ PASS, same evening:** the user confirmed the check is green on
  healthchecks.io with the 19:13 UTC ping received. Every alarm no longer lives inside GitHub.
- **Score now: 21 PASS, 1 PARTIAL, 0 FAIL, 0 UNKNOWN.** The one PARTIAL is row 21, prospective monitoring —
  by the calendar, not a defect. "Backend complete" is still not claimed: that waits for the registered
  checkpoints and a strict final audit, and a good checkpoint may not be used to hide any other problem.
- Still open, by the calendar only: **row 21, prospective monitoring** (≈ 90 of 500 hours).

### The three PARTIALs, 2026-09-23 ~20:00 UTC — what moved, what cannot move without the user

| row | status | what was done this evening | what still stands between it and PASS |
|---|---|---|---|
| 16 Automation | **PARTIAL** | heartbeat steps hardened (a ping hiccup cannot turn a good hour red; a failed run signals `/fail` at once), pinned by tests and a mutation; the watchdog's real cadence measured (3 of 8 slots ran in a day) | the user's heartbeat account and secret — attempted today, did not work, deferred by the user |
| 17 Security | **PARTIAL** | root cause closed live; detector covers views, functions, default grants; the least-privilege role made *verifiable* (`python -m agent.database.role_check` against the proven file) and every prediction now records the role that wrote it (`run_meta.db_role`) | the user creates the login role (a password) and switches the secret — ~10 min, steps in `open_user_actions.md`; plus the 10-second *Exposed schemas* check |
| 21 Prospective monitoring | **PARTIAL — the calendar** | nothing can be done but wait; the shadow record runs every hour with 0 errors | 42 graded prospective hours of 500 (counted from the database at 19:55 UTC); the first checkpoint is about three weeks away |

Tests: 395 unit (no database reachable), 19 integration on real Postgres, mutation testing 34 of 34.
**Still RELEASE CANDIDATE, not FINAL** — and none of the three remaining gaps can be closed from the
repository.

## Holdout readiness review, 2026-09-23 — NOT READY (one condition unmet), and never opened without the user

The master plan (section 51) lists what must be true before unsealing is even worth proposing. Each
condition, checked:

| condition | status | evidence |
|---|---|---|
| major development complete | **met** | backend is a release candidate (above); no open engineering change affects what the holdout tests |
| major architecture decisions complete | **met** | the model family (E020), target definition (E021) and feature set (E018) were all tested and stand as they are |
| calibration method fixed | **met** | Platt on a purged 90-day slice (E013), unchanged since |
| the version under test explicitly frozen | **met, after a correction today** | E014 still named scoring 0.1.0 while the live signal is 0.2.0 — amended while sealed; the script now refuses to run on an unregistered version. Objects C and D are the *procedure* (walk-forward, refit each holdout quarter, as a deployment would), not the frozen artefact `move_size_1h_v1`, which is tested prospectively instead — both by design |
| final evaluation code audited | **met** | dry run on validation reproduces the 2026-09-21 dry run for every object (only the random-mix baseline moves, explained); the E023 extension is dry-run too; one guarded route into the holdout, pinned by tests; the evaluation's own pass logic is mutation-tested |
| no important known leakage | **met** | point-in-time perturbation tests across features, labels, news and replay; 28 of 28 guard mutations caught in one pass with both controls (tools/guard_mutations.py, 2026-09-23) — after round two found and closed two real gaps, one of them a possible future leak in the historical replay |
| **meaningful prospective monitoring has occurred** | **NOT MET** | 37 prospective shadow hours of the 500 the protocol's first look needs; E024 shows the E012 verdict only becomes reliable near 2,000 hours. Opening the holdout before the live record has anything to say would spend the only clean arbiter while the other line of evidence is still silent |

**Verdict: not ready.** Everything that can be prepared is prepared; what is missing is time. The
earliest sensible moment to *propose* unsealing is after the 500-hour first look (about 19 days of
shadow hours from 2026-09-23), and the protocol's own logic points closer to the 2,000-hour E012
verdict. Either way the decision is the user's, explicitly, and the holdout stays sealed until then.
`research/HOLDOUT_ACCESS.log` does not exist.

### What this does and does not say

It says the backend is **trustworthy as an instrument**: what it records is correct, timestamped
honestly, reproducible, versioned, hard to corrupt, and it fails loudly.

It does **not** say the system predicts the market. The BUY/HOLD/SELL signal still has no
demonstrated predictive value at any horizon (E001, E017). The one thing that does work is the
calibrated *uncertainty* estimate — how big the next hour's move is likely to be, not which way —
and its out-of-sample evidence is validation-period only until the prospective record grows.

"Backend finished" is therefore **not** claimed. The honest statement is: **ready to be built
against, not finished.**


The strict checklist from the master operating prompt, item by item, with the evidence and
an honest status. **Verified** = checked and proven today; **Partial** = in place but
waiting on something outside the code; **Not yet** = not satisfied.

"Backend ready for frontend" means: reliable, research-valid, observable, reproducible,
secure and stable enough that a frontend can be built on it without treating it as a
prototype. It does **not** mean the system predicts the market.

## Research correctness

| item | status | evidence |
|---|---|---|
| point-in-time behaviour verified | **Verified** | `test_point_in_time.py`, `test_features_point_in_time.py` (future garbled → past unchanged), `test_news_cutoff.py`, `test_orchestrator_cutoff.py`; live: 0 timestamp-rule violations in 48 rows; CHECK constraints in the database |
| leakage protections tested | **Verified** | walk-forward purge/embargo demonstrated on an overlapping-label leak (`test_walkforward.py`); E010 controls (memoriser at chance, last-label no head start); feature-name tripwire (`test_feature_harness_guards.py`); holdout loader guard (`test_research_guards.py`) |
| target construction verified | **Verified** | `test_labels.py`, `test_horizon_lookup.py`; tracker = labels across a gap (`test_parity.py`); live tracker returns = research candles (46/46) |
| validation framework verified | **Verified** | Phase 6 / E010: 5 of 5 pre-registered checks on real data |
| calibration process verified | **Verified** | E013 (Platt chosen by rule; ECE ≤ 0.03 every year); `test_calibration.py` (calibrator sees only the purged slice) |
| final holdout protected | **Verified** | `research/HOLDOUT_ACCESS.log` does not exist; loader truncates; `build_frame` takes holdout candles only through the logged route; E014 pre-registered, not run |
| experiment history complete | **Verified** | E000–E014 in `research/EXPERIMENTS.md` + JSON each; results committed; per-hour dumps regenerable |

## Engineering correctness

| item | status | evidence |
|---|---|---|
| live/research parity checked | **Verified** | `agent/research/parity.py`: 44/44 live hours identical; `docs/research/parity.md`; weekly §4 |
| data validation strong | **Verified** | candle validation (impossible data raises, gaps flagged, zero volume counted), kline schema checks, staleness rule, bounded RSS/AI/DB calls (Phase B) |
| failure handling tested | **Verified** | `test_failure_modes.py`, `test_data_hardening.py`, `test_llm_robustness.py`, `test_market_data_fallback.py`; `docs/research/failure_modes.md` |
| retries safe | **Verified** | one retry per exchange endpoint (none on rate limits), SDK retries bounded, no DB retry (next slot recomputes; idempotent writes) |
| duplicate execution safe | **Verified** | early exit before AI; `ON CONFLICT DO NOTHING` everywhere; proven on real Postgres in a scratch schema (`tests/integration`, 7/7) |
| database integrity checked | **Verified** | UNIQUE keys, CHECKs (cutoff rule, fetch-after-cutoff, outcome status/consistency), append-only triggers, schema version — applied live |
| important code paths covered by meaningful tests | **Verified** | 185 unit tests + 7 integration; every guard has a test that fails when the guard is removed (perturbation tests in parity, golden scoring pin, artefact hash, fingerprint) |
| reproducibility demonstrated | **Verified** | `docs/research/reproducibility.md`: parity 44/44, shadow rows 1e-12, E012 re-run bit-identical; requirements now pinned exactly |

## Operational reliability

| item | status | evidence |
|---|---|---|
| hourly execution monitored | **Verified** | self-check step, 3-hourly watchdog, weekly report §1; 100% of hours since the trigger fix |
| failures detectable | **Partial** (revised 2026-09-22) | job failures email via GitHub; missed hours fail the next job; weekly report lists them. **Corrected after the incident:** a research add-on could turn the hourly job red every hour while the live record was healthy — alert fatigue, and it hid which failures mattered. Shadow failures are now recorded in `shadow_run_errors`, printed in the weekly report, and alarmed by the watchdog only when they persist (> 2 in 6 h). The external alarm (healthchecks.io heartbeat) is **still not set up** — a user action (`HEARTBEAT_URL` secret) |
| data-source failures handled safely | **Verified** | fallback + flags; stale → failure; news degrade → weight 0; `docs/research/failure_modes.md` |
| logs useful | **Verified** | every degradation lands in `run_meta`; step logs name the endpoint/attempt/reason; no secrets |
| state persisted | **Verified** | predictions, outcomes, shadow rows (append-only); research state in `research/`; roadmap/CLAUDE.md kept current |
| model/version identification reliable | **Verified after a correction** (2026-09-22) | `docs/research/versions.md`; golden pin, feature reference values, artefact hash, schema version, git SHA per row. The 2026-09-21 version of the feature guard was bit-exact across machines and broke the live shadow job; it now compares values with a tolerance, with regression tests in both directions |

## Security

| item | status | evidence |
|---|---|---|
| secrets protected | **Verified** | `docs/ops/security.md`; scans of tracked files and stored rows clean |
| workflow permissions reviewed | **Verified** | `permissions: contents: read` on both workflows |
| credentials absent from Git | **Verified** | `.env` ignored; `.env.example` placeholders; git grep clean |
| logs checked for secret leakage | **Verified** | code never logs secrets; psycopg errors do not echo the DSN |
| research-only boundary maintained | **Verified** | no execution code exists; documented |
| least-privilege database role | **Not yet** (low urgency) | the job uses the project's `postgres` role; a restricted role is a Supabase change for the user; mitigated by append-only triggers |

## Research quality

| item | status | evidence |
|---|---|---|
| E011 conclusion preserved | **Verified** | recorded; Phase L states nothing directional is justified |
| E012 conclusion evaluated honestly | **Verified** | pre-registered, 1h pass / 6h near-miss / 24h no, coverage check, by-move-size breakdown; prospective protocol pre-registered |
| E013 calibration validated | **Verified on validation data** | Platt ECE 0.014, ≤ 0.03 each year; the holdout confirmation is deliberately still ahead |
| live evidence tracked | **Verified (started)** | shadow record live since 2026-09-21 19:12 UTC; 2 rows; checkpoints at 500 / 2,000 / 5,000 hours |
| uncertainty reported | **Verified** | block-bootstrap intervals everywhere, gated by sample size; "no intervals yet" stated when too few |
| known limitations documented | **Verified** | README, `data_sources.md`, `reproducibility.md`, `failure_modes.md`, E-summaries |

## Maintainability

| item | status | evidence |
|---|---|---|
| architecture understandable | **Verified** | README rewritten (module map, how it runs, findings); module docstrings |
| modules reasonably separated | **Verified** | providers / indicators / scoring / news / ai / database / shadow / research; the research bench never imports the live orchestrator; the live job never imports research fitting code (only feature definitions for the shadow) |
| important dependencies documented | **Verified** | `requirements.txt` pinned exactly with the reason |
| no unnecessary complexity | **Verified** | performance review declined the one optimisation on offer; models are plain logistic + Platt in JSON |
| experiments reproducible | **Verified** | commands recorded; E012 re-run bit-identical |
| changes traceable through Git | **Verified** | one commit per phase/experiment; git SHA in every GitHub-produced row |

## Judgement

**Engineering: release-candidate quality — as of 2026-09-22, after the incident fix.** Every
engineering, security and maintainability item is verified except two that are not code: the
external heartbeat alarm and a least-privilege database role — both user actions in external
services, both mitigated, neither blocking a frontend that only *reads* the record.

The incident is part of this judgement, not an exception to it. What it showed: the live
pipeline and its guards held (no bad data, no missed prediction, no silent corruption — the
failure was loud and in the right place), but two design choices were wrong and are now
corrected. A backend of this age should be expected to produce a few more such findings; the
test is whether they surface loudly, get diagnosed from evidence, and end in a smaller class
of possible failures. This one did.

**Research: correct, honest, and early.** The research is valid and fully documented, but the
prospective live evidence is hours old. That is not a defect of the backend; it is the
calendar. The frontend can be built against a backend whose data is trustworthy today, as
long as the frontend shows the research state truthfully: the direction signal is an
instrument under test with no demonstrated edge; the move-size probability is calibrated on
development data and being tested live; confidence is a labelled heuristic.

**The holdout stays sealed.** Nothing about frontend work changes that; the one-time
confirmation waits for the Phase H checkpoints (see `research/ROADMAP.md`).

## What the frontend may rely on (read-only contract)

**Since 2026-09-22 this is a defined, versioned and tested contract, not a list of tables:**
`agent/api/state.py` and `docs/api/contract_v1.md`. Read the doc before building any screen.
Its rule is that a number which is not a validated probability must not be able to look like
one, so every quantity arrives with `kind`, `is_probability` and a `meaning` sentence, and the
signal always travels with its evidence status.

The underlying tables remain readable and append-only — `predictions`, `prediction_outcomes`,
`shadow_move_size`, `shadow_run_errors`, plus `research/monitoring/weekly_*.json` — but a
frontend that reads them directly takes on the job of labelling the numbers honestly, which is
exactly the job the contract exists to do once, in one place. The frontend must never write.
