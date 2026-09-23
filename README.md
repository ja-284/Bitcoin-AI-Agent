# Bitcoin AI Analysis Agent

A research backend that looks at Bitcoin every hour and records what it thinks, then checks
itself against what actually happened. It produces a **BUY / HOLD / SELL** signal with a
confidence figure and a plain-English explanation — and, separately, a **calibrated
probability that the next hour's move will be large**.

> ⚠️ **Analysis only. Not a trading bot, not financial advice.** It never places orders, holds
> funds, or touches an exchange account, and it is not going to. No AI can reliably predict
> price movements; this project measures honestly how little it can.

## What the research found so far (read this before trusting any signal)

- **Direction is not predictable from free data.** The hand-built scoring (v0.1.0, still the
  live signal) has no measurable edge over 2017–2025 (E001). 47 candidate features across
  volatility, regime, derivatives, macro, on-chain and microstructure add none (E002–E008). A
  fitted model combining the weak effects gains ~2 points of 1-hour accuracy and **zero**
  return edge (E011). The signal you see is therefore a *measuring instrument under test*,
  not advice.
- **Move size is predictable.** The probability that the next hour moves more than 0.25%
  tracks reality (rank correlation 0.45 / 0.36 in two separate periods, Brier 15% / 9%
  better than the base rate — E012), and after Platt calibration it means what it says in
  every year since 2018 (E013). This model runs live in *shadow* mode and is judged
  prospectively (`research/LIVE_EVALUATION.md`).
- **But most of that skill is free, and the model knows it.** Measured against a rule that
  needs no fitting at all — a 24-hour average of "did recent hours move a lot?" — the model
  is 2.5× better, not infinitely better (E019). Remove the volatility *level* from the
  question and the free rule scores **nothing** while the model keeps about three quarters
  of its own contribution (E021): what the model really adds is knowing *which hour inside a
  regime* will be big, and that part looks like it comes from trading activity rather than
  from price movement (E022, exploratory). The headline number alone overstates it.
- **The question itself moves.** Across years, the share of hours with a move over 0.25% has
  ranged from 34% to 68% — "a large move" is a different question in a calm year than in a
  wild one. A volatility-scaled threshold fixes that but predicts worse, so the fixed one
  stands, with the instability documented rather than hidden (E021).
- **Nothing fancier helped.** Gradient-boosted trees and an interaction model were each tried
  once with settings fixed in advance: 1.04× and 1.01× the logistic's skill, neither clearing
  a pre-registered bar of 1.10×, and the interaction model failed calibration (E020). Of the
  nine inputs, one is literally arithmetic — `vol_ratio_24_168` equals `rv_24` minus `rv_168`
  after the log transforms — and six carry 99.4% of the skill (E018).
- **Confidence is still a labelled heuristic** for the direction signal (it was shown
  uninformative in E001); the calibrated number is the move-size probability, not the
  BUY/HOLD/SELL confidence.
- A 13.5-month **holdout (2025-07 → 2026-08) is sealed** and will be used exactly once, at
  the end, to confirm — never to tune. It matters more than it used to: **twenty-plus
  experiments have now examined the validation period**, so validation results are treated as
  hypothesis-generating rather than confirmatory, and the holdout is the only clean arbiter
  left.

Full record: `research/ROADMAP.md` (what was done, in order), `research/EXPERIMENTS.md`
(every experiment, pre-registered criteria, results), `research/results/*/summary.md`.

## How it runs

Every hour (Supabase `pg_cron` → GitHub Actions `workflow_dispatch` at :12, with GitHub's own
cron as backup), on GitHub's servers:

1. fetch the last 250 closed hourly candles (Binance; CoinGecko fallback, flagged)
2. compute indicators and chart patterns; score trend, momentum, volume, patterns
3. fetch RSS news limited to the information cutoff (the reference candle's close); a
   structured Claude call scores it
4. combine deterministically → signal + confidence; a second Claude call writes the
   explanation *after* the decision (it cannot change it — tested)
5. store everything (inputs, scores, versions, data-quality flags, git commit) in Postgres,
   append-only
6. grade older predictions against the exact later candle (1h/6h/24h/72h/168h)
7. shadow: the frozen move-size model's probability for the hour, in its own table, graded
   an hour later

Weekly: `python -m agent.research.weekly_report` — health, the live signal record, the
shadow record with intervals, live/research parity, drift vs the development data.

## Module map

```
agent/
  orchestrator.py        one hourly run, start to finish (the information cutoff lives here)
  data_providers/        Binance (primary), CoinGecko (fallback), candle validation, facade
  indicators/ patterns/  deterministic technical inputs (pandas-ta-classic)
  scoring/ decision/     category scores -> overall score -> signal; confidence heuristic
  news/                  RSS feeds, availability-time rules, de-duplication
  ai/                    the two narrow Claude calls (news score; explanation)
  database/              schema (append-only, invariants as CHECKs/triggers, locked against
                         Supabase's public API), writes, security.py (the live exposure check)
  migrate.py             the ONLY way to change the schema: all schema files, one transaction
  outcome_tracker.py     grades predictions by the exact target candle; 'unavailable' on gaps
  healthcheck.py         fails the job if the newest prediction is stale
  shadow/                frozen move-size model (JSON artefact), features, run, grading
  api/state.py           the backend contract: what the backend says about itself, with every
                         number carrying whether it is a probability (docs/api/contract_v1.md)
  research/              everything experimental: periods & holdout guard, labels, features,
                         replay, walk-forward, calibration, model bench, parity, drift,
                         weekly report, holdout evaluation (sealed)
research/                roadmap, experiment log + JSONs, results, live-evaluation protocol
docs/research/           parity rules, data sources, failure modes, reproducibility, versions
docs/ops/                external trigger, security audit, performance review,
                         observability review, open user actions, incident write-up
docs/api/                the frontend contract (read this before building any screen)
tests/                   292 tests, no network or database (CI enforces that with an
                         unreachable DATABASE_URL); tests/integration (opt-in, real DB)
```

## Running it yourself

Python 3.12. `pip install -r requirements.txt` (pinned). Copy `.env.example` to `.env`
(Anthropic key, Supabase `DATABASE_URL`; optional CoinGecko key). Then, from the project
folder: `python run.py --no-save` for one analysis without writing, `python -m pytest tests/`
for the tests. Everything else is listed in `CLAUDE.md` → "How to run things".

## Principles that are enforced, not just stated

Point-in-time correctness (nothing after the cutoff, ever; tests garble the future and check
the past is unchanged) · no fabricated data (gaps stay gaps; missing → `unavailable`) ·
pre-registered experiments with fixed pass rules · chronological validation with purge and
embargo · one change at a time · versions on everything (pipeline, scoring, model artefact,
schema, git commit) with tests that fail on silent change · the explanation can never touch
the decision · the holdout stays sealed.

## Disclaimer

For research and personal use. Not financial advice. Any decision made with it is the
user's own responsibility.
