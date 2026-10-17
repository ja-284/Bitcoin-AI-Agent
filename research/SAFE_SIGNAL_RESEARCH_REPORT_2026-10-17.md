# Safe signal research: final report and decision (Phases 6 and 7, 2026-10-17)

*The user's "MASTER PLAN: SAFE SIGNAL RESEARCH, DATA INTEGRITY, AND EVIDENCE-DRIVEN MODEL IMPROVEMENT". This report closes
the plan's batch.*

| phase | what was done | report or record |
|---|---|---|
| 1 | closed the data-boundary gap | `research/DATA_BOUNDARY_2026-10-17.md` |
| 2 | registered the batch | `research/experiments/E036_ms_a_liquidity_pair.json`, `E037_direction_d1_d2.json` |
| 3 | reproduced the references | `research/results/E036/reproduction.*`, `research/results/E037/reproduction.*` |
| 4 | ran the three comparisons once | `research/results/E036/ms_a.*`, `research/results/E037/d1_d2.*` |

- Phase 5's statistical controls were built into the Phase 4 run.
- Nothing in this report was produced by a new run. It was written from the committed records and results, after a
  read-only consistency check (section 9).

## 1. Verified data and implementation facts

**The data path (Phase 1; `ec4db68`, `59aa794`).**
- Every research file is now read through one governed reader, `agent/research/snapshots.py`:
  - registered files only;
  - each pinned by its name, the count and sha256 of its development rows, and the whole file's size and sha256;
  - rows cut by when they became visible, at the last development cutoff (2025-07-01 00:00 UTC);
  - reading stops at the first row past that cutoff;
  - nothing is ever downloaded or substituted.
- It covers the spot candles (through `load_bars`) and the six side snapshots.
- The macro snapshot is refused (below).

**Holdout status (stated exactly; never "untouched" or "fully blind").**
- **Before 2026-10-17, holdout rows were loaded into memory.** The older loaders read their whole files, the holdout
  period included, and only then dropped those rows. This covers both the six side loaders and `load_bars`.
- **The code and tests indicate:**
  - no holdout outcome was scored;
  - no holdout value entered a development feature calculation, because every feature was computed on a candle grid
    that stops at the holdout and reads only rows visible at its own cutoff;
  - this is confirmed by each module's future-scrambling test and by the new identity test in
    `tests/test_snapshots.py`.
- **The records cannot establish whether anyone ever viewed holdout-period values by hand.** Separately, raw holdout
  candles were read as warm-up inputs before (E000's backtest; the EWMA warm-ups before Amendment A1;
  `research/HOLDOUT_ROUTES.md`).
- The holdout is therefore **sealed for evaluation**: E014 and E023 have never run, and
  `research/HOLDOUT_ACCESS.log` does not exist. It is not untouched and not fully blind.

**Invalid macro research.**
- **What is wrong with the file:** `data/macro_2026-09-20.csv` holds quarterly bars (S&P, Nasdaq, dollar, 10-year
  yield) and roughly monthly bars (gold, oil). Each bar is stamped at its start and holds its end-of-period close.
- **Why that is a leak:** the macro code read every row as a daily close visible at D 22:00 UTC, so each value was
  used up to about three months before it existed.
- **What it voids:** **E006 is void, and so is E011's set B** (its dollar and yield inputs). Dated corrections are in
  both records (`beb6c6b`), and the dollar/yield watch item is withdrawn.
- **What it means from now on:** none of those results may be used as evidence for any future model decision. The
  snapshot is refused by the governed reader. E011's candle-only sets are unaffected.

**Code versions.**

| step | commit |
|---|---|
| registration | `21408d1` |
| reproduction code / result | `37ccab3` / `50d246f` |
| comparison code / result | `909e00a` / `c996fc7` |

`agent/` has not changed since `909e00a`, so the committed code is exactly what produced the results.

**Data versions (development rows only).**

| file | development rows | sha256 of those rows |
|---|---|---|
| `btcusdt_1h_2026-09-19.csv` | 68,868 | `8a87f7d4…` |
| `klines_extra_btcusdt_1h_2026-09-20.csv` | 68,868 | `04f0a2a0…` |
| replay cache `…_2017082713_2025063023_p0.2.0_s0.2.0.csv` | — | `accf1a73…` (whole file) |

**Settings.**
- Bootstrap: 48 h circular blocks, 2,000 resamples, seed 31.
- Logistic C = 0.1.
- Walk-forward: expanding, 365-day minimum training, 90-day test blocks, 1 h + 24 h purge (the smallest gap
  observed was 26 h). E036 adds a 90-day Platt slice; E037 has none.

