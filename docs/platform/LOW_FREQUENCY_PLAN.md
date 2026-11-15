# Low-frequency trading: investigation, evidence and plan (2026-11-15)

The owner's brief of 2026-11-15: before any Firi account is connected, find out how the trader should become a
genuinely low-frequency one, with at most **1 or 2 trades a day**, and which limit the evidence supports. Investigate
first, register the tests, then plan.

**What this document is.** An investigation of the real code, one pre-registered experiment on real data (**E038**:
registered `86393c3` before any code, code `3748bba`, a loader fix `d2ebcba`, result in the commit that adds this
file), a design, measurable test goals and a roadmap.

**What did not change.** No production table, no workflow, no key, no order, no setting. Nothing in the prediction
engine, the frozen models, the direction track, the registered checkpoints or the holdout changed.
`research/HOLDOUT_ACCESS.log` still does not exist.

**The owner's 2026-11-15 rule, recorded here.** Any move to real money is a separate, explicitly approved stage. This
replaces the 2026-11-14 "go live after tests" wording for the first order.

---

## Summary

1. **The cap is not the problem; costs are.** Firi charges **0.7% on each buy and each sell** (official price list,
   verified today). Its BTC/NOK spread measured **0.9–1.3%**. A buy followed by a sell therefore costs about
   **2.5%**, which is 1.6% at best and 3.2% on bad hours.
2. **On 6.6 years of real history, rule-1.0 as built would have lost about 93% at Firi's costs.** That is true at 4, 2
   or 1 trades a day. Even 1 a day allows ~170–200 trades a year. That costs more than the stake, and the signal
   earns nothing to pay for it.
3. **No low-frequency design tested shows an edge after Firi's costs.** Four designs were tested, each at 1 and 2 a
   day: signal persistence, a daily vote, strong scores only, and a cost-aware gate. None was supported in either
   period. The best one, strong scores only, came out at −3% in 2024–25 and −24% in 2018–23 at the realistic cost.
   Its intervals include zero, and it is no better than random timing.
4. **A correctly priced cost filter never trades with today's signals.** The best signal state's estimated 24 h
   return is about **+0.75%**. That is half the cheapest Firi round trip and a third of the realistic one. For a
   24-hour hold, no hit rate can cover 2.5%. A 7-day hold would need 67–74% correct calls, and a 30-day hold 57–60%.
   The current signal is right 47–49% of the time.
5. **1 vs 2 a day:** the data cannot choose on predictive grounds. Neither limit shows timing skill or a net gain.
   The measurable difference is cost: the 1-a-day limit trades less in every comparison. By the rule registered in
   advance, **the default is 1 per rolling 24 hours, as a cost decision, not an edge**.
6. **Recommended design:** analyse every hour and act only when an opportunity's expected return over a stated
   holding period clears the full round-trip cost. Risk exits stay outside the allowance. Every opportunity is
   recorded, including the rejected ones. **Under today's evidence this design will hold its position and not
   trade.** That is the evidence-based outcome, not a defect.
7. **What can be built now at NOK 0, with no key and no money:**
   - the corrected core and the new strategy;
   - storage that makes duplicate orders impossible;
   - Firi hardening, a public order-book sampler, and paper trading at Firi's real quotes.
8. **What cannot be shown quickly:** a real edge at this frequency. Detecting +1% per trade cycle needs hundreds of
   cycles, which means years. Paper trading can prove the software and the costs in weeks, but not an edge.

---

## 1. Current-state assessment (verified in the code, not taken from the report)

| Area | What it actually does (file) | Fit for 1–2 trades a day? |
|---|---|---|
| Hourly analysis | GitHub Actions, dispatched at :12 by Supabase `pg_cron`, backup slots at :07/:22/:37/:52 (`.github/workflows/hourly.yml`) | **yes**: keep it |
| BUY/HOLD/SELL | Weighted mean of five category scores: trend 0.25, momentum 0.25, volume 0.20, chart pattern 0.15, news 0.15. BUY at ≥ +0.15, SELL at ≤ −0.15 (`agent/scoring/scorer.py`, `agent/decision/decision.py`). No horizon, no probability, no cost | **no**: no demonstrated edge at any horizon (E001, E017) |
| Signal stability | It changes about **3.7 times a day**. The median run is **3 hours**, and 67% of runs last under 6 hours. This is the same in development and live (E038) | **no**: it describes hourly noise, not daily opportunities |
| Confidence | (agreement + completeness) / 2. Agreement is 1 − the spread of momentum, volume and news. It never looks at an outcome. Stated 0.7–0.9 against a hit rate of 0.48–0.50 (E017) | **no**: correctly disabled |
| Move-size model | Calibrated P(next-hour move > 0.25%); real prospective skill (+9.8% Brier skill at 1,258 h). **Horizon: 1 hour** | **partly**: a risk input for sizing, not a direction |
| Direction model | Blind until its readings (≈ 2026-11-26, 2027-02, 2027-07); must not be used or shown | **not available** |
| Trader (`agent/execution/strategy.py`, `rule-1.0`) | Each hour, this hour's signal becomes a target exposure. Size = min(volatility factor, move factor). It resizes when a change exceeds 20% of the cap. No reversal within 6 h. At most 4 fills in any **rolling** 24 h | **no**: it reacts to every flip; its only cost control is the 20% band |
| Limits | Verified: `HARD_MAX_ALLOCATION` 500 in code; the owner's cap (150) is a setting; daily loss 10% vs 24 h ago; drawdown 30%; data-quality veto; halt until the owner resumes | **yes**: keep them all |
| Engine (`agent/execution/engine.py`) | Client order id `rule-1.0:<hour>`; reconciliation halts trading when the venue holds less than the ledger; it persists nothing itself | **partly**: idempotency depends on storage that does not exist yet |
| Firi adapter (`agent/execution/firi.py`) | A limit order through the best price (ask × 1.0025 / bid × 0.9975); rests 3 s, then cancels the remainder; the fill comes from balance changes; no retry | **partly**: see weaknesses 5–6 |
| Storage, hourly step, key | **none exist** | to build |
| Backtest tooling | `agent/research/replay.py` (point in time, verified); now E038's simulator, proven bit-identical to the real engine | **yes** |

