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
- **Confidence is still a labelled heuristic** for the direction signal (it was shown
  uninformative in E001); the calibrated number is the move-size probability, not the
  BUY/HOLD/SELL confidence.
- A 13.5-month **holdout (2025-07 → 2026-08) is sealed** and will be used exactly once, at
  the end, to confirm — never to tune.

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
  database/              schema (append-only, invariants as CHECKs/triggers), writes
  outcome_tracker.py     grades predictions by the exact target candle; 'unavailable' on gaps
  healthcheck.py         fails the job if the newest prediction is stale
  shadow/                frozen move-size model (JSON artefact), features, run, grading
  research/              everything experimental: periods & holdout guard, labels, features,
                         replay, walk-forward, calibration, model bench, parity, drift,
                         weekly report, holdout evaluation (sealed)
research/                roadmap, experiment log + JSONs, results, live-evaluation protocol
docs/research/           parity rules, data sources, failure modes, reproducibility, versions
docs/ops/                external trigger, security audit, performance review
tests/                   185 tests, no network or database; tests/integration (opt-in, real DB)
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
