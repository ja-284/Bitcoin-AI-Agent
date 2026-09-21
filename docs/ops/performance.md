# Performance and reliability review — 2026-09-21

Correctness came first; this review asks only whether anything is a real bottleneck or a
reliability risk. Numbers from GitHub's API over the last 60 runs.

## Runtime

| run type | n | median | min | max | budget |
|---|---|---|---|---|---|
| dispatch runs (do the hour's work: analysis + AI calls + outcomes + self-check; shadow steps from 19:12 UTC on) | 28 | **54 s** | 30 s | 67 s | 15 min job timeout |
| GitHub cron runs (usually exit early before any AI call) | 26 | 39 s | | | |

Of the ~54 s, roughly 25–30 s is the runner itself (checkout, Python set-up, `pip install`
with cache) and the rest is the work: one Binance request for 250 candles, three RSS
downloads, two Anthropic calls (the explainer dominates at ~5–15 s), ~15–20 short database
connections, up to five Binance lookups for outcomes. **No bottleneck.** The 15-minute
timeout leaves a 13-minute margin; every external call is now individually bounded (Phase B),
so the worst case is a few minutes, not a hang.

## API calls per hour

Binance: 1 (analysis) + 1 (shadow) + ≤ 5 + ≤ 1 (outcome lookups) ≈ 8 requests — far below
the public limit (1,200 weight/min). RSS: 3. Anthropic: 2 (cost well under $10/month, as
estimated). CoinGecko: 0 unless Binance fails. Supabase: ~20 connections/run through the
pooler; the free tier's limits are not approached.

## Recomputation

Nothing is recomputed unnecessarily in the hourly job. In research, the replay is cached per
(snapshot, range, versions) and feature snapshots are files; the walk-forward runs refit a
small logistic model per fold (seconds).

## Reliability

- **Trigger:** Supabase pg_cron → `workflow_dispatch` at :12 has fired 100% of hours since
  2026-09-20 08:12 UTC (median start delay 1 s). GitHub's own cron fires ~20–35% of its
  slots and is only a backup. A missed hour would be caught by the self-check (job fails),
  the 3-hourly watchdog, and the weekly report.
- **Retries:** exchange one retry per endpoint then the mirror then the fallback; LLM 2 SDK
  retries; database none (the next slot recomputes; writes are idempotent).
- **Recovery:** a failed slot costs nothing but that slot; the hour is recomputed by the next
  slot if it is still the same hour, otherwise it stays missing by design (no back-fill).
- **Known weak points:** a database outage across all slots of an hour loses that hour of the
  live record; the healthchecks.io external alarm is still not configured.

## Decision

No optimisation is warranted. The one change that would reduce wall time (reusing one database
connection per run instead of ~20) would save a few seconds and add shared state to code
paths that are currently simple and independently testable — not worth it at this scale.
Revisit if the runtime approaches a few minutes or if Supabase connection limits appear.
