# CLAUDE.md — Project Memory for Confluence (Bitcoin AI Analysis Agent)

This file is the project's memory. It should stay accurate and up to date
so that any future session (human or AI) can pick up this project and
understand the rules it must follow, without re-reading the whole chat
history. Update this file whenever we make a real decision.

## Project goal (plain English)

We're building an AI-assisted tool that checks on Bitcoin regularly (about
once an hour) and produces one of three signals: **BUY**, **HOLD**, or
**SELL** — plus a confidence level (how sure it is) and a plain-English
explanation of why.

It is **not** a trading bot. It never places real trades. Right now it's
purely an analysis tool: it watches the market, writes down what it thinks,
and later we check whether it was right. Only much later (if ever) would
any trading be considered, and that's a separate, deliberate decision — not
something that happens by default.

**Phase 1** (the current phase) is about building the "brain": the backend
that fetches data, does the math, asks the AI for input, combines it all
into a score, and saves the result. There is no dashboard/website yet —
that comes later, built separately (in a tool called Lovable), after the
brain actually works.

## Important principles (do not break these)

1. **Build the intelligence before the UI.** Get the analysis actually
   working first. A pretty dashboard on top of a broken or untested brain
   is worse than no dashboard at all.

2. **Prioritize data quality.** Bad or messy input data produces
   misleading signals no matter how good the analysis logic is. Clean,
   reliable data comes first.

3. **Avoid data leakage.** ("Data leakage" = accidentally letting the
   system see information from the future when we test it against the
   past.) When we later test this against historical data, the system must
   only ever use information that would have actually been available at
   that exact point in time. No peeking ahead.

4. **Avoid overfitting.** ("Overfitting" = tuning a system so precisely to
   match old data that it stops working on new data.) We are not trying to
   build something that perfectly explains the past — we're trying to
   build something that holds up on the future, which we can't see yet.

5. **Log everything important about every prediction.** Every time the
   agent produces a signal, we save what data it used, what each factor
   scored, what the final signal and confidence were, and why. Nothing
   important gets thrown away.

6. **Make confidence measurable and calibratable, not guessed.**
   ("Calibrated" = checked and adjusted so the stated confidence actually
   matches reality — e.g. if the agent says "70% confident" a hundred
   times, it should be right about 70 of those times.) The AI does not get
   to just state a confidence number because it "feels" confident. Over
   time we compare predicted confidence to actual outcomes and adjust.

7. **Test every meaningful change against historical data.** Before we
   trust a change (to scoring, to the AI prompt, to indicators, etc.), we
   check how it would have performed on the past, using the no-leakage
   rule above.

8. **Don't assume a signal is good just because the AI's explanation
   sounds convincing.** A confident-sounding, well-written explanation is
   not evidence that the underlying reasoning or data was actually sound.
   We judge the system by measured outcomes, not by how persuasive it
   sounds.

9. **Keep the architecture modular.** ("Modular" = built out of separate,
   swappable pieces rather than one tangled block.) We should be able to
   swap out any of the following without rewriting the whole project:
   - The AI model being used
   - Data providers (where price/market data comes from)
   - Technical indicators (the math formulas)
   - The scoring system (how factors combine into one signal)
   - News sources
   - The database (where results are stored)
   - The frontend (built separately, later)

10. **No real trading in this phase, or any time soon.** This stays
    analysis-only. The agent may eventually be tested with fake/simulated
    money ("paper trading") in a later phase, but it never touches real
    money without a separate, explicit decision to do so.

## What the agent analyzes

Each of these gets its own score, and the scores combine into one overall
score plus a confidence level:

- Price and historical price data
- Trends
- Trading volume
- Momentum / technical indicators (e.g. RSI, moving averages)
- Chart patterns
- Relevant Bitcoin/crypto news
- Possibly other market data later (added modularly)

The AI is given clean, structured information (prices, indicator values,
news summaries) rather than being asked a vague question like "will
Bitcoin go up?" Solid, deterministic math (indicators, scoring rules) does
the heavy lifting; AI is used specifically where it adds value (e.g.
reading and summarizing news, weighing mixed signals), not applied
everywhere just because it's available.

## Phase roadmap

- **Phase 1 — Backend & AI agent** *(current phase)*: data pipeline,
  indicators, scoring system, AI analysis, database, automated hourly
  runs. No frontend yet.
- **Phase 2 — Backtesting**: test the agent against historical data,
  simulating only what it would have known at each point in time.
- **Phase 3 — Improve the algorithm**: use backtest results to refine
  scoring and the AI's role, without overfitting to the past.
- **Phase 4 — Logging system**: full prediction history, compared against
  real outcomes.
- **Phase 5 — Paper trading**: run live, automatically, with fake money,
  to compare against backtest results.
- **Phase 6 — Dashboard**: a frontend (built in Lovable) showing live
  signals, confidence, scores, explanations, and historical performance.

## Architecture decisions log

*(This section gets filled in as we actually decide things — technology
choices, database, scheduling system, data providers, etc. Nothing is
locked in yet as of this writing; Phase 1 planning is in progress.)*

## Status

🚧 Phase 1 planning stage. No implementation code has been written yet —
architecture is being decided before any building starts, per principle
#1 above.
