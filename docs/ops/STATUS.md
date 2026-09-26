# Operational status — read this first

## Mode: PRE-500H MONITORING-ONLY (since 2026-09-26)

The pre-500h plan (`research/INTERIM_PLAN_PRE_500H.md`) is complete: every section of its audit
(`research/INTERIM_PLAN_AUDIT.md`) is COMPLETE or CONTINUOUS. Until the registered 500-hour checkpoint:

- the live system keeps running, prospective data keeps accumulating, and the heartbeat and watchdog keep
  alarming, all without anyone at a PC;
- hourly health is monitored at each working session; real production, security, data-integrity and
  reliability problems are still fixed (versioned, tested, their effect on the evaluation documented);
- scheduled audits still run (weekly report, integration drift check, dependency audit);
- **no predictive tuning, no frontend work, no ML, and no new research experiment** unless new live or
  system evidence raises a genuinely new question;
- the 500-hour checkpoint stays exactly as registered (`research/LIVE_EVALUATION.md`).

This is a freeze **for the current prospective evaluation**, not a permanent one. Work resumes before
500 hours only for: (1) a real production problem, (2) a security, data-integrity or reliability problem,
(3) a scheduled audit that is due, (4) genuinely new evidence from the live system, (5) the 500-hour
checkpoint itself.

## Snapshot — the only time-dependent figures in this file

**Snapshot taken 2026-09-26 15:45 UTC.** Each figure names the command that is its source of truth. If
this snapshot is old, run the command. The command is authoritative, not this file. The same figures are
in [`status.json`](status.json), and `tests/test_status_docs.py` fails if the two disagree with each
other or with the versions in the code. **Update both, together, from the commands below.**

| figure | value at the snapshot | source of truth (run it for the current value) |
|---|---|---|
| graded prospective shadow hours | **110 of 500** | `python -m agent.research.live_checkpoint`: the checkpoint's own selection rule; before 500 it prints the count and writes nothing |
| first checkpoint expected | **≈ 2026-10-12, late evening UTC** (390 more hours at one per hour, if none are lost) | derived from the count above |
| newest prediction | the 14:00 UTC hour, 0.8 h after its candle closed: **OK** | `python -m agent.healthcheck --max-age-hours 2` |
| published backend state | refreshed 15:12 UTC, health **ok** | the `backend_state` table (rewritten by every hourly run) |
| sealed holdout | **sealed** (`research/HOLDOUT_ACCESS.log` does not exist) | the file's absence |
| everything else that moves (missed hours, parity, cost, drift flags, shadow errors) | see the latest weekly report | `python -m agent.research.weekly_report` → `research/monitoring/weekly_<date>.md` |

## Production state (changes only by a versioned, committed decision)

- **Live since 2026-09-19**, hourly, analysis only. No trading capability exists anywhere. Automated
  execution is a long-term goal recorded as **NOT ACTIVE** in `docs/FUTURE_EXECUTION_ARCHITECTURE.md`;
  none of it may be built during this evaluation.
- Versions, all frozen for the prospective evaluation: pipeline **0.2.0**, scoring **0.2.0** (the
  BUY/HOLD/SELL signal, *no demonstrated predictive value*, E001/E017), shadow model **`move_size_1h_v1`**
  (the calibrated 1h move-size probability under prospective test), schema **4**, contract **v1**.
- The jobs connect to the database as **`bitcoin_agent`** (least privilege: read and append only), since
  2026-09-25 19:12 UTC. The hourly job stamps every row `db_role = bitcoin_agent`, and the watchdog's role
  check has verified it (first 2026-09-26 11:42 UTC). The local `.env` keeps the owner role for maintenance.
- Readiness gate: **21 PASS, 1 PARTIAL**. The PARTIAL is prospective monitoring, which only time closes
  (`docs/research/readiness_gate.md`).
- Research is isolated from production: E026–E029 ran on development data only, and no research module is
  imported by the live or shadow path (tested). None of them changed anything that runs.

## What happens automatically (no one needs to do anything)

1. **Every hour at :12 UTC** Supabase `pg_cron` starts the hourly workflow on GitHub (the reliable path).
   GitHub's own slots at :07/:22/:37/:52 are the backup and exit early once the hour is saved.
2. Each run: fetch candles (Binance; CoinGecko fallback, marked synthetic) → news → scoring → save the
   prediction → grade older outcomes → self-check the hour was saved → shadow probability → grade shadow
   rows → publish `backend_state` → **ping the heartbeat**.
3. A failed news or explanation call degrades the hour **visibly** (news weight 0, error recorded). It never
   fabricates a value. Missing price data fails the run loudly.
4. **Alarms:**
   - The **self-check** fails the next run if an hour is missing (GitHub emails).
   - The **watchdog** runs on GitHub, nominally every 3 h but really every 5–7 h. It checks staleness,
     repeated shadow errors, public-API exposure, and that the jobs run as `bitcoin_agent` with exactly
     their proven rights.
   - The **heartbeat** (healthchecks.io, outside GitHub) emails if no successful run pings for 1 h 30 min,
     and at once on a failed run.

**Nothing routine needs the user.** Nothing in production depends on a PC being on, on a working session
happening, or on the weekly audit being run on time.

## Scheduled checks (Claude, at working sessions; none keeps the system running)

