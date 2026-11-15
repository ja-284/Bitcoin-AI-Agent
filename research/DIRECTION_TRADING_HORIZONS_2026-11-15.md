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

## 3. Results (E039, run once at `909923d`, 320 s)

**The checks first:**
- The 200-day rule reproduced E038 exactly: 10 of 10, difference 0.0.
- No tripwire fired.
- `research/HOLDOUT_ACCESS.log` does not exist.
- Full tables: `research/results/E039/daily_direction.md`.

### 3.1 The map: where reversal turns into momentum

Spearman ρ between the past return over L days and the forward return over H days. An asterisk means the interval
excludes zero.

| Lookback | 2018–23: 1 d | 3 d | 7 d | 14 d | 30 d | 2024–25: 1 d | 3 d | 7 d | 14 d | 30 d |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 day | **−0.074*** | −0.010 | −0.005 | +0.011 | +0.035 | −0.064 | −0.039 | −0.048 | −0.008 | −0.001 |
| 7 days | −0.000 | +0.017 | +0.011 | +0.064 | +0.105 | −0.046 | −0.054 | −0.033 | +0.010 | +0.040 |
| 28 days | +0.033 | **+0.070*** | **+0.100*** | **+0.135*** | +0.182 | −0.011 | −0.010 | +0.045 | +0.070 | −0.036 |
| 56 days | **+0.050*** | **+0.083*** | +0.093 | +0.087 | +0.136 | −0.012 | −0.033 | −0.045 | −0.051 | −0.037 |
| 84 days | +0.040 | +0.067 | +0.080 | +0.095 | +0.139 | −0.008 | −0.041 | −0.079 | −0.124 | −0.163 |
| 182 days | +0.006 | +0.009 | +0.005 | −0.006 | +0.025 | −0.067 | **−0.121*** | −0.176 | −0.265 | **−0.420*** |

**What it shows:**
- **One day:** a reversal in both periods, the same family as the hourly reversal.
- **2018–23:** momentum from 1–2-month lookbacks at 3–30-day horizons.
- **2024–25:** no momentum, and **reversal** at 3–6-month lookbacks. A strong half-year was followed by a weaker
  month.
- The sign of the multi-week effect **flipped between the periods**, as E004 found at shorter horizons. Trend is a
  property of the regime, not a stable predictor.

### 3.2 Fourteen signals at 1, 7 and 30 days

**0 of 42 tests survive Holm.**
- The best is the 1-day reversal: −0.074 [−0.121, −0.025] in 2018–23 and −0.064 [−0.142, +0.014] in 2024–25. Its
  Holm-adjusted p is 0.29.
- Every other test has an adjusted p of 0.99 or more.
- No LEAD and no REPLICATED pair.
- Funding over 7 days at 30 days kept its contrarian sign in both periods (−0.17, −0.11), but both intervals are wide
  and include zero. The registered live re-test (≈ 2027-03) is unchanged.

### 3.3 Fitting them together makes it worse

The walk-forward logistic M7 (13 signals, 7-day direction):

| Period | Brier M7 | Brier base rate | Base − M7 [95% CI] | Calibration slope |
|---|---|---|---|---|
| 2020–23 | 0.2802 | 0.2528 | **−0.0274 [−0.0430, −0.0117]** | −0.19 |
| 2024–25 | 0.2468 | 0.2471 | +0.0003 [−0.0075, +0.0074] | 0.44 |

- In 2020–23 it is clearly **worse than the base rate**, and its coefficients swing between years: NOT_SUPPORTED.
- Its trading rule was below random timing in 2020–23 (6th percentile) and above it in 2024–25 (100th). A model that
  is anti-skilful in one period and skilful in the next is fitting regimes, not finding skill.

### 3.4 Trading rules at Firi's realistic cost (1.25% a side)

