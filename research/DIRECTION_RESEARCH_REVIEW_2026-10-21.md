# Direction-first research review (2026-10-21)

Written for the user's plan "Protect live evidence and prepare direction-first research", steps 3–5, which make
Bitcoin **direction** the primary long-term research goal. **This is a read-only review and plan.** Nothing was run,
fitted, compared or registered.

**What this review did not do:**
- read the blind direction track (`direction_1h_v1`): no prediction or outcome was looked at;
- open or read the sealed holdout. It stays sealed for evaluation, which is not "untouched";
- change the live signal, the frozen models, the checkpoints or the registrations.

**Where the figures come from:**
- the project's existing records (`research/experiments/`, `research/results/`);
- the committed artefact `agent/direction_shadow/models/direction_1h_v1.json`, whose development-time metadata is
  public in the repository;
- the 500-hour reading and the weekly report of 2026-10-20;
- external sources checked on 2026-10-21, cited with what could and could not be verified.

**Validation wear applies to everything offline.** 31 experiments have examined the development years
(`research/SAFE_SIGNAL_RESEARCH_REPORT_2026-10-17.md`). An offline result on them can generate a hypothesis; it
cannot confirm one.

---

## 1. The current architecture, as the code implements it

### 1.1 How BUY / HOLD / SELL is computed (scoring 0.2.0; `agent/scoring/scorer.py`, `agent/decision/decision.py`)

Each hour, five category scores in [−1, +1] are computed. Each uses only the 250 hours up to the reference candle's
close.

| category | what it measures | formula (full scale) | weight | independent? |
|---|---|---|---|---|
| trend | distance of the close from its 200-hour average | (close − SMA200) / SMA200 ÷ 10%, clamped | 0.25 | no |
| momentum | RSI(14) and the MACD(12,26,9) histogram | mean of (RSI − 50)/50 and (histogram / close) ÷ 0.5%, each clamped | 0.25 | yes |
| volume | above-average volume confirming the last 6 hours' direction | sign(close − close 6 h earlier) × max(0, volume / 20h average − 1), clamped | 0.20 | yes |
| chart pattern | 50h vs 200h average (golden / death cross), and higher-highs / lower-lows over 20 hours | mean of the two ±1 votes | 0.15 | no |
| news | the AI news score: Claude Haiku 4.5 rates each headline of the 24 hours before the cutoff for relevance and sentiment, and the code takes the relevance-weighted mean | — | 0.15 | yes |

- **Overall score:** the weighted mean over the categories that had data. A category without data gets weight 0 and is
  never counted as neutral.
- **Signal:** BUY if the overall score is ≥ +0.15, SELL if ≤ −0.15, otherwise HOLD.
- **Confidence:** (agreement + completeness) / 2.
  - Agreement = 1 − the standard deviation of the *independent* categories' scores (0.5 if fewer than two).
  - Completeness = the share of the nominal weight that had data.
- **No part is fitted to outcomes.** The weights, scales and thresholds were set by hand at design time, deliberately,
  to avoid tuning to history. The only AI part is the news score; the explanation is written after the decision and
  cannot change it (E009).

### 1.2 What BUY, HOLD and SELL mean today

- **What a signal is:** a statement that a hand-set blend of technical indicators and news sentiment is currently
  above +0.15, below −0.15, or in between.
- **What it is not:**
  - not a forecast of a stated horizon;
  - not a probability;
  - not an expected return;
  - not a cost-aware decision.
- **Confidence measures agreement and data coverage, not correctness.** E001: stated 0.7–0.9, observed ≈ 0.48 in
  every bucket. The 2026-10-08 audit: Spearman −0.024 between confidence and being right. The backend contract labels
  the signal "no demonstrated predictive value" everywhere it is shown.

### 1.3 Why historical testing found no predictive value (E001, E002, E004, E017)

1. **No category carries positive information at any horizon** (E002: rank correlations with forward returns at
   1–168 h, both development periods).
2. **The formula has the wrong sign at the only horizon where structure exists.** Momentum and volume are slightly
   **anti**-correlated with the next hour's return (|ρ| 0.02–0.04). That is short-term *reversal*, while the formula
   scores them as *continuation*. The frozen direction model learned the same thing from data: its largest
   coefficients are **negative** on `momentum_score` (−0.097) and on the 1-hour taker-buy share (−0.099).