## 2. Main weaknesses for a 1–2-trades-a-day system

1. **Every hourly signal is treated as an instruction.** The strategy has no memory of signal history, persistence or
   strength, and no idea of a holding period.
2. **No cost model in the decision.** Nothing compares an expected gain with the ~2.5% round trip. Only the 20% resize
   band touches cost.
3. **The horizons do not match.** The trader would hold for days, but its only skilled input (move size) and the blind
   direction model are 1-hour forecasts. The BUY/HOLD/SELL score has no horizon at all.
4. **The cap counts in-memory fills.** `trade_times` lives in the portfolio object. If the process dies between
   sending an order and saving it, the count is lost. Firi has no client order id, so a retry could place a second
   order.
5. **Unclear order outcomes.** A rejected order raises and leaves no trace. A partial fill counts once, but nothing
   says whether a slot was used. A risk exit is appended to `trade_times`, so it uses up allowance for the next 24 h.
6. **A latent sizing defect (found while building E038).** A `NaN` move-size probability gives `f_move` = 1.0, full
   size, because `min(1.0, nan)` is 1.0 in Python. A missing value gives the intended 0.5.
7. **The pause also blocks protective exits.** This is by design today: pause = no order of any kind.
8. **Resizing and trimming are turnover.** Each resize or trim to the cap is an action that pays the spread and the
   fee.
9. **Unknown venue facts:**
   - Firi's minimum order size is not documented; a sized-down entry is NOK 37.50;
   - no historical Firi order book exists.

## 3. Recommended low-frequency architecture

**Analyse every hour; act rarely; record everything.** The prediction job and its research stay exactly as they
are. The execution layer changes from "turn this hour's signal into an order" into separate steps. Each step is a pure
function with its own tests, and only the last one touches the exchange.

```
every hour (unchanged)          every hour (new, pure)                         rarely (existing, hardened)
prediction record  ---->  1 ASSESS    signal history, smoothed score, volatility,
move-size record   ---->              expected move, live Firi quote, position, risk state
Firi public quote  ---->  2 PROPOSE   candidate actions: enter / exit / none
                          3 PRICE     expected advantage = expected return over the horizon
                                                         - full round-trip cost - margin
                          4 PERMIT    risk exits first (outside the allowance); then the
                                      allowance (1 per rolling 24 h), staleness, pause,
                                      venue minimum
                          5 RECORD    the decision and EVERY candidate with its reason,        ---> 6 EXECUTE: intent row
                                      accepted or rejected (hypothetical outcome tracked)             first, then the order,
                                                                                                      reconcile, record fill
```

- **No obligation to trade.** A new day or an unused slot is never a reason to act. "None" is step 3's answer whenever
  the expected advantage does not clear the cost.
- **Entries and exits are priced differently.**
  - An entry must clear the whole round trip, because it will have to be undone.
  - An exit only has to beat the expected return of staying in; the entry cost is already paid.
  - Risk exits are not priced at all: they run whenever a limit is hit.
- **The horizon is explicit.** The expected return in step 3 is over a stated holding period (24 h, 72 h, 7 days). It
  comes from a registered, development-data table or a validated model, never from the live record. The margin is
  statistical: an opportunity must clear the cost at the **lower 95% bound** of its expected return, not at its point
  estimate, so a noisy estimate cannot open the gate.
- **Learning from what was not done.** Every rejected candidate is stored with its hypothetical outcome at its own
  horizon. Those tables are never read by the portfolio, so the system can later measure whether its filters threw
  good opportunities away without ever confusing hypothetical results with money.
- **Configurable, but enforced in code.**
  - One versioned config holds the allowance, horizon, margin and sizing.
  - The hard cap and the risk stops remain constants that only a reviewed commit can change.
  - A database key enforces the allowance; the app can never raise it.

### What counts as a trade

