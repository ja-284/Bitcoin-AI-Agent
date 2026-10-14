# Directional signal: is another experiment justified? (assessment, 2026-10-14)

Written for the post-500h plan, Phase 4. **No experiment was run, and nothing changed.** This reads the existing
record and answers one question: what kind of genuinely new hypothesis or new permissible data would justify
another directional experiment?

## Four different objectives, kept apart

| objective | what it asks | evidence so far |
|---|---|---|
| **move-size forecasting** | how likely is a move of more than 0.25%, *in either direction*, in the next hour? | the one positive result: E012 / E013. On development data it is 2.47× the free EWMA rule (E019). Live at 500 hours it is ahead of that rule (Brier 0.1927 vs 0.2091), as a first look with no verdict |
| **probability calibration** | do stated probabilities match observed frequencies? | E013 holds on validation. Live it is not confirmed (500 h: ECE 0.059, about 0.03 too high). Time-of-day offsets are real and stable (E027, E031) |
| **direction prediction** | will the price be higher or lower after H hours? | **no usable signal** anywhere (below) |
| **a useful BUY/HOLD/SELL decision** | does acting on the signal beat not acting, after costs? | **no demonstrated value** (E001, E017, live). Needs direction, or a decision rule that uses size, and has neither |

**Better move-size prediction does not give directional skill.** The move-size model is symmetric: it says *how
big*, never *which way*. A large expected move is equally likely up or down as far as anything here has shown. It
could inform a decision layer (for example "hold when a large move is likely"), but no such rule has been
registered or tested, and none should be presented as having value.

## What has already been tried for direction (all negative)

- **The live scoring, 0.1.0 and 0.2.0** (E001, E017): 68,619 replayed hours, five horizons. There is no edge
  beyond buy-and-hold drift, acted-hour accuracy is 47–50%, and the confidence heuristic is uninformative.
  - Live, at 348 graded hours: 1h matched 0.500 vs a 0.509 baseline (weekly report 2026-10-13).
  - 6h, 24h and 72h sit below baseline, but on few independent windows.
- **Each category alone** (E002): no positive information at any horizon.
- **47 candidate features in six groups**, all fit-free and checked in both periods (E003–E008): volatility,
  regime, derivatives, macro, on-chain, microstructure. None meets the directional criterion.
- **A fitted direction model** (E011): L2 logistic on the reversal inputs plus the category scores, 15
  walk-forward runs. **0 of 15 pass**: accuracy is earned on small moves and lost on the largest.
- **Eight "shape" features** (E015, 80 tests): **0 pass**. The strongest consistency the programme has found,
  `up_streak_6` at 1h (ρ −0.080 / −0.060), earns only **0.4×** the 0.10% round-trip cost.
- **News** (E030, 2026-10-14): a first look at 500 hours, with every interval including zero. Underpowered by
  design; the verdict needs 3,140 hours.

**What is robust:** a tiny short-horizon *reversal* family (momentum, volume, taker-buy share, streaks; |ρ| 0.02–0.08
at 1–6h). It is real, consistent across periods, and economically useless at retail costs (E015).

**What is underpowered, not refuted:**
- the news score (E030, verdict ≈ 2027-02);
- the two live watch-list items, funding at 24h contrarian (E005) and dollar/yield at 168h (E006). Their
  confirmatory re-tests are already registered for ≥ 6 live months (≈ 2027-03).

## What would justify a new directional experiment

All four of the following would be needed. None is met today.

1. **New information, not a new transformation of old information.**
   - The 47 + 8 candle, macro, on-chain and derivatives features already cover what the free data offers.
   - What is missing is unavailable or unsafe as free point-in-time history: order-book depth, liquidation
     flows and open interest (E005 marked them UNAVAILABLE), options skew (paid), and historical news (no
     archive; LLM training knowledge would leak).
   - A *new free source with trustworthy timestamps and a stated mechanism* would qualify. Another indicator
     sweep would not.
2. **A mechanism stated before the data is seen.** It must also say why the effect would survive costs, not
   only that it would show up in a correlation. E015 shows that consistency is not usefulness.
3. **A cost-aware criterion from the start:** gross edge per acted hour above the round-trip cost, with an
   interval, at a pre-registered horizon.
4. **Clean evaluation data.**
   - The development periods are worn (about 30 experiments).
   - The holdout's one use is reserved for E014/E023.
   - So a new directional idea could only be confirmed prospectively, and at |ρ| ≈ 0.05 that needs about
     3,000 graded hours (E025's arithmetic), about four months.

## Recommendation

**Do not run more directional experiments now.** No novel, defensible directional hypothesis is supported by the
record, and the only clean data are months away. Keep what is already registered:
- the news verdict at 3,140 usable hours;
- the funding and dollar/yield re-tests at six live months.

Keep the BUY/HOLD/SELL signal labelled *no demonstrated predictive value* in every report and in the contract.
Revisit only if a genuinely new free data source with a stated mechanism appears.
