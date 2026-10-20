# Evidence assessment: what would it take to call this system predictively useful? (2026-10-20)

Written for the user's post-audit plan (2026-10-20, Phase 4). **No experiment was run and no new figure was computed.**
Every number below comes from a record that already exists, named in the row. The registered criteria are quoted, not
changed. This is not a readiness score: the six areas are separate requirements, and passing one says nothing about
another.

**Read every development result through validation wear.** 31 experiments have examined the development years
(`research/SAFE_SIGNAL_RESEARCH_REPORT_2026-10-17.md`). So an offline result is hypothesis-generating. Only the
prospective record, or one registered look at the sealed holdout (a user decision), can confirm anything.

**Statuses:** *demonstrated* (a registered criterion passed on data it was not built on) · *not demonstrated* (a
registered test ran and failed) · *inconclusive* (a test ran, and its size cannot decide) · *being collected*
(registered, waiting for its size) · *next decision point* (the registered reading that will decide).

## 1. BUY / HOLD / SELL (scoring 0.2.0, live)

| | |
|---|---|
| Registered criterion | E001: an edge (mean return after BUY minus after SELL) above zero with its interval excluding zero in both development periods, **and** three-class balanced accuracy above every trivial baseline in both |
| Demonstrated | nothing |
| Not demonstrated | decision skill. E001 (68,619 replayed hours, five horizons) and E017 (the gap-corrected re-run): the criterion fails at every horizon. Confidence is uninformative: stated 0.7–0.9, observed ≈ 0.48 |
| Live, descriptive (weekly report 2026-10-20) | 1h: acted accuracy 0.500 (n = 446) against 0.501 naive; edge −0.009% [−0.080%, +0.054%]; stated-confidence ECE 0.425. At 72h the interval is below zero (−1.46%), from about 4–5 independent blocks, so it is not read |
| Being collected | the live table, descriptively. **No prospective criterion is registered for this signal** (proposal P1) |
| Limitations | it is a fixed heuristic formula, never fitted; news moves about 5% of its calls |

## 2. Move size (`move_size_1h_v1`, frozen; P(next-hour move > 0.25%))

| | |
|---|---|
| Registered criteria | `research/LIVE_EVALUATION.md` rule 4. **E012:** Brier ≥ 5% below the base rate of the same hours, accuracy ≥ naive + 5 points, and ρ(p, \|move\|) ≥ 0.10 with its interval excluding zero. **E013:** ECE ≤ 0.03 and every bucket with ≥ 100 rows within 0.05 |
| Demonstrated (development) | E012 passes at 1h in both periods (Brier −15% / −9% against the base rate, ρ 0.45 / 0.36). E013: validation ECE 0.014, ≤ 0.03 in every year. E019: 2.47× the skill of a free 24h-EWMA rule (+0.098 vs +0.040). E020: fancier models do not help. All of it hypothesis-generating under validation wear |
| Prospective, official (500-hour first look, no verdict by registration) | Brier gain +0.089 [+0.019, +0.137]; ρ +0.324; ahead of the EWMA rule (0.1927 vs 0.2091); accuracy 0.698 vs 0.696 naive; ECE 0.059 (ordinary at that size, E024); stated 0.335 vs observed 0.304 (+0.031 [−0.013, +0.070], not established) |
| Prospective, routine (weekly report 2026-10-20; not a checkpoint; intervals optimistic below ~2,000 h) | n = 681: Brier 0.1952 vs base 0.2155 (+9.4%); ρ +0.312; ECE 0.051; accuracy 0.695 vs 0.686; ahead of the EWMA rule by 0.0177 |
| Inconclusive | calibration prospectively (readiness row 8 PARTIAL); the accuracy part |
| Being collected | 682 of 2,000 graded hours (13:16 UTC; 685 by 16:30) |
| Next decision point | **2,000 hours ≈ 2026-12-14: the E012 verdict.** 5,000 hours ≈ 2027-04: the E013 verdict, with regime slices |
| Limitations | (a) **Every live hour so far is in the calm tercile** (rv_168 below 0.004759), so a 2,000-hour verdict may describe calm markets only. (b) In a calm market few hours cross 0.5, so the accuracy part tends to the majority call even when Brier and ranking are good. E024's ~2% chance-fail figure was measured over validation stretches, not a persistently calm one (`research/DIAGNOSIS_2026-10-15.md` row 2). (c) Most of the skill is knowing the volatility *level*. The model's own timing is the smaller part (E021: +0.074 against a volatility-scaled target, where the EWMA rule scores +0.0003). (d) It says how big the next move is likely to be, **not which way** |

## 3. Direction (E034, `direction_1h_v1`, blind)

| | |
|---|---|
| Registered criteria | `research/DIRECTION_TRACK.md` §7, at 6,500 eligible hours. IMPROVEMENT = Brier gain over the base rate with lo > 0 **and** the calibration guard (\|mean stated − observed\| ≤ 0.03, ECE ≤ 0.03). Otherwise SKILL BUT MISCALIBRATED, NO IMPROVEMENT (hi < 0.0005) or INSUFFICIENT EVIDENCE |
| Demonstrated (development) | E032: a faint 1h P(UP), calibrated and positive in 8 of 8 years (Brier skill +0.0038 / +0.0043 against a leak-free base rate). Essentially one reversal feature (H_b fails) |
| Not demonstrated | that it is more than one feature (E033: undecidable at any size the track will reach); economic value (gross edge 1–13% of a 0.10% round trip) |
| Being collected | 117 eligible hours at 13:16 UTC (121 rows by 16:30), 0 lost, integrity 9 of 9. **No outcome figure exists outside the registered readings** (Amendment 1.1) |
| Next decision point | 1,000 hours ≈ 2026-11-26 and 3,000 ≈ 2027-02-17 (looks, no verdict); **6,500 ≈ 2027-07-13 (the verdict)** |
| What it can establish | whether a faint, calibrated directional probability holds on new data |
| What it cannot | usefulness for trading (§9 only *describes* economics); anything beyond one feature; anything before 6,500 hours. E033: in a calm market even 6,500 may be too few, read as INSUFFICIENT EVIDENCE, never extended after looking |

