# Why predictive performance is weak: a consolidated diagnosis (2026-10-15)

Master plan, Phase 2. **An analysis of existing work, not a new experiment.** Nothing was fitted for use, nothing
was selected, and no rule or model changed. Every figure comes from a committed source:
- `tools/diagnose_500h.py` → `research/monitoring/diagnosis_500h_2026-10-15.json`. Exactly the registered first
  500 prospective hours, with the project's own statistics functions.
- `tools/diagnose_e031_slopes.py` → `research/results/E031/block_slopes_by_fold.json`. Development data only.
- The experiment records E012–E032 and `research/monitoring/checkpoint_500h.md`.

**One caution, stated first.** The 500 hours examined in 2A are the first quarter of the 2,000-hour reading's fixed
prefix. Nothing learned from them may be used to fit, choose or tune anything that is later judged on them, and
nothing below is. Phase 4's hypothesis was chosen from development evidence. It does not target the 500-hour misses.

## 2A. The 500-hour reading, measured more closely (descriptive)

| measure | value | what it means |
|---|---|---|
| stated − observed, overall | **+0.031 [−0.013, +0.070]** | an over-statement of about 3 points, but the interval includes zero: not established |
| raw logistic vs after Platt (mean) | **0.301 → 0.335**, observed 0.304 | the raw model is level with reality here. The Platt map adds about +0.034 |
| calibration slope / intercept | 1.05 [0.67, 1.28] / −0.13 [−0.33, +0.10] | **no sign of over-confidence** (a slope below 1 would mean too extreme). What is there is a level shift |
| buckets (n 17–155) | +0.085, −0.082, +0.017, +0.074, +0.100, −0.072 | the gaps alternate in sign, with wide intervals. That looks like sampling noise around a small level shift, not a pattern |
| ECE | 0.059 | E024: a model as good as on validation stays above 0.03 at 500 hours about 90% of the time |
| six-hour blocks (n ≈ 125 each) | 00–06 −0.027, 06–12 −0.004, 12–18 +0.011, **18–24 +0.138 [+0.024, +0.230]** | only one block's interval excludes zero, and the live pattern does not match development (E027 validation: +0.022 / +0.007 / −0.057 / +0.013). With four blocks this small, one excluding zero can easily be chance (and E025 found these intervals optimistic at 500 hours) |
| regime | 500 of 500 hours calm (low tercile) | no regime comparison is possible |
| week by week | +0.069, +0.024, +0.035, then −0.213 (22 hours) | it wanders, as E029 found the family's calibration does |
| data quality and evaluation code | 500 / 500 probabilities reproduce (5.6e-16); input parity; 0 outcomes graded early; registered code | **ruled out** as a cause |

## The weak points, one row each