## 2. Reference reproduction (Phase 3): exactly what was reproduced

| reference | data path exercised | values compared | largest difference |
|---|---|---|---|
| E018's full move-size model (identical to E019's incumbent; E018 recorded that it reproduces E013's Platt variant) and E019's 24 h EWMA rule, including their paired difference | spot candles and trade counts through the governed readers; the s0.2.0 replay cache (row index and periods) | 51 (38 floats) | 0.0 |
| E032 (M, F, B and every bootstrap interval), re-run by its own unchanged code | spot candles, trade counts and taker volume through the governed readers; the s0.2.0 replay cache (category scores) | 153 (108 floats) | 0.0 |

**What this does NOT show.**
- **E013's own result files were not compared directly.** E018's record states the identity with E013's Platt variant,
  and E013's rounded figures agree (validation Brier 0.2249, ECE 0.0139).
- **No other experiment was reproduced:** not E001–E012, E015–E017, E020–E031, E033 or E035.
- **Four data files were not exercised:** funding, premium, on-chain and difficulty. Their development rows match
  their registered fingerprints (the check of 2026-10-17), but no result built on them was reproduced. The refused
  macro file was not read at all.
- **Not every historical dataset has been independently verified.** The fingerprints prove only that the files are
  unchanged since registration, not that each value equals the one first published. Revision risk remains as recorded
  in the inventory; on-chain data in particular, since hash rate is an estimate and fees are priced in USD.

## 3. Candidate results (Phase 4, one run, development data only)

| comparison | question | verdict (registered rules) |
|---|---|---|
| **E036 MS-A** | do `amihud_rel_168` and `trade_size_rel_24` add move-size information to E013's nine inputs? | **NOT_SUPPORTED** |
| **E037 D1** | do the four BUY/HOLD/SELL category scores add directional information to E032's four candle inputs? | **INCONCLUSIVE** |
| **E037 D2** | does `up_streak_6` add directional information to E032's eight inputs? | **NOT_SUPPORTED** (it fails the calibration requirement) |

**Rows.**
- **E036:** 63,988 common frame rows. That is 192 fewer than E013's 64,180, the hours where `amihud_rel_168`'s window
  is incomplete. It has 54,286 out-of-sample rows (41,159 exploration, 13,127 validation) in 27 folds: 7,842–60,162
  training rows, 1,581–2,160 calibration rows and 1,606–2,160 test rows per fold.
- **E037:** 56,309 out-of-sample rows (43,182 / 13,127), identical to E032's; none were lost to `up_streak_6`. It has
  28 folds (7,846–62,514 training rows, 1,584–2,160 test rows), and M reproduces E032 exactly.

## 4. Uncertainty and multiple testing

The table gives validation differences; positive means the extra information helps. Exploration is shown for
contrast.

| | validation d | 95% interval | 97.5% interval | p | Holm-adjusted p | exploration d |
|---|---|---|---|---|---|---|
| MS-A: Brier(ref) − Brier(cand) | −0.000240 | [−0.000424, −0.000068] | — | 0.012 | 0.012 (family of one) | +0.000063 [+0.000010, +0.000116] |
| D1: Brier(R) − Brier(M) | +0.000113 | [−0.000169, +0.000401] | [−0.000203, +0.000445] | 0.459 | 0.918 | +0.000475 [+0.000292, +0.000649] |
| D2: Brier(M) − Brier(C) | −0.000155 | [−0.000872, +0.000490] | [−0.000965, +0.000608] | 0.666 | 0.918 | +0.00158 [+0.00115, +0.00202] |

- **Three comparisons in total.** Move-size is a family of one; direction is a family of two, corrected with Holm.
- **What the correction changed: nothing.** No direction comparison was significant before it.
- **How to read MS-A's p = 0.012:** the difference points the wrong way. The candidate is *worse* on validation, so S1
  (a significant improvement) fails.

## 5. Calibration and stability

- **MS-A.**
  - Calibration: the candidate passes E013's rule (validation ECE 0.0144, buckets OK; exploration ECE 0.0046).
  - Ranking: unharmed (validation ρ 0.3587 vs 0.3603).
  - Stability: d is positive in only **4 of 8** years (2020, 2021, 2023 and a zero-level 2018); 2024 and 2025 are both
    negative.
