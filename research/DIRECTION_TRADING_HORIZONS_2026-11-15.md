# Direction at trading horizons: review, plan and results (2026-11-15)

The owner's brief of 2026-11-15: make this session's focus the direction predictor. Review everything relevant, find
what can be done better or differently, plan the tests, then do a lot of **safe** backtesting of new signals and
combinations.

"Safe" here means:
- development data only, through the governed readers;
- the sealed holdout not opened, and the blind direction track not read;
- every test written down (E039) before any code existed;
- nothing live changed.

## 1. Review: what is known, and where the gap is

**What has been tested** (`research/DIRECTION_RESEARCH_REVIEW_2026-10-21.md` §2): every directional experiment so far
**sampled hourly rows** and judged forward horizons of **1 to 168 hours**. That covers:
- the BUY/HOLD/SELL categories (E001, E002, E017);
- volatility (E003); trend and regime (E004); funding and premium (E005); on-chain (E007);
- taker flow (E008); a fitted logistic (E011); 80 candle-shape signals (E015);
- the direction probability (E032); D1/D2 (E037).

**The findings:**
- a real, tiny 1-hour **reversal** after aggressive buying, below any cost;
- nothing else that holds in both periods.

**Why that is not the end of the question.** E038 showed what the trader actually needs:

| Hold | Needed hit rate to cover Firi's 2.5% round trip |
|---|---|
| 24 h | impossible |
| 7 days | 67–74% |
| 30 days | 57–60% |

The horizons the research measured are exactly the ones that cannot pay for themselves.

**The gaps:**

1. **Horizons beyond 7 days were never measured.** E004's trend features *grew* with the horizon in 2018–23 (the
   30-day trailing return: ρ +0.04 at 24 h, +0.07 at 72 h, +0.10 at 168 h) and the measurement stopped there. In
   2024–25 they were flat. Whether that growth continues, or flips, at 2–4 weeks is unknown.
2. **Hourly rows overstate the evidence at long horizons.** 55,000 hourly rows carry only about 330 independent weeks.
   Daily samples with an explicit effective sample size (`n_eff = days / H`) make the power honest.
3. **No trend rule was ever judged against random timing.** E038's 200-day rule was only a reference, and beating cash
   in a rising market says nothing about timing.
4. **Direction where it matters for a long/cash trader:** the risk of a large fall. It was never measured. Trend
   following's classic case is protection, not prediction.
5. **No fitted daily-feature model at a multi-day horizon.** E011 fitted hourly features at up to 24 h.
6. **The literature's positive single-asset results sit exactly here:**
   - weekly time-series momentum (Liu & Tsyvinski 2021);
   - moving-average ratios (Detzel et al. 2021);
   - the 52-week high (George & Hwang 2004);
   - volatility-scaled trend (Moskowitz, Ooi & Pedersen 2012).

**Considered and rejected:**

| Idea | Why not |
|---|---|
| More hourly features | the space is exhausted and the data worn (the October review) |
| Complex models | no signal for them to find (E020) |
| Flipping the BUY/HOLD/SELL momentum sign to match the reversal | the reversal is below costs, and it would break the live record's comparability |
| Macro | the snapshot is void, and the owner declined a new one |
| Day-of-week effects | no reason for them to persist in a 24/7 market; a classic forking path |
| New data sources | an owner's decision (Rank 4 of the October roadmap) |

## 2. The plan (registered as E039 before any code)

1. **The map.** For past returns over 1, 3, 7, 14, 28, 56, 84 and 182 days, against forward returns over 1, 3, 7, 14
   and 30 days, in both periods: where does reversal turn into momentum? Descriptive only.
2. **Fourteen fixed signals from the literature,** at 1, 7 and 30 days:
   - time-series momentum over 1 day to 26 weeks;
   - the 20- and 200-day ratios, the 50/200 crossover, the 52-week-high ratio;
   - an equal-weight multi-horizon trend score and its volatility-scaled version (the "fit together" without
     fitting);
   - 7-day funding and 7-day taker share.

   They are judged with Holm over 42 tests in 2018–23, and must keep their sign in 2024–25.
3. **One fitted combination:** a walk-forward logistic at 7 days against the leak-free base rate.
4. **Eleven long/cash rules,** decided once a day, at E038's five cost levels:
   - judged against cash, buy-and-hold, exposure-matched buy-and-hold;
   - and **random timing with the same turnover**.
5. **The tail table:** the rate of 30-day falls worse than −20%, by trend state.
6. **Exactness gate first:** the 200-day rule must reproduce E038's result bit for bit.

**Power, computed before anything ran:**

| Horizon | Detectable ρ (80% power), 2018–23 | Detectable ρ, 2024–25 |
|---|---|---|
| 1 day | 0.063 | 0.12 |
| 7 days | 0.17 | 0.32 |
| 30 days | 0.35 | 0.66 |

So 2024–25 can only confirm large effects beyond one day.

**What happens with the result:**
- A **replicated** signal becomes a proposal for a separately registered prospective daily direction track, which is
  the owner's decision.
- Anything weaker is a hypothesis, recorded as such.
- Nothing is adopted into the live system from development data alone.

## 3. Results

*(filled after the one-time run)*