3. **Trend and chart pattern are one signal counted twice.** They are 69% correlated and built from the same moving
   averages, and neither is consistent across periods.
4. **Longer-horizon trend-following is year-dependent** (E004). Monthly time-series momentum appears in 2019–2021 and
   vanishes or reverses in 2017–18 and 2022–25.
5. **Nothing connects the formula to outcomes.** That was a design choice against overfitting, but it means the
   thresholds and weights encode no measured relationship.

**Live, descriptive** (weekly report 2026-10-20; not a verdict):
- 1h acted accuracy 0.500 (n = 446) against 0.501 naive;
- edge −0.009% [−0.080%, +0.054%];
- confidence ECE 0.425.

### 1.4 The separate probabilistic direction model (`direction_1h_v1`, E032 → E034, blind)

- **Target:** P(the next 1h candle closes above the reference close).
- **Model M:** an L2 logistic regression (C = 0.1, no calibration step, by E032's design) on eight inputs:
  - the four technical category scores (not news);
  - `tr_mean_14_rel`, the relative true range;
  - `trades_rel_168h`, trade intensity;
  - the 1h and 6h taker-buy share.
- **Fit:** 64,156 development hours, 2017-08 → 2025-06-29, purge 25 h. The holdout is never crossed.
- **References, scored on the same hours:** F, the 1h taker-buy share alone; B, the base rate (0.5097).
- **Development evidence (E032, walk-forward out-of-sample):**
  - Brier skill against the base rate +0.0038 (exploration) / +0.0043 (validation), positive in 8 of 8 years;
  - well calibrated (ECE 0.006);
  - accuracy 0.525 against 0.509 naive (exploration).
  - The artefact's in-sample Brier: M 0.24887, F 0.24935, B 0.24991.
- **What it is:** a real, stable, *tiny* 1h reversal effect. Most of it is the one feature (H_b fails). It is
  economically negligible: its gross edge is 1–13% of a 0.10% round trip.
- **What is being collected:** prospectively, blind, in its own tables (117 eligible hours on 2026-10-20). Readings at
  1,000 and 3,000 hours (no verdict), and the verdict at 6,500 (≈ 2027-07-13) under `research/DIRECTION_TRACK.md` §7.
- **What it cannot establish:**
  - that M is better than F (E033: 15,000–188,000 hours needed);
  - usefulness for trading (§9 only describes economics);
  - anything about calm versus volatile markets, if every hour stays calm.

### 1.5 Why move size worked and direction did not

**Move size:** volatility clusters, and the clustering is strong, persistent and economically unexploitable. That is
why it survives in markets.
- Recent volatility predicts the next hour's move size with ρ up to 0.45, and trade intensity up to 0.30 (E003, E008).
- The model beats a free 24h-EWMA rule 2.47× on validation (E019). Most of its skill is knowing the current volatility
  *level*, and about +0.074 is its own timing (E021).
- Prospectively it has kept its edge: at 500 hours, Brier gain +0.089 [+0.019, +0.137] and ahead of the EWMA rule. All
  of those hours were calm.

**Direction:** any reliable directional pattern is a profit opportunity, which traders remove. What remains at one hour
is the reversal family, smaller than costs.

### 1.6 Could separating direction, magnitude and the decision help?

- **Conceptually, yes.** A decision needs three different things:
  - a direction probability, P(up);
  - a size expectation, from the move-size model;
  - a rule that turns both into an action, net of costs, with HOLD as the abstention.

  Today's formula mixes all three into one hand-set score without a horizon.
- **But the evidence warns against a naive combination.** E011 found the 1h direction edge "earned on small moves and
  lost on the largest ones". So gating direction on large expected moves may *remove* the edge rather than amplify it.
- The two probabilities come from different models with different uncertainty, and their errors are not independent.
- **Any combination needs its own registration and its own prospective record.** DIRECTION_TRACK §7 already says the
  direction track is never combined with move size until each component has credible prospective evidence.

---

## 2. What has already been tested: do not repeat

| idea | where | result | status |
|---|---|---|---|
| the five technical/news categories as direction signals | E001, E002, E017 | no positive information at 1–168 h; a 1h reversal of \|ρ\| 0.02–0.04 | **closed** for the signal |
| category scores added to the direction model (D1) | E037 | validation +0.000113 [−0.000169, +0.000401], INCONCLUSIVE | **closed**, no variants |
| volatility group for direction | E003 | none (strong for magnitude only) | closed |
| long-horizon trend / regime (7–90 d returns, 50/200-day distance) | E004 | year-dependent | closed |
| funding rate (24h contrarian) | E005 | right sign in every year 2019–23, absent 2024–25 | **registered live re-test** at 6 live months (≈ 2027-03-21) |
| premium index | E005 | none | closed |
| macro (dollar, yields, equities, oil, gold) | E006 | **VOID**: the snapshot held quarterly or monthly bars read as daily | unusable until a valid daily source exists (the user declined one, 2026-10-17) |
| on-chain activity | E007 | 0 of 50 | closed |
| candle microstructure: taker-buy share, trade intensity | E008 | direction: reversal 1–6 h (\|ρ\| 0.02–0.05); magnitude: strong | reversal is in M and F |
| fitted direction logistic, 1/6/24 h, two feature sets | E011 | 0 of 15 pass | closed |
| candle shape, streaks, range position, illiquidity, trade size | E015 | 0 of 80; the reversal family, `up_streak_6` strongest (ρ −0.080 / −0.060); 0.4× the cost of acting | closed |
| `up_streak_6` added to the direction model (D2) | E037 | NOT_SUPPORTED: over-confident on validation (slope 0.65) | **closed** |
| liquidity pair for move size (MS-A) | E036 | NOT_SUPPORTED | closed |
| fancier model families (squared/product terms, gradient-boosted trees) | E020 (move size) | statistically 1.04×, practically equivalent; the polynomial fails calibration | the logistic stands |
| intraday calibration variants | E028, E031, E035 | not candidates | **line closed** |
| news value | E009, E025, E030 | reliable scorer; first look inconclusive (ρ +0.046 [−0.052, +0.151]) | **verdict at 3,140 usable hours** (≈ 2027-01-29 to 02-03) |
| the sealed holdout (E014, E023) | — | registered, never run | the user's decision; the only clean historical arbiter left |

---

## 3. External research: what it says, how strong it is, what transfers

**Evidence levels:**
- **J**: peer-reviewed journal, verified from its abstract;
- **J\***: journal, but verified only from a secondary description;
- **P**: preprint;
- **R**: record only, content not accessible.

None of these is an independently verified prospective study. Publisher pages (ScienceDirect, Springer, SSRN) refused
automated access. **Nothing below claims more than the cited abstract or record states.**

| # | study | target and horizon | data | method and baselines | out-of-sample? | what it found | transfers to our hourly BTC direction? |
|---|---|---|---|---|---|---|---|
| 1 | Gradojevic, Kukolj, Adcock & Djakovic, "Forecasting Bitcoin with technical analysis: A not-so-random forest?", *Int. J. Forecasting* 39(1), 2023 ([IDEAS](https://ideas.repec.org/a/eee/intfor/v39y2023i1p1-17.html)) — **J** | Bitcoin returns, **hourly and daily** | hourly and daily BTC; exchange and period not verified | non-linear models (random forest among them) on trend, momentum, volume and sentiment indicators; random-walk benchmark | yes (details not verified) | prices are **"weakly efficient at the hourly frequency"**; at the **daily** horizon technical indicators with non-linear models beat the random walk; predictor importance shifts over time | **Agrees with us at hourly.** The daily result is a different target; our 24h tests (E001, E011) found nothing, and E004 found trend year-dependent |
| 2 | Anastasopoulos, Gradojević, Liu, Maynard & Tsiakas, "Order flow and cryptocurrency returns", *J. Financial Markets*, 2026 ([doi](https://doi.org/10.1016/j.finmar.2026.101047)) — **J\*** | cross-sectional crypto returns, **daily and weekly** | "world" order flow from 11 fiat currencies across exchanges; 82 cryptocurrencies | panel regressions; machine-learning forecasts; macro fundamentals as the comparison | stated | world order flow explains about 11% of daily (20% of weekly) returns **in the same period**; out of sample it beats macro fundamentals; long-short portfolios report up to 0.79% a day of alpha, Sharpe 3.63 | **Not directly.** It is cross-sectional (ranking 82 coins), daily, and built on multi-exchange fiat order flow we do not have. A long-short alpha across coins says nothing about whether one coin's next hour goes up |
| 3 | Raffaelli, Cestari, Marazzina & Formentin, "Forecasting Bitcoin price movements using multivariate Hawkes processes and limit order book data", *Decisions in Economics and Finance*, 2026 ([doi](https://doi.org/10.1007/s10203-026-00570-z)) — **J** | the sign of **short-term** BTC/USD returns (order-book event time) | limit-order-book event streams from one centralized exchange; period not verified | two multivariate Hawkes designs; the hybrid (Hawkes + continuous-time output-error model) is compared with the pure Hawkes | reported, with simulated trading | the hybrid beats the pure Hawkes in accuracy and simulated profit; computational cost assessed | **No.** It is tick-level, needs order-book event data we neither hold nor collect, and its baseline is a sibling model, not a simple rule. Free historical order-book data does not exist in our governed set |
| 4 | Berger & Koubová, "Forecasting Bitcoin returns: Econometric time series analysis vs. machine learning", *J. Forecasting*, 2024 ([doi](https://doi.org/10.1002/for.3165)) — **J** | **daily** Bitcoin returns | daily BTC | econometric time-series models against machine learning, including deep and LSTM layers | in and out of sample | machine learning beats the econometric benchmarks; **deep or LSTM layers do not improve daily precision**; the authors favour a simple recurrent network | **Weakly.** Daily. Complexity beyond a simple model did not help, which matches E020 |
| 5 | Yae & Tian, "Out-of-sample forecasting of cryptocurrency returns: A comprehensive comparison of predictors and algorithms", *Physica A* 598, 2022 ([IDEAS](https://ideas.repec.org/a/eee/phsmap/v598y2022ics0378437122002928.html)) — **J** | **daily** returns of BTC, ETH and XRP | daily | predictors from the literature; shrinkage, combinations, monitoring, machine learning, and economically motivated methods | **yes, the paper's focus** | attention and volume predictors **fail out of sample**; only the change in stochastic correlation with stocks helps (out-of-sample R² about 2.7% for BTC); economically grounded methods beat generic machine learning | **The method lesson transfers:** in-sample predictors often die out of sample. The one predictor that survives is daily and cross-asset, and needs valid daily equity data (our macro snapshot is void) |
| 6 | Wang, Zeng, Li & Wang, "The Training Set Delusion: Machine Learning Overfitting in Bitcoin Return and Volatility Prediction", SSRN working paper, 2025 ([doi](https://doi.org/10.2139/ssrn.5797242)) — **R** | (not verifiable) | — | — | — | the abstract and paper could not be read (SSRN refused, no indexed abstract); **no finding is attributed to it here** | — |
| 7 | Kitron & Wengrowicz, "Short-horizon mean reversion in cryptocurrency markets: a matched cross-market measurement", arXiv 2608.21888, 2026 ([arXiv](https://arxiv.org/abs/2608.21888)) — **P** | next **15-minute** bar direction | 183 Binance pairs against 187 US stocks and ETFs | betting against the previous candle; permutation null; a frozen six-month holdout | **yes**, including a frozen holdout | reversal in about 90% of crypto pairs against 2.7% of equities, in every coin-year since 2021; strongest **after aggressive taker flow**; the gross edge is about 1.3 bp against a 5 bp round trip, **below costs** | **The closest match to our own findings** (E008, E015, E032): a real reversal after taker-buy pressure, statistically clear and economically insufficient. An independent outside check that our 1h signal is the right *kind* of thing, and that it is small |
| 8 | Kim & Hansen, "The Quarter-Hour Effect: Periodic Algorithmic Trading and Return Predictability in Cryptocurrency Futures", arXiv 2607.09426, 2026 ([arXiv](https://arxiv.org/abs/2607.09426)) — **P** | returns over **4–12 hours** after quarter-hour openings | trades of six Binance **perpetual futures** | order imbalance at quarter-hour openings | stated for opening returns | opening order imbalance predicts 4–12 h returns; much weaker at finer clocks; effect sizes and costs not in the abstract | **A hypothesis only.** It needs futures trade data that is not in our pipeline. It is the one source pointing at a horizon (4–12 h) and an input (futures order imbalance) we have not tested |
| 9 | Liu & Tsyvinski, "Risks and Returns of Cryptocurrency", *Review of Financial Studies* 34(6), 2021 ([IDEAS](https://ideas.repec.org/a/oup/rfinst/v34y2021i6p2689-2727..html)) — **J** | crypto returns (the published abstract gives no horizon) | — | factor and predictive regressions | — | crypto-specific factors; **time-series momentum**; investor attention forecasts returns | Contrast with #5: attention fails **out of sample** there. Our own long-horizon momentum test (E004) found it year-dependent |

### What the literature, read together, says

1. **At one hour, direction is close to efficient.** #1 says so directly. #7 and our E008/E015/E032 find the same small
   reversal after aggressive buying: real, consistent, below costs.
2. **The positive results sit elsewhere:**
   - daily or weekly horizons (#1, #4, #5, #9);
   - many-coin cross-sections (#2);
   - tick-level order-book event time (#3);
   - futures order flow at 4–12 h (#8).

   **None of them is evidence that next-hour BTC direction is predictable** beyond the faint reversal we already
   measure.
3. **Complexity rarely buys out-of-sample accuracy.** #4 (no LSTM gain), #5 (generic machine learning loses to
   economically grounded methods) and our E020 point the same way.
4. **In-sample predictors often fail out of sample.** Attention is a case: #9 in sample against #5 out of sample.
   This is exactly why this project registers first, uses walk-forward, and confirms only prospectively.
5. **What could be genuinely new information for us** is data we do not have:
   - true order-book imbalance;
   - futures order flow;
   - multi-exchange order flow.

   Free historical versions are not in the governed dataset. Any honest test would start with prospective
   collection.

---

## 4. A prioritised roadmap, with realistic expectations

**The honest expectation:** a large improvement in next-hour BTC direction is unlikely. The project's own evidence
across ~10 directional experiments, and the outside evidence, agree on that. The defensible goals are smaller:
- a **calibrated** direction probability that beats the base rate on new data, which the registered track decides;
- a BUY/HOLD/SELL that is honest about horizon, probability and cost.

Each candidate is assessed on ten points:
1. the problem it addresses;
2. why it might help;
3. the evidence;
4. whether it was already tested;
5. the data and infrastructure it needs;
6. its cost and complexity;
7. what could go wrong;
8. the honest test;
9. what would reject it;
10. when.

### Rank 1: let the registered prospective evidence arrive (now). **Recommended.**

1. **Problem:** we do not know whether *any* component works on new data.
2. **Why it helps:** prospective data is the only evidence not worn by reuse.
3. **Evidence:** E024 and E033 sized the readings. The 2,000-hour E012 verdict is sound for move size, and the 6,500-hour
   verdict is about 80% powered for direction.
4. **Already tested?** It is the registered plan.
5. **Data:** already being collected.
6. **Cost:** nothing beyond operations.
7. **What could go wrong:**
   - the calm market may leave the readings regime-limited;
   - **no database backup exists**: losing the project loses the evidence (STATUS, unresolved risk).
8. **Honest test:** the readings, exactly as registered.
9. **Rejection:** n/a.
10. **When:**
    - move size at 2,000 h ≈ 2026-12-14;
    - direction looks at 1,000 h ≈ 2026-11-26 and 3,000 h ≈ 2027-02-17;
    - the direction verdict at 6,500 h ≈ 2027-07-13;
    - the news verdict ≈ 2027-01-29 to 02-03;
    - move size at 5,000 h ≈ 2027-04-18.

### Rank 2: redesign BUY / HOLD / SELL as a decision layer, on paper only, registered before any data. After the 2,000-hour reading.

1. **Problem:** today's signal has no horizon, no probability and no cost model, and its momentum sign contradicts
   the measured reversal.
2. **Why it helps:** separates the question (P(up) at a fixed horizon, plus expected move size) from the action, which
   comes from an explicit rule:
   - act only when the expected net return exceeds a stated cost;
   - otherwise HOLD.
3. **Evidence:** E001, E002 and E011 (why the current form fails). DIRECTION_TRACK §9 (cost framework). #7 (the edge
   is below costs at short horizons, so the abstention rule matters more than the forecaster).
4. **Already tested?** No decision layer has been tested. The *inputs* have (E032, E012), and the conclusion so far is
   that the honest decision at 1h is almost always HOLD.
5. **Data:** existing components only. It would read the frozen models' probabilities, never refit them.
6. **Cost:** a design document and a registration. Later, its own isolated shadow track, which needs a separate
   authorisation.
7. **What could go wrong:**
   - combining two weak signals manufactures false confidence;
   - gating on size may remove the direction edge (E011);
   - the result could be "always HOLD", which is honest but uninteresting.
8. **Honest test:** rules fixed before any data, then prospective only. Compare net of costs against always-HOLD,
   buy-and-hold, and a base-rate decision rule.
9. **Rejection:** not better than always-HOLD and the base-rate rule net of costs at a pre-registered size.
10. **When:** design after the 2,000-hour reading. Evaluation only after the direction verdict says the input is worth
    using.

### Rank 3: the funding-rate re-test (already registered). At about 2027-03-21.

1. **Problem:** E005's contrarian 24h funding effect held in 2019–23 and vanished in 2024–25.
2. **Why it helps:** it is the most consistent directional pattern the programme has seen, with an economic mechanism
   (crowded longs).
3. **Evidence:** E005. The literature on crowded positioning.
4. **Already tested?** Yes, offline. The live confirmatory re-test is registered as a watch item at 6 live months.
5. **Data:** in the governed development snapshot. **The live path does not collect funding.** The re-test needs the
   live period's funding history from Binance's public API, a download that needs authorisation at that time.
6. **Cost:** small.
7. **What could go wrong:**
   - 24h windows give few independent observations in 6 months, so power is low;
   - the effect was already absent in 2024–25.
8. **Honest test:** exactly as registered, once.
9. **Rejection:** the registered criterion fails.
10. **When:** at 6 months (≈ 2027-03-21).

### Rank 4: genuinely new information, collected prospectively. Long-term, and only if the user decides to collect new data.

1. **Problem:** every candle-derived input has been examined, and the development data is worn.
2. **Why it helps:** order-book imbalance and futures order flow carry information that candles do not (#2, #3, #8).
3. **Evidence:**
   - journal evidence at daily and cross-sectional horizons (#2);
   - tick-level evidence (#3);
   - preprint evidence at 4–12 h in futures (#8).

   **None at next-hour spot BTC.**
4. **Already tested?** Only the candle proxy (taker-buy share, E008), which shows reversal.
5. **Data:** not in the governed dataset, not collected live, and free history does not exist. It would mean a new
   collection job and new storage, which is new infrastructure and a user decision.
6. **Cost:** moderate, ongoing. Months of collection before a single test.
7. **What could go wrong:**
   - API changes;
   - data gaps;
   - survivorship of the collection design;
   - a result that only holds in futures or at tick scale.
8. **Honest test:** register the features and the target *before* collection. Collect blind. Test once at a size fixed
   by a power analysis, as E033 did.
9. **Rejection:** no gain over F and B at the registered size.
10. **When:** after the direction verdict, if the user wants to invest in new data.

### Rank 5: a daily-horizon direction target. Defer.

1. **Problem:** the outside positive results are mostly daily.
2. **Why it helps:** less noise per observation; trend and momentum effects live there (#1, #9).
3. **Evidence:** daily journal results (#1, #4, #5), mostly against weak baselines.
4. **Already tested?** Yes, at 24h: E001, E011 (no pass) and E004 (year-dependent momentum).
5. **Data:** candles exist. But the development years hold only about 2,800 independent days, already reused.
6. **Cost:** low to build, high in evidence. A prospective daily track needs years for power.
7. **What could go wrong:** over-reading a regime (the 2019–21 momentum); multiple testing across horizons.
8. **Honest test:** prospective only, registered.
9. **Rejection:** at the registered size, no skill over the base rate.
10. **When:** not before the hourly direction verdict.

### Rank 6: recalibrating the direction probability. Only if the verdict asks for it.

1. **Problem:** E032's model is uncalibrated by design (exploration slope 1.22).
2. **Why it helps:** a calibrated P(up) is what a decision layer needs.
3. **Evidence:** the E013 precedent for move size.
4. **Already tested?** No. The verdict's calibration guard decides whether it matters.
5. **Data:** development data only.
6. **Cost:** low.
7. **What could go wrong:** calibrating to noise; a 4th or 5th look at the same rows.
8. **Honest test:** only if the 6,500-hour verdict is "SKILL BUT MISCALIBRATED". Then it is a new registered experiment
   and a new record from zero, as §7 already says.
9. **Rejection:** the verdict is IMPROVEMENT, so it is not needed; or NO IMPROVEMENT, so it is pointless.
10. **When:** after July 2027.

### Rejected or postponed, with reasons

- **More complex models for hourly direction** (random forests, boosting, LSTM, Transformers): **reject now.**
  - There is no signal for them to find beyond a ~0.4% Brier improvement.
  - E020 found boosting practically equivalent even where signal exists, and #4 found no LSTM gain at daily.
  - Every extra parameter is fitted on worn data.
- **Another broad offline feature search on the development years: reject.**
  - 55+ candidate features and ~10 directional experiments have examined these years.
  - E036 and E037 were the last authorised batch, and both are closed.
  - A new "pass" there would be hypothesis-generating at best and likely a selection artefact. **The development data
    is now too heavily reused to justify another broad search.**
- **Re-running closed lines under new names: reject.** These are MS-A, D1, D2, intraday calibration, the E006 macro
  set, `up_streak_6` and the shape group.
- **Copying published models: reject.**
  - Tick-level Hawkes (#3) answers a different question with data we lack.
  - Cross-sectional order-flow alpha (#2) does not apply to one asset.
  - Daily random forests (#1) contradict nothing we found, because hourly was weakly efficient there too.
- **Macro (cross-asset correlation, #5): postpone.** It needs a valid daily equity source; the user declined a new
  macro snapshot on 2026-10-17. Its horizon is daily.
- **Using the holdout to choose among ideas: never.** E014 and E023 are the one-time arbiter, opened only by the user
  and never for search.

---

## 5. A long-term strategy for a more reliable direction predictor

1. **Treat next-hour direction as nearly efficient.** The target is a *calibrated* probability that beats the base
   rate on new data, not a high hit rate.
2. **Confirm before building.** Only components with a prospective verdict feed a decision layer: move size from
   2,000 h, direction at 6,500 h, news at 3,140 h.
3. **Look for new information, not new transformations of the same candles.** Prospective collection of order flow is
   the credible long-term avenue (Rank 4). Its cost is time.
4. **Make BUY/HOLD/SELL a decision, not a score.** Give it an explicit horizon, probability inputs and costs, with HOLD
   as abstention (Rank 2). Judge it against always-HOLD and buy-and-hold net of costs.
5. **Template for any future research plan** (none is proposed now):
   - an experimental budget of one to two hypotheses, each run once;
   - falsification criteria, practical thresholds and stop rules written first;
   - baselines: B, F, the frozen M, and for decisions always-HOLD and buy-and-hold net of costs;
   - time-ordered walk-forward with a purge ≥ the horizon;
   - Holm correction across hypotheses;
   - development results labelled hypothesis-generating;
   - confirmation only in an isolated prospective track sized by a power analysis, or once on the holdout by the
     user's decision;
   - economics judged only as DIRECTION_TRACK §9 does.
6. **A favourable historical result never authorises production use or a claim of profit.** Automated execution stays
   NOT ACTIVE (`docs/FUTURE_EXECUTION_ARCHITECTURE.md`).

**The safest next action** is to change nothing predictive, keep the weekly audits running, and read each registered
checkpoint as it arrives. The next legitimate decision points:
- the direction first look (≈ 2026-11-26, no verdict);
- the move-size 2,000-hour verdict (≈ 2026-12-14). After it, the Rank 2 design could be considered.

**The largest present risk is operational, not statistical:** without a database backup, the evidence everything
above waits for could be lost.