| Rule | Net 2018–23 | Net 2024–25 | Actions a year | Beats random timing (percentile, 2018–23 / 2024–25) |
|---|---|---|---|---|
| 50/200 crossover | **+366%** | **+41%** | 2–3 | 85 / 21 |
| 200-day average | +351% | +21% | 6–14 | 92 / 15 |
| 84-day return | +151% | +58% | 13–15 | 92 / 61 |
| 182-day return | +87% | +103% | 3–9 | 72 / 31 |
| 28-day return | +214% | −32% | 29–40 | **100** / 30 |
| Trend score | +9% | −33% | 38–46 | **99** / 37 |
| 7-day return | −95% | −61% | 62–70 | 84 / 15 |
| Fitted model M7 | −90% | +36% | 38–57 | 6 / **100** |
| Buy-and-hold | +570% | +142.5% | — | — |

- **No rule is a trading candidate.**
- The low-turnover rules survive Firi's costs in both periods. But they trail buy-and-hold in both, and their timing
  is not distinguishable from random in 2024–25.
- In 2018–23 their maximum drawdown (68–79%) was about buy-and-hold's (~77%), so they did not protect much either.
- The faster rules showed real momentum timing in 2018–23 (the 99th–100th percentile without costs), but costs eat it
  and 2024–25 did not repeat it.

### 3.5 The risk of a large fall

The share of days followed by a 30-day fall worse than −20%:
- **2018–23:** 10.1% overall; 9.8% above the 200-day average and 10.4% below it, so no difference. By the trend score,
  5.5% at +1.0 against 15.7% at −0.6, in the expected direction, but the intervals overlap.
- **2024–25:** one such day in 517, so it cannot be tested.

### 3.6 Verdicts, by the registered rules

| Hypothesis | Outcome |
|---|---|
| H1, the map | holds, with the twist that 2024–25 reversed |
| H2, no replicated signal | holds |
| H3, the model does not beat the base rate | holds |
| H4, no trading candidate | holds |
| H5, the trend state raises large-fall risk | not supported as stated |

## 4. What this means for the direction predictor

1. **The evidence now covers 1 hour to 30 days.** Together, E001–E039 say the only directional structure with the same
   sign in both development periods is **short-term reversal**: after a rise over the last hour or day, slightly
   weaker returns follow. It is real and repeatable, and far too small for any realistic cost (E015, E032, E038,
   E039).
2. **Longer-horizon direction exists only as a regime.** Momentum ruled 2018–23 (driven by 2019–21 and the 2022 crash)
   and reversal ruled 2024–25. Two big bear markets carry most of the value a trend rule showed in development. Two
   events cannot tell whether that repeats.
3. **More fitting is not the fix.** The combined model was worse than knowing nothing in 2020–23. With two regimes in
   the data, a flexible model learns the regime it was trained in.
4. **So another offline search on these candles is not justified.** It would mostly add false positives to worn data.
   This study is the last broad one I would run on them.

## 5. Recommendations, ranked

1. **Keep the registered prospective readings as the arbiter.**
   - The direction track's first look at 1,000 eligible hours (≈ 2026-11-26; no verdict);
   - the funding re-test (≈ 2027-03);
   - the direction verdict at 6,500 hours (≈ 2027-07).

   Nothing here changes them.
2. **The only path with real potential is new information, collected prospectively** (the October review's Rank 4):
   - order-book imbalance from Firi's and Binance's free public books (the session's spread sampler is a first piece);
   - futures funding and open interest.

   Register the features and target before collecting, then test once at a size from a power analysis. This needs
   the owner's go-ahead (new collection job, new storage, no cost).
3. **For the trader (`LOW_FREQUENCY_PLAN.md`):** nothing here opens its cost gate. If the owner ever wants a trend
   component, the 50/200 crossover is the one rule that survived Firi's costs in both periods with 2–3 actions a
   year. But it is a regime and risk choice, not a predictor. It trailed buy-and-hold in both periods and could not be
   told from random timing in 2024–25. It would need its own registration and a prospective record, and the decision
   is the owner's.
4. **Not recommended:**
   - fitted daily models (M7);
   - fast trend rules (costs);
   - the 1-day reversal as a trading signal (costs);
   - further candle-based searches.