| Term | Meaning | Uses an allowance slot? |
|---|---|---|
| **Decision** | the hourly record: assessment, candidate actions, the chosen one (usually "none") and why | no |
| **Order intent** | written to the database BEFORE anything is sent, keyed `(strategy version, window, slot)` with a UNIQUE constraint | reserves the slot |
| **Rejected before acceptance** | Firi refuses the request (validation, balance, signature) and returns no order id | no. The slot is released, the attempt is counted (at most 3 a day) and raises an alarm |
| **Accepted, nothing matched, cancelled** | the order reached the book and nothing filled before it was cancelled | **yes**: it reached the venue; no second try in the window |
| **Partially filled** | some of it matched; the rest is cancelled | **yes**, once; the remainder is never topped up in the same window |
| **Filled** | an **executed action**: one BUY or one SELL | yes |
| **Risk exit** | a sale forced by the daily-loss or drawdown limit | **no**: its own key and counter, at most one an hour |
| **Owner's "sell all"** | an explicit instruction in the app | no; logged as the owner's |
| **Cycle** | flat → invested → flat: two executed actions | — |

So "1 trade a day" means **one executed BUY or SELL in any 24 hours**. A full buy-then-sell cycle then takes at least
two windows. "2 a day" allows the buy and the sell inside the same 24 hours. A retry, a restart, a duplicated
workflow run or two concurrent runners can never take a slot twice, because the slot is a row written before the order
exists.

### The trading day