- **Every session:** the hourly-health loop. It covers every hour saved, roles, sources, errors, shadow
  rows and outcomes, heartbeat and watchdog runs, cost, and the snapshot above.
- **Weekly audit, next due ≈ 2026-10-02** (or the first session after it, if the user is away):
  `python -m agent.research.weekly_report`, `BITCOIN_AGENT_DB_TESTS=1 python -m pytest tests/integration -q`
  (drift check), and `python tools/dependency_audit.py`. The first report covering a full measured week of
  AI cost is due then (cost has been measured since Wednesday 2026-09-23).
- **The 500-hour checkpoint** (below), at the first session after 500 graded hours.

## Known, non-critical — nothing to do

- GitHub fires the watchdog irregularly (≈ 4 of 7 slots a day). The heartbeat covers the gap.
- AI cost follows the news week: ≈ $0.013–0.015 a run at weekends, ≈ $0.019–0.020 on busy weekdays, which
  is about $11–14 a month, around the accepted ~$12. The weekly report flags a projection above $15.
- Supabase grants its `net` schema to PUBLIC (unrevocable by this project). It is not an exposed API
  schema (checked 2026-09-24), so it is unreachable from outside.
- Permanent, documented gaps, never backfilled: 9 missing hours on go-live weekend (2026-09-19/20), 8
  missing shadow hours (incident 2026-09-21/22), 17 hours with news unavailable (2026-09-21/22, marked).
- Runtime ≈ 75–80 s per real run, under a tenth of the 15-minute budget.
- The free 24h-EWMA reference (weekly report, checkpoint) downloads raw candles as warm-up, and at the
  500-hour checkpoint those reach into the holdout period's last weeks. No holdout performance is computed,
  shown or used, and their weight in any value used is below 2e-10. It is recorded precisely in
  `research/LIVE_EVALUATION.md` (500-hour procedure, item 3) and left unchanged as registered checkpoint
  code. Clipping the warm-up would be a separate, later decision.
- **Watch item — the calm market (drift flag "outcomes" in the weekly report since 2026-09-26).** The live
  market is calmer than in development (large moves in ~34% of hours vs ~47% on validation). The pipeline
  is ruled out. The model may be over-stating slightly in this calm market. It is judged **only** at the
  registered checkpoints and never tuned. Context from development data, none of which changes a rule:
  - **E026:** the model family was calibrated in calm markets historically, so a *persistent* live
    over-statement would be a genuine deviation.
  - **E027:** it over-states at night and under-states in the US session.
  - **E029:** its calibration naturally wanders in multi-week runs about three to four times a year, so a
    few weeks of over-statement is not by itself a deviation.

## Emergency-only — when the user should act

| you receive | what it most likely means | what to do |
|---|---|---|
| healthchecks.io "DOWN" email, and it stays down > 3 hours | no successful run for hours | Look at GitHub → Actions. If runs fail with *permission denied*, roll back the database switch: copy the `DATABASE_URL` line from your local `.env` into the GitHub secret `DATABASE_URL`. Otherwise wait for the next session. |
| GitHub "run failed" emails for several hours in a row | a persistent failure (a source down, a secret, a code defect) | Nothing is lost while it fails; the hour simply isn't recorded. Leave it for the next session unless it lasts > 1 day. |
| an Anthropic "credit balance" or billing email | the AI calls will start failing | Top up the Anthropic account. The runs keep saving predictions meanwhile, marked "news unavailable". |
| a Supabase email about pausing or limits | the free project is at risk | Open the dashboard and follow its instructions (hourly writes should prevent pausing; storage is ~17 MB of 500 MB). |
| a GitHub email that scheduled workflows were disabled | 60 days without repository activity | Click "enable" in the Actions tab. Not expected before ≈ 2026-11-25; any commit resets the clock. |

**Calendar:** renew the GitHub token `supabase-dispatch` before **2027-09-20**
(`docs/ops/open_user_actions.md` item 3).

## The 500-hour checkpoint, exactly (registered; unchanged)

At the first working session after **500 graded prospective hours**, run
`python -m agent.research.live_checkpoint`:

- It reads **exactly the first 500** prospective graded hours in time order (rule 8 of
  `research/LIVE_EVALUATION.md`), so the day it is run changes nothing. Later hours belong to the next
  checkpoint and are never used for this one.
- It refuses to run early and never rewrites a computed checkpoint (tested).
- It states whether every judged probability reproduces from its stored inputs (clarification 11).
- It reports skill, ranking and calibration with intervals, against the free 24h-EWMA rule.
- **By registration the 500-hour reading gives no verdict.** Intervals at that size are known to be
  optimistic (E025), and ECE above 0.03 is expected there (E024).

**After it, in order:**

1. A strict final readiness audit covering predictive evidence, calibration, uncertainty, leakage, data
   quality, parity, security, database integrity, automation, monitoring, reproducibility, failure
   handling, maintainability and performance.
2. A plain report of what is proven, what is uncertain, and whether the backend is genuinely
   frontend-ready. A good reading never hides another problem, and a weak one is investigated, never
   tuned against.
3. Then the news first look (descriptive, ≈ 2026-10-11 by the weekly report's counter), the 2,000-hour
   E012 verdict (≈ mid-December 2026) and the 5,000-hour E013 verdict (≈ spring 2027).

The holdout opens only on the user's explicit instruction.