| # | problem | what the evidence shows | what is unknown | most plausible explanation, and why | the single next step | what makes us stop instead of trying variants |
|---|---|---|---|---|---|---|
| 1 | **Move-size calibration live** (500-h ECE 0.059, +0.03 over-statement) | The level gap is not significant ([−0.013, +0.070]). The slope is ≈ 1. The bucket gaps alternate. The raw model is level (0.301 vs 0.304), and Platt adds +0.034 | whether a level shift persists over 2,000 / 5,000 hours | **A calibration level that does not carry across volatility regimes.** Platt was fitted on a 2025 slice where the raw model *under*-stated large moves (E013), so it shifts probabilities up. In a calmer market that shift over-shoots. E029 shows the family's level wandering for weeks, 3–4 times a year. The buckets are mostly noise at this size (E024) | none on v1, which is frozen. Read the registered 2,000-hour bucket table and the 5,000-hour E013 verdict. Phase 4 deliberately does **not** target this level, because doing so would be tuning to the 500-hour miss | if the 5,000-hour E013 verdict fails: record v1's calibration as not transferable across regimes. Any new calibration approach then needs its own registration and its own prospective record, never a refit of v1 |
| 2 | **Yes/no accuracy at 0.5** ≈ "always small" (0.698 vs 0.696) | only 71 of 500 hours were stated above 0.5. The large-move share is 0.30 | the 2,000-hour E012 accuracy part | in a calm regime few hours cross a fixed 0.5. So a 0.5-threshold classifier collapses to the majority call **even when ranking and Brier are good** (ρ +0.32, Brier skill +0.089). E024: missing this part at 500 h is a ~41% event for a validation-quality model | the registered 2,000-hour E012 verdict, unchanged | if E012's accuracy part fails at 2,000 hours (about a 2% event for a validation-quality model): record it and demote the deliverable per rule 6. The threshold is never moved |
| 3 | **Representativeness:** every hour so far is calm | rv_168 stayed below the low tercile's cut-point for all 500 hours | behaviour in normal and volatile markets | the market has been calm since go-live; nothing is wrong with the record | only time. The 5,000-hour reading slices by regime | nothing to stop. It cannot be investigated without data, and no simulated regime replaces it |
| 4 | **The 500-hour reading was not blind** | 400 of its hours were reviewed in aggregate on 2026-10-08, and weekly reports show the running record | — (a fact) | monitoring by design | state it at every reading. Keep diagnostic looks such as 2A out of any model choice | n/a |
| 5 | **Intraday miscalibration (E027), and why E031 failed** | E027: offsets in both development periods. E031: removed them (0.057 → 0.012), but the confident tail went to +0.077 (slope 0.976 → 0.928). **Per fold (27 folds, development):** the four block maps' slopes average the same as the single map's (mean difference −0.001, sd 0.159, 42% steeper), but they are noisy (range 0.00 to 1.57; about 505 rows each). Their **intercepts** differ (−0.08 / +0.07 / +0.19 / +0.15) | whether one shared slope keeps the tails calibrated; whether the offsets persist live (the 500-hour block pattern differs) | **E031 had too many degrees of freedom.** The real intraday effect is a *level* per block. The slopes do not genuinely differ between blocks, so fitting four of them on ~505 rows each only added noise, and steep blocks spread the tails | **Phase 4's one hypothesis:** one shared slope plus four block intercepts (5 parameters instead of 8), on development data only, registered first | if it fails its registered offsets or bucket criterion: **close the intraday-calibration line.** No further variants (other blocks, slice lengths, smoothers). E027's offsets stay a descriptive reference for the 2,000-hour slices |
| 6 | **Direction is faint, one-feature, and uneconomic** (E032) | Brier skill vs a leak-free base rate +0.0038 / +0.0043; calibrated; positive in 8 of 8 years. The one-feature rule (taker-buy share) gets 90% of the model's validation skill and 51% in exploration; the model is not better on validation. The gross edge is ~1–13% of costs. **E032 reproduces exactly** (re-run 2026-10-15, identical) | whether the faint skill holds on new data; whether anything beyond the one feature adds | a real, stable, tiny 1h reversal (heavy taker buying precedes slightly lower returns, E008, E011), far too small to trade at retail costs | **Phase 3:** a separate prospective direction shadow track, registered before collection, measuring skill only. It is never combined with move-size and never acts | if the registered prospective verdict's interval for skill against the base rate includes zero: close the directional track on free candle data until genuinely new information exists |
| 7 | **News value unknown** | E030: 1h ρ +0.046 [−0.052, +0.151], so this size sees only ρ ≥ 0.125. The review: $7.66 per 30 days, and it changes 5.5% of signals, mostly to HOLD | whether news predicts at the plausible size (ρ ≈ 0.05) | underpowered, not uninformative | the registered verdict at 3,140 usable hours (≈ 2027-02). Nothing changes before then | if the verdict's interval includes zero: news adds no detectable 1h information, and keeping it becomes a cost decision for the user |
| 8 | **Validation wear** | about 30 experiments have examined the development periods; E022's rule | the true out-of-sample value of any offline finding | inherent to a long research programme on one history | label every offline result hypothesis-generating. Confirm only prospectively (separate shadow tracks), or once on the holdout (a user decision) | never present an offline pass as confirmation |

## What this diagnosis does not say

- It does not say v1 is miscalibrated. At 500 hours the evidence cannot distinguish a real level shift from noise,
  and the registered readings will.
- It does not say the intraday fix works. That is Phase 4's question.
- It does not say direction is useful. E032 measured skill, not usefulness.
- It changes no model, rule, selection, threshold or weight.

## Update, 2026-10-15 (after E035): row 5's explanation was only partly right, and the line is closed

The table above is kept as written. Row 5 named the single next step, and it has been taken: E035 (registered in
`1ff9e12` before its code; result in `research/results/E035/`).
- One shared slope plus four block intercepts removed the offsets (worst block 0.057 → 0.008 on validation) and
  even improved skill (Brier +0.00074 [+0.00011, +0.00132]).
- But it **failed E013's bucket rule at the same place as E031**: [0.8, 0.9) over-stated by +0.069 (n = 262),
  against E031's +0.077 and the incumbent's +0.028.
- So "too many degrees of freedom" was at most part of E031's failure. The shared slope (0.962) did not keep the
  tail calibrated.
- What the numbers suggest, as an observation only: the block intercepts themselves, the US session's +0.20
  above all, lift some hours into the high-probability range, where this family already over-states slightly.

**Row 5's stop rule applies, as registered: the intraday-calibration line is closed.** No further variant is run
on this data (other blocks, slice lengths, smoothers, shrunk intercepts, a tail cap). E027's offsets stay a
descriptive reference for the 2,000-hour slices. The documented limitation remains: the reference model's
probabilities are miscalibrated by time of day, by up to about 0.06 in the US session on validation, offset
elsewhere.