| Option | For | Against |
|---|---|---|
| UTC calendar day | fixed 24 h; the candles, data and jobs are all UTC | resets at 01:00 or 02:00 Oslo time; two actions can still sit minutes apart across midnight |
| Europe/Oslo calendar day | matches what the owner sees | 23 h and 25 h days at the daylight-saving changes; the same midnight problem |
| **Rolling 24 h (today's rule)** | no reset to game, no daylight-saving case, rebuilt from stored rows after any restart | "the day" has no fixed start, so the app must show the next possible time |

**Recommendation:**
- Keep the rolling 24 h window for the limit, and do all arithmetic in UTC.
- Show every time in Europe/Oslo time (`zoneinfo`).
- A design that acts on a schedule fixes its decision hour in UTC and shows it in Oslo time.

### Risk controls and the allowance

- **Risk exits always outrank the allowance.** E038's code proves it on real data: a 10% fall within the same 24 h as
  the day's one entry still sells (`tests/test_low_frequency.py`).
- **A risk exit halts trading until the owner resumes.** This is unchanged.
- **Stale or doubtful data never allows a risk-increasing order.** An exit is still allowed. This is unchanged.
- **The owner's pause (decision D4).** Choose between:
  - (a) the pause blocks everything, as today;
  - (b) the pause blocks entries and normal exits but lets risk exits run, with a separate "stop" that blocks
    everything.

## 4. One trade vs two trades: the evidence (E038)

**Data:**
- The BUY/HOLD/SELL signal replayed hour by hour (scoring 0.2.0, technical-only: the development data has no news).
- E018's out-of-sample move-size probabilities for sizing.
- Binance BTC/USDT closes.
- All through the governed readers.

**Periods:** exploration **2018-11-27 → 2023-12-31** and validation **2024-01-01 → 2025-06-30**. Each period starts
from 150 in cash.

**Engine:** a lean copy of rule-1.0 that **reproduces the production engine bit for bit**: 30 of 30 checks with
identical actions (17,036 in all) and a final-equity difference of 0.0. The first launch stopped at that check. Pandas had parsed the times at
microsecond resolution, so every hour collapsed into one. That was fixed in `d2ebcba` before any result existed.

**Costs per side:**

| Scenario | Per side | What it is |
|---|---|---|
| S0 | 0% | gross: no costs |
| S1 | 0.11% | a low-cost venue: **not available on Firi**; a diagnostic only |
| S2 | 0.8% | Firi optimistic: patient limit orders |
| S3 | 1.25% | **Firi realistic**: 0.7% fee + half the measured spread |
| S4 | 1.6% | Firi conservative |

**Validation wear:** ~31 experiments had seen these years, so all of this is hypothesis-generating.
Full tables: `research/results/E038/low_frequency.md`.

### 4.1 At Firi's realistic cost (S3)

| Policy | Net 2024–25 | Net 2018–23 | Mean daily return, 2024–25 [95% CI] | Actions/yr (24–25 / 18–23) | Mean exposure (24–25) |
|---|---|---|---|---|---|
| A4 rule-1.0 as built (4 per 24 h) | **−93.3%** | **−93.4%** | −0.47% [−0.65, −0.29] | 177 / 63 | 52% |
| A2 rule-1.0, 2 per 24 h | −93.4% | −93.4% | −0.48% [−0.65, −0.30] | 186 / 68 | 47% |
| A1 rule-1.0, 1 per 24 h | −93.2% | −95.2% | −0.47% [−0.64, −0.29] | 171 / 84 | 46% |
| B1 persistence (6 h), 1 per 24 h | −43.9% | −68.8% | −0.09% [−0.25, +0.07] | 61 / 69 | 50% |
| B1 persistence (6 h), 2 per 24 h | −34.1% | −89.7% | −0.06% [−0.22, +0.10] | 63 / 80 | 49% |
| B2 daily vote (one decision a day) | −24.8% | −31.5% | −0.04% [−0.18, +0.12] | 34 / 42 | 51% |
| B3 strong scores only, 1 per 24 h | **−3.3%** | −24.2% | +0.01% [−0.15, +0.17] | 33 / 39 | 44% |
| B3 strong scores only, 2 per 24 h | −3.7% | −5.3% | +0.01% [−0.15, +0.17] | 33 / 42 | 44% |
| B4 cost-aware gate, 1 or 2 per 24 h | **0.0%** (never traded) | 0.0% (never traded) | 0 | 0 / 0 | 0% |
| Buy-and-hold (one entry) | +149.1% | +1004.8% | +0.20% [−0.00, +0.41] | — | 100% |
| Cash | 0.0% | 0.0% | 0 | — | 0% |
| 200-day average (published reference rule) | +21.0% | +351.2% | +0.06% [−0.16, +0.28] | 14 / 6 | 80% |

Why A1, A2 and A4 end alike:
- Each lost about 93% within roughly a year: in the full run, 2019 alone was −75% to −87%.
- The account then sat near 10 units, the venue minimum, and could hardly trade.
- The risk stops cut each 30% fall, but trading resumed and the stake bled again. The simulation resumes after 168 h;
  live, the owner decides.
- With the account ruined, "1 a day" and "2 a day" cannot be told apart at S3: paired difference +0.003% a day
  [−0.15, +0.14].

### 4.2 Without costs: is any timing better than chance?

Each policy's cost-free result was compared with **200 random-timing versions of itself**. The signal is shifted in
time against the prices, so the turnover and exposure stay the same and only the timing is random.

| Policy | Gross net 2024–25 | Percentile vs random timing, 2024–25 | Gross net 2018–23 | Percentile vs random timing, 2018–23 |
|---|---|---|---|---|
| A4 | +57% | 65 | +212% | **95.5** |
| A2 | +58% | 65 | +244% | **99.0** |
| A1 | +30% | 26 | +213% | 90.5 |
| B1 persistence, 1 / 2 per 24 h | +54% / +61% | 53 / 64 | +252% / +262% | **96 / 97** |
| B2 daily vote | +35% | 36 | +193% | 72 |
| B3 strong only, 1 / 2 per 24 h | +47% / +47% | 50 / 53 | +195% / +199% | 78 / 82 |

**No policy beats random timing in both periods.** Three looked skilful in 2018–23 (the 95th–99th percentile), and
none of that survived 2024–25 (the 26th–65th). This is the same pattern as E017's exploration-only hints.

The gross results are positive mainly because the policies were partly invested in a rising market. In 2024–25 the
random versions earned about as much. In 2018–23 some actual results beat most random versions, and that did not
repeat.

### 4.3 The cap itself

**Turnover (cost-free runs, actions a year, 2024–25 / 2018–23):**

| Policy | Actions a year |
|---|---|
| A4 | 286 / 310 |
| A2 | 274 / 292 |
| A1 | 201 / 215 |
| B1 at cap 1 | 63 / 74 |
| B1 at cap 2 | 65 / 86 |
| B3 at either cap | 34 / 41–43 |

- **A 1-per-24 h cap removes only ~30% of rule-1.0's trades.** The 6 h rule, the band and the signal flips already
  shape the rest.
- **The selective designs rarely want more than one action a day.** The cap matters little for them (B3: paired
  difference 0.000% a day).

**Paired differences, cap 1 minus cap 2 (mean daily return):**
- A at S2, 2024–25: **+0.17% [+0.07, +0.27]** — the 1-a-day version lost clearly less.
- B1 at S3, 2018–23: **+0.06% [+0.02, +0.11]** — cap 1 clearly better.
- B1 at S3, 2024–25: −0.03% [−0.07, +0.01] — no clear difference.
- Everywhere else, the intervals include zero.

**The registered reading:**
- Neither cap has a positive net result at S3.
- Neither beats random timing in both periods.
- So the data cannot choose on predictive grounds. The 1-a-day cap has the lower turnover in every comparison.
- **The default is 1 per rolling 24 h. This is a cost decision, not an edge.**

### 4.4 Persistence, strength and the cost gate (descriptive)

Forward 24 h and 72 h returns were compared with the period's average, by signal × run length and by score quintile.

**2018–23:**
- Long runs (≥ 24 h) were followed by **higher** returns for **both** BUY (+0.63%) and SELL (+0.64%).
- Short runs (1–5 h) of every signal were followed by lower returns.
- The most bullish quintile was +0.31%. The most bearish was **not** lower (+0.09%).

**2024–25:** none of this repeats; every interval includes zero.

So persistence and strength carry **no directional information**. Long runs mark trending, volatile stretches, and in
2018–23 those happened to rise. Going to cash on a persistent SELL would have missed exactly those gains.

**The cost gate's own estimates at the end of development:**
- BUY ≥ 24 h: +0.75% over 24 h;
- SELL ≥ 24 h: +0.71% (it learned "long runs" rather than "BUY");
- every other state: below +0.25%.

The best of these is below half of the cheapest Firi round trip (1.6%), so **at S2–S4 the gate never opened in
either period**. At the low-cost reference (S1) it traded and drifted towards buy-and-hold.

### 4.5 The live record (descriptive only, never used to choose)

2026-09-19 → 2026-11-15: 1,355 hours, while Bitcoin fell ~19%.

| Policy | Result at S3 |
|---|---|
| A4 | −36.0% |
| A2 | −33.9% |
| A1 | −29.3% |
| B1 | −17.0% |
| B2 | −11.5% |
| B3 | −10.3% |
| B4 (the cost gate) | 0.0% (no trade) |
| Buy-and-hold | −20.2% |
| Cash | 0% |

The signal's flip rate and run lengths match development exactly (3.7 changes a day, median run 3 h).

### 4.6 Hypotheses as registered

| Hypothesis | Outcome |
|---|---|
| H1: lower caps lose less | **Partly.** Lower caps trade less. A1 lost clearly less than A2 at S2 in 2024–25, but at S3/S4 all three were ruined alike |
| H2: no selection design beats cash at S3 in both periods | **Holds** |
| H3: no policy's timing beats random in both periods | **Holds** |
| H4: the cost gate barely trades at Firi's costs | **Holds**: 0 entries at S3/S4; about 1 a year at S2 in 2018–23 |
| H5: no persistence or strength bucket repeats | **Holds** |

No tripwire fired.

## 5. Recommended trading strategy

**`lf-1.0`, the cost-hurdle design (recommended).**

| Element | Rule |
|---|---|
| Analysis | every hour, unchanged |
| Opportunity | an entry when the expected return over horizon H, at its lower 95% bound, exceeds the full round trip estimated from the live quote; an exit when staying in is expected to lose more than the exit costs |
| Horizon H | stated per strategy version. Today 24 h (E038's state table); the gate is designed to move to 72 h–30 days once a forecast at that horizon is validated (section 7) |
| Allowance | **1 executed normal action per rolling 24 h**; risk exits outside it |
| Sizing | one sized entry (volatility factor as today); no resizing between entry and exit; trim to the cap only when the excess clears a band; confidence off; no "stronger signal, bigger position" (no evidence) |
| Default when nothing clears the hurdle | stay as you are |
| Every hour's record | the assessment, every candidate with its expected advantage, cost and reason, the hypothetical outcome later |

**What it will do with today's evidence: nothing.** The gate stays closed because no input of the system has an edge
that pays for Firi. That is the evidence-based result, and it is safe: the system stays fully built, monitored and
ready, so that a future validated forecast opens the gate on its own merits.

**The default position is the owner's decision.** It is cash today. Whether to hold Bitcoin outside of any signal is
an investment choice. I'm not a licensed advisor and do not recommend one way or the other. Note one technical fact
for that choice: with a closed gate, a portfolio that starts invested stays invested, and one that starts in cash
stays in cash.

**If the owner wants real trades anyway (an operations test, not an investment).** The least-bad measured design is
**strong scores only at 1 per 24 h** (B3):
- about 33–39 actions a year;
- −3% (2024–25) and −24% (2018–23) at S3;
- costs of about **NOK 53 a year on a NOK 150 stake**;
- no demonstrated edge.

It would be labelled exactly that in the app.

**Rejected:**
- rule-1.0 at any cap (ruinous at Firi's costs);
- persistence and the daily vote (no edge, more turnover);
- confidence-based sizing;
- gradual scaling in (each step pays the spread again);
- a 24 h minimum hold as a rule by itself. The cap already spaces normal actions 24 h apart; what matters is the cost
  hurdle, not a timer.

## 6. Transaction costs

| Item | Value | Status |
|---|---|---|
| Firi trading fee | **0.7% on each buy and each sell**, no maker/taker tiers listed | **verified**, firi.com/no/priser (2026-11-15) |
| Firi BTC/NOK spread | 1.29% (2026-11-14) and 0.98% (2026-11-15 10:39 UTC); this session's public-book sampler, 6 samples 10:44–11:34 UTC: 0.91–1.28%, mean 1.13% | measured, few samples, one weekend |
| Cost of a NOK 150 buy vs the mid price | ≈ 0.57% (top of book; the top level holds ~0.5 BTC, so no depth slippage at this size) | measured |
| Slippage while the order rests 3 s | small; not measurable without trades | estimate |
| Deposits | bank transfer free; card/Vipps 3.9% | verified |
| Withdrawals | NOK 69 (minimum NOK 70); BTC 0.0001 | verified |
| Minimum order | **not documented** | unknown |
| Tax | every sale realises a gain or loss | owner's reporting |

**The round trip.** Two fees plus one full spread, plus a little slippage: **≈ 2.4–2.7% at today's spreads**. That is
1.6% with patient limit orders and 3.2% on wide hours.

**How the system should use it.**
- Estimate the round trip **at decision time** from the live Firi quote: 2 × (0.7% + half the live spread + 0.05%).
- Never use a fixed number.
- Log the estimate with the decision.
- After every fill, compare the realised cost with the estimate.

**The hurdle:**
- An entry needs LCB95(E[return over H | state]) − round trip ≥ 0.
- An exit needs E[return over H | state, invested] < −(exit cost).

**What the cost does to the needed accuracy.** This is the hit rate needed to cover a 2.5% round trip, if wins and
losses are the same size. The figures come from the development data's mean absolute return over each horizon.

| Hold | Mean absolute move (2018–23 / 2024–25) | Needed hit rate |
|---|---|---|
| 24 h | 2.6% / 1.9% | 98% / impossible |
| 72 h | 4.7% / 3.4% | 77% / 87% |
| 7 days | 7.4% / 5.2% | 67% / 74% |
| 30 days | 18.5% / 12.2% | 57% / 60% |

The current signal is right 47–49% of the time at every horizon (E017).

**Costs that could be cut, to test before relying on them:**
- **Passive limit orders.** Post at the best bid or ask and wait, accepting no fill. This could save most of the half
  spread (≈ 0.5% a side). Firi's public trade history (`/v2/markets/BTCNOK/history`) can measure how often a resting
  price would have filled, for free.
- **Trading at narrow-spread hours.** The sampler would show when the spread is narrowest.

## 7. Test goals and measurable requirements

Three different kinds of evidence, never mixed:

- **software tests** prove the code does what it says;
- **historical evaluation** (development data, hypothesis-generating) can only reject an idea or nominate one;
- **prospective evaluation** (paper, then real) is the only confirmation.

### 7.1 Predictive goals: what an input must show before the gate may open on it

| Requirement | Threshold | Why this number |
|---|---|---|
| Expected return in the acted states | lower 95% bound > the S3 round trip (2.5%) at the strategy's horizon, in both development periods | the hurdle itself; the bound absorbs estimation error |
| Equivalent hit rate (symmetric moves) | ≥ 77–87% at 72 h, 67–74% at 7 days, 57–60% at 30 days | section 6 table |
| Skill vs the base rate | Brier skill > 0 with the interval excluding zero, both periods; calibration by E013's rule | a probability that is not calibrated cannot price a hurdle |
| Stability | right sign in ≥ 6 of 8 calendar years (E032's year rule) | no dependence on one era |
| Prospective confirmation | the same at a registered reading on the live record | validation wear: development data cannot confirm |

**Today:** the BUY/HOLD/SELL signal fails every row, and the move-size model is not directional. Nothing qualifies.

### 7.2 Trading goals (historical, to nominate a design for prospective testing)

| | Requirement | Measured by |
|---|---|---|
| **Essential** E1 | mean daily net return above cash at S3 with the 95% interval above zero, in both periods; S4 point estimate > 0 | 20-day block bootstrap |
| **Essential** E2 | gross result ≥ the 95th percentile of its random-timing null, in both periods | 200 circular shifts |
| **Essential** E3 | ≥ 20 cycles per period, and still positive after removing the 3 best cycles | the cycle list |
| **Essential** E4 | maximum drawdown no worse than buy-and-hold at the same average exposure; no risk-limit breach | the equity path |
| **Essential** E5 | positive at S3 in at least 5 of the 7 full years 2019–2025 | yearly returns |
| Secondary | profit factor > 1.2; fewer than 50 actions a year; costs below 25% of the gross gain | the run's figures |

Beating rule-1.0 or buy-and-hold in one falling stretch is not a pass.

### 7.3 Sample size

E038's cycles at S3 vary by **5.5–11.6% each** (standard deviation, the selective designs). Detecting a true net
**+1% per cycle** (80% power, two-sided 5%) needs **240–1,060 cycles**; +2% needs 60–265. At 24–48 cycles a year,
that is **8 to 66 years**, or **2 to 17 years** for +2%.

On daily returns, a strategy with a true Sharpe ratio of 1 needs about **4 years** to reach t = 2, and one with 0.5
needs about **16 years**.

**So at this frequency an edge cannot be shown in months.** Paper trading proves the software and the real costs, not
profitability. The cap should not rise above NOK 150 (the code's hard maximum is NOK 500) without E1–E5 plus a
prospective reading of that size.

### 7.4 Go / No-Go gates

| Gate | From → to | Requirements (all measurable) |
|---|---|---|
| **G1** | code → paper | all of section 9's tests pass; mutation guards on the allowance key, the risk-exit override, staleness, the NaN sizing rule and the pause; integration tests on a scratch schema (two concurrent runners, a crash between intent and order); CI green |
| **G2** | paper → one real minimum-size order | ≥ 28 days (672 hourly decisions) of paper trading at Firi's real quotes. Over that run: 0 allowance violations, 0 duplicate intents, 0 unexplained ledger differences, a quote recorded in ≥ 95% of hours, every rejected candidate logged with its reason. The alarms tested. **And the owner's separate, explicit approval** |
| **G3** | minimum stake → keep running | every weekly audit: ledger = Firi balances; realised fee within ±0.05 pp of 0.7%; realised spread cost inside S2–S4, or a registered model update; 0 limit breaches |
| **G4** | "no demonstrated value" → any claim of an edge in the app | E1–E5 on development data **and** a prospective reading of the size in 7.3 |
| **G5** | raise the cap above NOK 150 (never above the coded NOK 500) | G4 |

## 8. Required software changes

| # | Component (file) | Change | Why |
|---|---|---|---|
| S1 | `agent/execution/` | Keep `rule-1.0` frozen. Add `lf-1.0` as a separate, versioned strategy, with its parameters in one frozen, bounded config object: allowance per 24 h, horizon, cost model, hurdle, sizing switches. A registry maps a version to its code | frequency, thresholds, horizons and sizing change without touching logic; every decision names its exact version |
| S2 | new `assessment.py` | A pure hourly assessment: signal history (run length, last change), smoothed score, rv_24 and p_large, the live quote's cost estimate, the expected return at the horizon (from a registered table, never the live record), exposure, risk state | separates "what does the market look like" (hourly) from "do we act" (rarely) |
| S3 | new `opportunity.py` | Candidates (enter, exit, none), each with its expected advantage, cost, rank and reason | the hurdle becomes explicit and logged; "no trade" carries a reason |
| S4 | `engine.py` | The allowance comes from **stored order intents**: the intent row (UNIQUE `(strategy, window, slot)`) is written before the order is sent. Risk exits use their own key and do not count | survives restarts, retries, duplicate runs and concurrent runners; Firi has no client order id |
| S5 | `firi.py` | After sending, find the order in `/v2/orders/BTCNOK` and `/v2/orders/BTCNOK/history` (side, amount, `created_at`). Record `matched` / `remaining` / `cancelled`. A partial fill = the action. A rejection before acceptance = no slot, but an attempt and an alarm | "sent, but we do not know what happened" becomes recoverable without a second order |
| S6 | `strategy.py` (defect) | Treat a NaN `p_large` as missing (`f_move` 0.5), not as full size | a NaN must never mean full size |
| S7 | `strategy.py` | Pause vs stop, if the owner chooses (D4) | protective exits during a pause |
| S8 | new `agent/execution/schema.sql` | `execution_assessments`, `execution_opportunities` (+ hypothetical outcomes), `execution_orders` (intent + status, UNIQUE slot key), `execution_fills`, `execution_portfolio`, `execution_settings` + `_log`, `execution_quotes`. RLS on, API roles revoked, exact job-role rights in `least_privilege_role.sql`, the security check extended | the state that must survive restarts, and the evidence for every decision |
| S9 | `.github/workflows/hourly.yml` | One isolated step after the existing ones, `continue-on-error`, with its own heartbeat; it never writes the prediction tables | an execution failure must never break the prediction record |
| S10 | new `paper.py` | The same path with simulated fills at the **real Firi quote** sampled at decision time, plus the 0.7% fee; no key | the closest thing to real costs before money moves |
| S11 | `web/` | A "Today" panel showing: <br>• allowance used and left; <br>• the next possible action (Oslo time); <br>• whether it is waiting or acting; <br>• the last accepted and rejected opportunities, with expected advantage vs cost. <br>Also the opportunity log, and hypothetical results kept visibly apart from the portfolio | the owner sees why it traded or did not |

Nothing here touches the prediction engine. The isolation tests stay as they are. E038 keeps the engine comparison in
`tools/`, so that the research package still never imports the execution layer.

## 9. Testing and validation plan

### 9.1 Software tests (all must pass; none of the existing ones is removed or weakened)

| # | Test | How it is proven |
|---|---|---|
| 1 | At most 1 normal action in any rolling 24 h | property test over many random paths (E038 already has one) + a mutation guard raising the limit |
| 2 | At most 2, for the option-B configuration | the same, with 2 |
| 3 | The count survives a restart | the engine rebuilt from stored rows mid-window |
| 4 | Duplicate requests and retries | the same run twice, two runners at once, a retry after a timeout: exactly one intent wins by the UNIQUE key; a guard that drops the key must be caught |
| 5 | Partial fills | one action counted, remainder cancelled, ledger = venue |
| 6 | Rejected orders | HTTP 4xx before acceptance: no slot, attempt counted, alarm, no retry loop |
| 7 | Cancelled orders | accepted, nothing matched, cancelled: the slot is used, no second order in the window |
| 8 | Close to the window edge | decisions at 23:13 and 00:13 UTC and across the Oslo midnight: still at most N |
| 9 | Time zone and daylight saving | the last Sundays of March and October: the shown "next action" time is right; the limit is unchanged |
| 10 | Emergency exit after the allowance is used | entry at 10:13, a fall at 15:13: the sale executes as a risk exit and uses no slot (E038 has a version) |
| 11 | Exchange outage | ticker, balances or order call times out: no order, a recorded failure, reconcile first next hour |
| 12 | Stale or inconsistent market data | candle > 2 h old, quote far from the close, zero or crossed book: no risk-increasing order |
| 13 | Incorrect balances | venue below the ledger: halt and alarm (exists), extended to pending orders |
| 14 | Failed database writes | intent not stored: no order sent; fill not stored: halt, alarm, reconcile |
| 15 | Risk-limit activation | daily loss and drawdown: sell all, halt, outside the allowance |
| 16 | Manual pause (and stop) | per D4 |
| 17 | Bad or missing predictions | missing hour, unknown signal, wrong version, NaN inputs: no risk-increasing order; NaN never means full size |
| 18 | Cost arithmetic | fee, spread and slippage against hand-computed values; a round trip at c leaves (1 − c)² on a flat price (E038 has one) |
| 19 | Minimum order | an entry below the minimum is skipped with a reason; dust never blocks a later entry |
| 20 | No execution from an outdated run | a backup slot 90 min late, a re-dispatched old hour, an hour that already has an intent: no order |
| 21 | The cost hurdle | an opportunity below the round trip is rejected and logged with both numbers |
| 22 | Hypothetical stays hypothetical | the opportunity log never changes the portfolio; the portfolio tables never read it |
| 23 | Isolation | nothing in the prediction engine or its research imports the execution layer (exists) |

### 9.2 Historical evaluation

- Any new design is registered first, like E038.
- It runs on development data only, through the governed readers.
- It must reproduce the production engine exactly before results count; the method is `tools/e038_low_frequency.py`.
- It is judged by 7.2.
- The holdout stays sealed for evaluation, and opening it remains the owner's decision.

### 9.3 Prospective evaluation

- Paper first (G2).
- Then, only with the owner's separate approval, one minimum order, then the owner's cap.
- Every week: the audit checks of G3.
- No reading of the live record is ever used to tune; changes go through a new registration and a new version.

## 10. Implementation roadmap

Each stage gets its own commits through the gate, tests first. Nothing goes live without the owner.

| Stage | What | Depends on | Exit condition |
|---|---|---|---|
| L0 | This report and E038 (**done**); the owner's decisions (section 12) | — | decisions recorded |
| L1 | Fix the current core whatever the strategy: NaN sizing (S6), the pause/stop split if chosen (S7), risk exits off the allowance count | L0 | tests 10, 15, 16, 17 + their mutation guards |
| L2 | `lf-1.0` as a pure, versioned module with its config (S1–S3); `rule-1.0` frozen beside it | L1 | tests 1, 2, 8, 9, 18, 19, 21; replaying `lf-1.0` on development data reproduces E038's matching policy exactly (no new tuning) |
| L3 | Storage (S8) with the UNIQUE slot key, RLS, the job role and the security check; integration tests incl. two concurrent runners | L2 | tests 3, 4, 14, 20, 22; integration with the drift check |
| L4 | Firi hardening (S5), plus the public quote sampler as an hourly step (no key; it only reads the book) | L3 | tests 5, 6, 7, 11, 12, 13; the sampler's first week reviewed (spread by hour of day) |
| L5 | Paper trading (S10) with its own heartbeat | L4 | G2 (except the approval) |
| L6 | The owner creates the key and stores it as secrets; a read-only balance check from a GitHub runner, or the EU Edge Function if Firi refuses US addresses | L5, owner | a signed balance call works; nothing ordered |
| L7 | **The owner's separate, explicit approval**; then one minimum order the owner watches | L6, owner | ledger = Firi; fee and spread as modelled |
| L8 | Running at the owner's cap; weekly audits extended (G3) | L7 | continuous |
| R | In parallel, each registered first and only on the owner's go-ahead: (1) a forecast at the trading horizon (72 h–30 days); (2) the Firi cost model from the sampler; (3) passive-order fill rates from Firi's public trade history | owner | its own registered verdict |

L1–L5 need no key, no account and no money, and change nothing in the prediction engine. L6 and L7 wait for the owner.

## 11. Remaining uncertainties

| Uncertainty | Why it matters | How to settle it (free) |
|---|---|---|
| Firi's minimum order size | a sized-down entry (NOK 37.50) might be refused | the first signed call, or Firi support |
| Firi's spread over time | the realistic cost rests on a few weekend snapshots | the hourly public-book sampler (L4) |
| Whether Firi accepts GitHub's US runners | where orders run | the read-only balance check (L6); the EU Edge Function fallback |
| Passive-order fill rates | could save most of the spread | Firi's public trade history |
| Firi's own BTC/NOK history | E038 uses Binance BTC/USDT; Firi adds the NOK rate and its own book | cannot be reconstructed; only the live paper record |
| News in the signal | the replay has none; live news changed ~5.5% of signals | the live record; the news verdict ≈ 2027-02 |
| A forecast at the trading horizon | no input has an edge at 24 h–30 days | a registered research line (the owner's decision) |
| Regimes | the live record is calm and falling; development covers 2018–2025 | time |
| The simulation's "resume after 168 h" | live, the owner decides when to resume after a stop | it only affects how fast a bad strategy bleeds, not whether |

## 12. Decisions for the owner

1. **D1, the allowance:** 1 executed action per rolling 24 h (recommended: the cost decision of section 4.3), or 2.
2. **D2, the strategy:** `lf-1.0` with the cost hurdle (recommended; with today's evidence it does not trade), or a
   labelled operations test with "strong scores only, 1 per 24 h" at an expected cost of about NOK 53 a year and no
   edge.
3. **D3, the default position** while the gate is closed: cash (today), or invested. This is an investment choice and
   yours alone; I don't advise on it.
4. **D4, the pause:** keep it blocking everything, or let risk exits run during a pause and add a separate stop.
5. **D5:** go ahead with L1–L5 (no key, no money, no change to the prediction engine).
6. **D6, later:** whether to register research line R(1), a forecast at the trading horizon.

---

## Sources (accessed 2026-11-15)

- Firi price list (trading fee 0.7%, deposits, withdrawals): https://firi.com/no/priser
- Firi trading API page (no API withdrawals): https://firi.com/about/trading-api
- Firi API reference (endpoints, order fields, order history): https://developers.firi.com/
- Firi public market data: `https://api.firi.com/v2/markets/BTCNOK/ticker` and `/depth` (read without a key)
- Internal: E001, E017 (`research/results/E017/summary.md`), E018, E032, E033, E038 (`research/results/E038/`),
  `docs/platform/PLATFORM_PLAN.md`, `research/DIRECTION_RESEARCH_REVIEW_2026-10-21.md`
