# Operational status — read this first

**As of 2026-09-26 ~09:00 UTC.** Machine-readable copy: [`status.json`](status.json). Updated at every
working session; if the date above is old, the live record (`python -m agent.research.weekly_report`) is
the truth.

## Production state

- **Live since 2026-09-19**, hourly, analysis only — no trading capability exists anywhere.
- Versions, all frozen for the prospective evaluation: pipeline **0.2.0**, scoring **0.2.0** (the
  BUY/HOLD/SELL signal — *no demonstrated predictive value*, E001/E017), shadow model **`move_size_1h_v1`**
  (the calibrated 1h move-size probability under prospective test), schema **4**, contract **v1**.
- The jobs connect to the database as **`bitcoin_agent`** (least privilege: read and append only), since
  2026-09-25 19:12 UTC — the hourly job (every row stamped `db_role = bitcoin_agent`) and the watchdog
  (verified 2026-09-26 11:42 UTC by its own role check). The local `.env` keeps the owner role for maintenance.
- Sealed holdout: **sealed** (`research/HOLDOUT_ACCESS.log` does not exist).
- Readiness gate: **21 PASS, 1 PARTIAL** — the PARTIAL is prospective monitoring, which only time closes.

## Prospective evidence so far

- **103 graded prospective shadow hours of 500** (2026-09-26 08:53 UTC). Accrues about one per hour.
  **First checkpoint ≈ 2026-10-12, evening UTC**, if no hours are lost.
- News evaluation: first look at 500 usable news hours ≈ 2026-10-11; verdict only from 3,140 hours (E025).

## What happens automatically (no one needs to do anything)

1. **Every hour at :12 UTC** Supabase `pg_cron` starts the hourly workflow on GitHub (the reliable path);
   GitHub's own slots at :07/:22/:37/:52 are the backup and exit early once the hour is saved.
2. Each run: fetch candles (Binance; CoinGecko fallback, marked synthetic) → news → scoring → save the
   prediction → grade older outcomes → self-check the hour was saved → shadow probability → grade shadow
   rows → publish `backend_state` → **ping the heartbeat**.
3. A failed news or explanation call degrades the hour **visibly** (news weight 0, error recorded); it
   never fabricates a value. Missing price data fails the run loudly.
4. **Alarms:** the self-check fails the next run if an hour is missing (GitHub emails); the **watchdog**
   (GitHub, nominally every 3 h — really every 5–7 h) checks staleness, repeated shadow errors, public-API
   exposure, and that the jobs run as `bitcoin_agent` with exactly their proven rights; the **heartbeat**
   (healthchecks.io, outside GitHub) emails if no successful run pings for 1 h 30 min, and at once on a
   failed run.

## Known, non-critical — nothing to do

- GitHub fires the watchdog irregularly (≈ 4 of 7 slots a day). The heartbeat covers the gap.
- AI cost follows the news week: ≈ $0.015 a run at weekends, ≈ $0.019–0.020 on busy weekdays — about
  $11–14 a month, around the accepted ~$12. The weekly report flags a projection above $15.
- Supabase grants its `net` schema to PUBLIC (unrevocable by this project); it is not an exposed API
  schema (checked 2026-09-24), so it is unreachable from outside.
- Permanent, documented gaps — never backfilled: 9 missing hours on go-live weekend (2026-09-19/20), 8
  missing shadow hours (incident 2026-09-21/22), 17 hours with news unavailable (2026-09-21/22, marked).
- Runtime ≈ 75–80 s per real run, under a tenth of the 15-minute budget.
- **Drift flag "outcomes" in the weekly report (since 2026-09-26) — expected, understood:** the live market
  is calmer than in development (large moves in ~34% of hours vs ~47% on validation). The pipeline is ruled
  out. Watch item: the model may be over-predicting slightly in this calm market; E026 shows it was calibrated
  in calm markets historically, so if this persists it is a genuine deviation — judged at the registered
  checkpoints only, never tuned.

## Emergency-only — when the user should act

| you receive | what it most likely means | what to do |
|---|---|---|
| healthchecks.io "DOWN" email, and it stays down > 3 hours | no successful run for hours | Look at GitHub → Actions. If runs fail with *permission denied*, roll back the database switch: copy the `DATABASE_URL` line from your local `.env` into the GitHub secret `DATABASE_URL`. Otherwise wait for the next session. |
| GitHub "run failed" emails for several hours in a row | a persistent failure (a source down, a secret, a code defect) | Nothing is lost while it fails — the hour simply isn't recorded. Leave it for the next session unless it lasts > 1 day. |
| an Anthropic "credit balance" or billing email | the AI calls will start failing | Top up the Anthropic account. The runs keep saving predictions meanwhile, marked "news unavailable". |
| a Supabase email about pausing or limits | the free project is at risk | Open the dashboard and follow its instructions (hourly writes should prevent pausing; storage is 17 MB of 500 MB). |
| a GitHub email that scheduled workflows were disabled | 60 days without a commit | Click "enable" in the Actions tab (not expected: sessions commit regularly). |

Nothing else needs the user. **The only calendar item:** renew the GitHub token `supabase-dispatch`
before 2027-09-20.

## The next checkpoint, exactly

At the first working session after **500 graded prospective hours** (≈ 2026-10-12):
`python -m agent.research.live_checkpoint`. It reads **exactly the first 500** prospective hours (so the
day it is run changes nothing) and reports skill, ranking and calibration with intervals, against the
free 24h-EWMA rule. **By registration the 500-hour reading gives no verdict** (`research/LIVE_EVALUATION.md`);
intervals at that size are known to be optimistic (E025), and ECE above 0.03 is expected there (E024).

**After it, in order:** a strict final readiness audit (predictive evidence, calibration, uncertainty,
leakage, data quality, parity, security, database integrity, automation, monitoring, reproducibility,
failure handling, maintainability, performance) and a plain report of what is proven, what is uncertain,
and whether the backend is genuinely frontend-ready — a good reading never hides another problem, and a
weak one is investigated, never tuned against. Then: the news first look (descriptive); the 2,000-hour
E012 verdict (≈ December 2026); the 5,000-hour E013 verdict (≈ spring 2027). The holdout opens only on the
user's explicit instruction.

## Standing rules while waiting (`research/INTERIM_PLAN_PRE_500H.md`)

The predictive path is frozen; prospective outcomes are observations, never a tuning set; no frontend, no
ML, no busywork; every change is tested, documented, committed and pushed.