## 4. News (Claude Haiku 4.5 score, one of the five categories)

| | |
|---|---|
| Registered criterion | E025: 1h Spearman ρ of the hour's news score with the next-hour return, with a 48h block-bootstrap interval excluding zero, at **3,140 usable hours** (80% power for \|ρ\| = 0.05) |
| Demonstrated | reliability: the scorer is schema-reliable, with a small order-sensitivity bias, and the explainer is faithful and decision-neutral (E009). The record is clean: 0 news errors in 7 days; 18 news-unavailable hours in total, each marked |
| Inconclusive | incremental value. E030's first look on 500 hours: 1h ρ +0.046 [−0.052, +0.151], with every interval including zero. At that size only \|ρ\| ≥ 0.125 is detectable |
| Being collected | 715 of 3,140 usable hours (the registered query, 2026-10-20 12:00 UTC hour) |
| Next decision point | **the verdict ≈ 2027-01-29 to 02-03** |
| Cost | ≈ $7.66 per 30 days, 74% of the AI cost (`research/NEWS_COST_VALUE_2026-10-15.md`). The whole AI cost is ≈ $10.29 per 30 days (weekly report, list-price estimate) |
| Limitation | there is no historical news archive, so news can never be back-tested. If the verdict's interval includes zero, keeping news becomes a cost decision for the user (diagnosis row 7). No rule says so yet (proposal P4) |

## 5. Operational readiness

| | |
|---|---|
| Registered criterion | the readiness gate, revision 3 with addendum 2: **20 PASS, 2 PARTIAL** (calibration prospectively; prospective monitoring by the calendar). RELEASE CANDIDATE, not FINAL |
| Demonstrated | reliability: 736 of 747 hours since go-live, none lost since 2026-10-07. Integrity: parity 732/732; probabilities reproduce (5.6e-16); 0 outcomes graded early. Security: RLS on and API roles revoked; least-privilege role exact; 0 vulnerable packages. Alarms: missed-hour and direction emails proven by delivery tests (2026-10-15/16). Test guards: the full mutation suite caught 166 of 166 at `368df96` (2026-10-20, after the F1 repair), and every guard's target is now checked on each commit |
| Not demonstrated | **recovery of the record itself.** No documented backup, export or restore procedure exists for the Supabase database, which holds the only copy of the prospective evidence (proposal P5). The AI-failure alarm's failing path has not happened for real |
| Limitations | the external alert path (healthchecks.io and its email) can fail silently. A periodic look at its dashboard is the only check (`docs/ops/observability.md`, 2026-10-20 review). The watchdog runs about half its slots |

## 6. Economic usefulness

| | |
|---|---|
| Registered criterion | only for direction: "economically useful" may be written only if the 6,500-hour verdict is IMPROVEMENT, **and** long/flat's net mean per traded hour at the standard 0.11% one-way cost has an interval above zero, **and** it beats buy-and-hold (`DIRECTION_TRACK.md` §9). Nothing comparable is registered for the other components |
| Demonstrated | nothing |
| Not demonstrated | the BUY/HOLD/SELL edge (−0.009% at 1h) is far below a 0.22% round trip (`research/COST_ASSUMPTIONS_2026-10-16.md`). E032's directional edge is 1–13% of costs. Move size gives no direction at all |
| Why prediction ≠ profit | (a) Costs: a statistically real edge can be far smaller than fees, spread and slippage. (b) Selection: one history examined 31 times flatters whatever survives. (c) Calm-market evidence may not carry over. (d) A Brier gain improves probabilities, not decisions: turning it into returns needs a decision rule, position sizing and risk limits, each with its own error. (e) Execution adds failure modes (latency, partial fills, outages) that analysis never meets |
| Status | automated execution is **NOT ACTIVE** (`docs/FUTURE_EXECUTION_ARCHITECTURE.md`): a separate layer, paper trading first, risk controls and a kill switch, and only after the prospective validation. No evidence here justifies starting it |

## Proposals for later pre-registration (NOT rules; none applies to a current experiment)

Each would need the user's decision and, where it touches a reading, registration **before** that reading is
computed. None changes a threshold.

- **P1, BUY/HOLD/SELL:** either register one prospective test of E001's criterion at a fixed live size, or formally
  label the signal "display only, no claimed value" until a new version passes on development data and
  prospectively.
- **P2, move-size scope:** decide, before the 2,000-hour reading is computed, how a verdict reached entirely in the
  calm tercile is worded (for example "shown in calm markets only"). This is wording only, with no criterion moved.
- **P3, move-size usefulness:** no criterion says what decision the probability improves. Usefulness would need a
  registered decision rule and its own baseline (for example the EWMA rule), judged prospectively.
- **P4, news:** register the decision that follows the verdict (keep, keep for display only, or drop) before the
  3,140-hour reading.
- **P5, recovery:** a documented, owner-run export of the record to the user's own storage, outside the public repo
  (it holds the blind direction rows, which must not be published), plus one restore drill as a readiness item.
- **P6, economics:** if any component reaches a positive statistical verdict, register an economic test in the
  style of DIRECTION_TRACK §9 for it before looking further. Paper trading remains a later stage, outside this
  project's current phase.

## What this assessment does not say

It does not say any model is good or bad beyond its registered readings. It does not combine the areas into a score.
It recommends no new experiment: the default is to let the registered prospective evidence accumulate.
