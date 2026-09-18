# Confluence — Bitcoin AI Analysis Agent

An AI-powered agent that watches Bitcoin and produces a simple signal:
**BUY**, **HOLD**, or **SELL** — along with a confidence level and a plain-English
explanation of why.

> ⚠️ **This is an analysis tool, not a trading bot.** It does not place real
> trades. It's built to be tested carefully before being trusted with any
> real decisions, and even then, the decision stays with the person using it.

## What it does

The agent looks at several types of information and turns them into one
combined score:

- Price and historical price data
- Trends
- Trading volume
- Momentum / technical indicators (like RSI)
- Chart patterns
- Relevant Bitcoin/crypto news

Each factor gets its own score. The scores combine into an overall score,
which maps to a BUY / HOLD / SELL signal, plus a **confidence level** —
one that's measured against real historical results, not just guessed by
the AI.

## Why it's built this way

A few rules this project follows on purpose:

1. **Build the intelligence before the UI.** The backend and the AI agent
   come first. The dashboard comes later, once the analysis actually works.
2. **No data leakage.** When testing against old data, the agent only ever
   sees what would have actually been known at that point in time.
3. **No overfitting.** The goal is a system that holds up on new data, not
   one that's just been tuned to match the past perfectly.
4. **Log everything.** Every prediction is stored, along with what actually
   happened afterward, so the agent can be judged fairly over time.
5. **Confidence is measurable.** Not a made-up number — calibrated against
   real outcomes.
6. **Modular by design.** The AI model, data sources, indicators, scoring
   system, database, and frontend can all be swapped out without rebuilding
   the whole project.
7. **No real trading, for now.** This phase is analysis-only.

## Roadmap

- [ ] **Phase 1 — Backend & AI agent.** Data pipeline, indicators, scoring
      system, AI analysis, database, automated hourly runs.
- [ ] **Phase 2 — Backtesting.** Test the agent against historical data,
      simulating only what it would have known at each point in time.
- [ ] **Phase 3 — Improve the algorithm.** Use backtest results to refine
      scoring and the AI's role, without overfitting to the past.
- [ ] **Phase 4 — Logging system.** Full prediction history, compared
      against real outcomes.
- [ ] **Phase 5 — Paper trading.** Run live, automatically, with fake money,
      to compare against backtest results.
- [ ] **Phase 6 — Dashboard.** A frontend (built in Lovable) showing live
      signals, confidence, scores, explanations, and historical performance.

*Currently working on: Phase 1.*

## Status

🚧 Early development. Architecture decisions are still being made — this
README will be updated as those are locked in.

## Disclaimer

This project is for research and personal use. It is not financial advice,
and no AI can reliably predict price movements. Any real financial
decisions made using this tool are the user's own responsibility.