- **D1.** M meets the calibration requirement (it is E032's model). d is positive in **7 of 8** years; only 2018 is
  negative. The 2024–25 values (+0.000123, +0.000094) are much smaller than 2019–23's (+0.00026 to +0.00069).
- **D2.**
  - Calibration: C **fails E013's bucket rule on validation**. Its calibration slope is 0.647, against M's 1.017, so it
    is over-confident.
  - Stability: d is positive in 6 of 8 years, with 2021 and 2025 negative. The exploration gain (+0.0038 in 2018,
    falling to +0.0004 in 2024) did not carry into 2025 (−0.0013).
  - The `up_streak_6` coefficient (−0.200, standardised) has the same sign in 100% of folds: a stable direction, an
    unstable size.

## 6. Practical effect size (the registered bar: 1.10× skill, in Brier terms)

| | threshold | validation d | skill ratio (larger / smaller model) | reading |
|---|---|---|---|---|
| MS-A | +0.002453 | −0.000240 | 0.990 | the interval excludes the bar entirely; the candidate is slightly worse |
| D1 | +0.0000957 | +0.000113 | 1.118 | the point estimate passes the bar, but the interval includes both zero and the bar |
| D2 | +0.0001070 | −0.000155 | 0.855 | the interval reaches the bar, so the bar itself was not excluded; NOT_SUPPORTED by calibration |

**None of these figures establishes trading profitability.**
- Every quantity here is a probability-quality measure (Brier, calibration, ranking).
- E032-style gross returns per hour on validation (M +0.0069%, R +0.0103%, C +0.0137%, F +0.0134%) were reported only
  descriptively. They stand against a 0.10% round trip and support no claim.

## 7. Known limitations and the prior use of these years

**Repeated use of the development periods.**
- **The precise count.** By my reading of the records, **29 of the 36 earlier experiments (E000–E035)** fitted or
  evaluated something on the development periods: E001–E008, E010–E013, E015–E022, E024, E026–E029, E031–E033, E035.
- **The ones that did not:**
  - E000 (buffer);
  - E009 (AI components);
  - E014 and E023 (registered, never run);
  - E025, E030 and E034 (live only).
- **With this batch the total is 31.** E006, among the 29, is now void.
- **A correction:** the E036/E037 records and the brief say "about 35". The precise count is 29 (31 with this batch).
  The registered records are left as written.
- **What the registered controls do and do not achieve:** registration before code, reproduction gates, identical rows,
  the paired bootstrap, Holm, the practical bar, calibration and year rules all make the batch disciplined. They do not
  make it **independent confirmation**: these years have been looked at too often for that. Every result here is
  hypothesis-generating.

**Other limitations.**
- **Validation wear works in both directions.** A pass would not have confirmed anything, and a fail on a
  much-examined period is not a final verdict either.
- **Only two periods.** Validation is 18 months (13,127 rows), so one market regime can dominate it. The exploration
  vs validation reversals (D1, D2) are exactly the pattern a single regime change would produce.
- **Narrow scope.** Each result concerns one target, one horizon (1 h), one model (logistic regression, Platt
  calibration for move-size), and these specific input definitions.
- **News is absent.** There is no historical news, so no offline test can include it.

## 8. Verdicts, and what they do and do not mean

- **MS-A is NOT SUPPORTED** under its registered criteria.
  - The validation data exclude a useful gain, and the candidate was slightly worse.
  - **Scope:** for the 1 h |return| > 0.25% target, in this model, on development data.
  - **It does not say** these features are useless for every target or horizon.
- **D1 is INCONCLUSIVE.**
  - The category scores add a small, consistent amount in 2017–23 (7 of 8 years) that 2024–25 neither confirms nor
    rules out.
  - **This is not proof of no effect, and not proof of an effect.** It is about these four scoring-0.2.0 scores as
    linear inputs at 1 h, not about every underlying indicator.
- **D2 is NOT SUPPORTED: it failed its calibration requirement.**
  - Strong in 2017–23, absent and over-confident in 2024–25.
  - The data did not by themselves exclude the practical bar. The registered calibration rule decides the verdict.

## 9. The read-only consistency check (2026-10-17; 37 checks, 0 failures)

| area | checked |
|---|---|
| Git order | both records were added together in `21408d1`, before the reproduction code (`37ccab3`) and the comparison code (`909e00a`); `21408d1` is their ancestor |
| results vs code | both result files name `909e00a` and were generated after it was committed; `agent/` has not changed since |
| registrations | since registration only the outcome fields changed (`git_commit`, `status`, `result`, `phase_3_reproduction`); every registered criterion is untouched |
| code vs registrations | inputs, α, the practical bar, the ECE bar, the ρ tolerance, the year rule, the tripwires, the bootstrap settings, the target, C, the horizon and both walk-forward specifications match; no holdout route |
| saved results vs docs | every quoted figure matches the saved results; each verdict follows from its criteria as stated above; no tripwire fired; E037's rows and M are identical to E032's |
| reproductions | both report 0 differences; re-comparing E032 with its committed reproduction gives 0 differences again |
| data path and tree | `snapshots.py` changed only in `ec4db68` and `59aa794`; the holdout access log is absent; the working tree is clean |

**Not done, on purpose:**
- no experiment was re-run;
- no raw holdout value was read;
- no direction prediction or outcome was inspected (the E034 track was counted only);
- no data was downloaded.

**One wording correction** came out of the check: the experiment count in section 7.

**No material problem** requiring a code, data or experiment change was found.

## 10. Is further research justified, and is a prospective test justified?

**No, for all three candidates.**
- **MS-A** is excluded on validation. The registered line is closed.
- **D2** fails its calibration requirement, and its large 2017–23 gain did not carry into 2024–25. The registered line
  is closed.
- **D1** is inconclusive, but a prospective test would not resolve it at reasonable cost.
  - The gain is about +0.0001 Brier on validation. E033 measured a difference of the same order (E032's model vs the
    one-feature rule, +0.00011 on validation): telling it apart prospectively needs 15,000–188,000 graded hours, so it
    is effectively undecidable.
  - Neither answer would change anything that runs: the frozen `direction_1h_v1` already contains the category scores,
    and it stays frozen.
  - Its registration allows no follow-up variant.

No result here justifies a new frozen artefact, a new shadow track or any change to the live model.

## Phase 7: the decision

**What the evidence supports.**
- On development data, neither the liquidity pair (MS-A) nor `up_streak_6` (D2) improves the existing models under
  their registered criteria.
- The reference models reproduce bit for bit through the corrected data path.
- No holdout outcome was scored and no holdout value reached a development feature.

**What remains unknown.**
- Whether the category scores carry a small directional contribution beyond the candle inputs (D1): it is real in
  2017–23 and undetermined in 2024–25.
- Whether anyone ever viewed holdout-period values by hand.
- Whether daily macro data carries any information: untestable without a new, registered daily snapshot, which is not
  approved.
- Whether the earlier development-period findings hold out of sample. Only the sealed holdout (a user decision) or the
  prospective tracks can say.
- Whether any of this has economic value. Nothing here measures that.

**What continues, unchanged** (dates estimated from the observed rates on 2026-10-17):

| what | where it stands | when |
|---|---|---|
| live BUY/HOLD/SELL system, heartbeat, watchdog, reporting | running | hourly |
| weekly audit | last report 2026-10-13 | due ≈ 2026-10-20 |
| move-size 2,000-hour reading (the E012 verdict) | 612 of 2,000 graded hours; the pre-check passes every mandatory item and exits 3 (not reached) | ≈ 2026-12-14/15 |
| move-size 5,000-hour reading (the E013 verdict) | 612 of 5,000 | ≈ 2027-04-21 |
| direction shadow track E034 | 47 eligible hours, 0 lost; blind until each reading | 1,000 h ≈ 2026-11-26; 3,000 h ≈ 2027-02-17; 6,500 h (the verdict) ≈ 2027-07-13 |
| news evaluation | about 649 usable hours of 3,140 (a direct count; the weekly report's count may differ by a few early rows) | verdict ≈ 2027-02-03 |

These dates are extrapolations. Missed hours or outages would move them, and each reading runs at the first session
after its count is reached.

**What is explicitly not approved.**
- No further work on MS-A, D1 or D2, and no substitute features, variants, transforms or combinations for them.
- No additional model, no new live experiment, no new shadow track, no new data source (including a new macro
  snapshot).
- No change to the live BUY/HOLD/SELL scoring, to `move_size_1h_v1`, to `direction_1h_v1`, or to any registered
  checkpoint, threshold, target, window or success criterion.
- No use of E006 or E011's set B as evidence for anything.
- No access to the sealed holdout. Opening it remains the user's explicit decision.
- No trading of any kind.

## Reproducible commands

```
python -m agent.research.signal_batch reproduce   # Phase 3: E018/E019 and E032 must match their committed results to 1e-9
python -m agent.research.signal_batch compare     # Phase 4: refuses to run with uncommitted code under agent/
python -m agent.research.checkpoint_precheck      # the 2,000-hour integrity pre-check (exit 0 READY, 3 not reached, 1 FAIL)
python -m agent.research.direction_checkpoint     # counts only until a reading is due (Amendment 1.1)
```

Running `compare` again would rewrite `research/results/E036/ms_a.*` and `research/results/E037/d1_d2.*` with
identical figures (the bootstrap seed is fixed) but a new timestamp. It is not needed, and this report does not
depend on it.
