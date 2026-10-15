# News: cost and value (review, 2026-10-15)

Master plan, Phase 1, step 3D. **Read-only.** Nothing in production changed: no weight, no prompt, no call added or
removed. The figures come from `python tools/news_cost_value.py`, and its exact output is
`research/monitoring/news_cost_value_2026-10-15.json` (613 hours, pipeline 0.2.0, 2026-09-19 20:00 →
2026-10-15 12:00 UTC). It reads **no outcome**: whether news predicts returns is E030's registered question.

## What news is in the system

- The hourly job sends the last 24 hours of RSS headlines and snippets, cut off at the information cutoff, to
  Claude Haiku 4.5. It gets back a relevance-weighted sentiment score in [−1, +1], the news category.
- That category has nominal weight **0.15** of 1.00 (`agent/scoring/scorer.py`). The other weights are trend 0.25,
  momentum 0.25, volume 0.20 and chart pattern 0.15. The signal thresholds are ±0.15 (`agent/decision/decision.py`).
- So news alone, at full strength, can move the overall score by up to the threshold. That is what lets it
  change a signal.
- When news is unavailable, its weight is 0 and completeness drops, visibly. It is never scored as neutral.

## Measured (the live record)

**Cost**, from the API's own token counts at the dated list prices (2026-09-23 table: Haiku 4.5 $1 / $5, Sonnet 5
$2 / $10 per million tokens):

| | last 7 days (167 runs) | last 30 days (523 runs) |
|---|---|---|
| news call: mean tokens in / out | 1,543 / 1,884 | 1,511 / 1,824 |
| news call: cost per run | $0.0110 | $0.0106 |
| news call: per 30 days | **$7.89** | **$7.66** |
| explanation call: per 30 days | $2.71 | $2.74 |
| all AI per 30 days | $10.61 | $10.40 |
| news's share of the AI cost | 74% | 74% |

- The 7-day total matches the weekly report's own cost function exactly ($10.61).
- The total is under the accepted ~$12/month and the $15 flag.
- The news call writes more tokens than it reads (≈ 1.2×). Its answer echoes each headline, a design choice
  recorded on 2026-09-21: removing the echo would roughly halve the news cost, but it changes the AI's task and
  would need E009 re-run.

**Reliability** (613 hours):
- 18 hours had news unavailable:
  - 17 from the `max_tokens` defect of 2026-09-21/22, fixed then;
  - 1 provider server error on 2026-09-29.
- Every one of them is marked in its row. None has happened since 2026-09-29.
- 1 explanation failure (the same 2026-09-29 error).
- 0 hours with a feed down, and 0 hours with no headline used. The median is 51 headlines per hour (mean 44).
- **Not recorded:** the latency of the AI calls themselves. Only the whole run's lag after the cutoff is stored
  (median 753 s, which is mostly the :12 schedule). There is no evidence of slow calls, and none of their absence.

**Influence on the signal** (595 hours where news had weight; recombined without news by
`research/parity.overall_without_news`, the parity check's own function):

- **News changed the stored signal in 33 hours (5.5%):** 19 SELL → HOLD, 13 BUY → HOLD, 1 HOLD → BUY.
- So in practice news mostly *damps* the signal towards HOLD.
- Without news the mix would be 228 BUY / 205 HOLD / 162 SELL; with it, 216 / 236 / 143.
- Mean absolute shift of the overall score: 0.029; largest 0.107.
- News score: mean +0.086, sd 0.140, 30% of hours negative.

## What the evidence says about value

| question | evidence | what it shows | what it cannot show |
|---|---|---|---|
| Does the scorer do its job? | E009 (2026-09-20) | reliable and stable (sd 0.013 across repeats); relevance separates relevant from irrelevant (0.93 vs 0.04); signs correct on crafted headlines. Its one failed check: order sensitivity (shuffling the headlines shifts the aggregate by 0.046, about 0.007 on the overall score) | whether the *aggregate* score carries market information |
| Does news predict the next hour? | **E030** (registered first look, 500 hours, blind until run) | 1h ρ **+0.046 [−0.052, +0.151]**, 6h +0.001, 24h −0.096. Every interval includes zero | anything below ρ ≈ 0.125 at 1h, which this size cannot detect (E025). The plausible size (0.05) is inside the interval. **Neither "news works" nor "news is worthless" follows** |
| When will it be known? | E025 | ρ = 0.05 at 1h needs ≈ 3,140 usable hours, about 2027-02 | — |
| Does it improve the signal? | E001, E017, the live record | the BUY/HOLD/SELL signal has no demonstrated predictive value, with or without news | news moves 5.5% of a signal that has no measured value. Its effect on outcomes in those 33 hours is not tested here: about 30 hours, unregistered, uninterpretable |

## Measurements, assumptions, unknowns

- **Measured:** cost per run and per 30 days; call counts and tokens; the error history; how often news changes the
  signal, and in which direction.
- **Assumed:**
  - list prices with no discount or tier, as of 2026-09-23;
  - one priced run per hour (backup slots exit before any AI call);
  - the 30-day projection assumes the coming weeks' headline volume looks like the last month's.
- **Unknown:**
  - whether news improves predictions (the registered verdict is ≈ 2027-02);
  - the AI call latency;
  - the price on any later date.

## Conclusion

The news call costs about **$7.70 per 30 days** (74% of the AI spend). It works reliably (no failure since
2026-09-29). It changes about **one signal in eighteen**, mostly to HOLD. There is **no evidence yet** that it adds
predictive information, and no evidence that it does not: the only test so far is underpowered by design.

No production change follows from this review, as the master plan requires. Keeping it until the registered verdict
costs about $7.70 a month, and the verdict is what can settle whether it is worth that. Two options exist, and each
would need its own justification, risk assessment and documentation:
- cutting the echo, which saves ~half the news cost but needs an E009 re-run;
- dropping news, which changes the signal under test and resets its comparability.
