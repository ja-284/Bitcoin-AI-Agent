# Operational status — read this first

## Mode: POST-500H MONITORING-ONLY (since 2026-10-13)

The registered 500-hour first look was taken on 2026-10-13 (`research/monitoring/checkpoint_500h.md`; no
verdict, by registration). The strict readiness audit that follows it is revision 3 of
`docs/research/readiness_gate.md`. The monitoring-only rules in force since 2026-09-26 (the completed
pre-500h plan, `research/INTERIM_PLAN_PRE_500H.md`) carry on unchanged towards the 2,000-hour reading:

- the live system keeps running, prospective data keeps accumulating, and the heartbeat and watchdog keep
  alarming, all without anyone at a PC;
- hourly health is monitored at each working session; real production, security, data-integrity and
  reliability problems are still fixed (versioned, tested, their effect on the evaluation documented);
- scheduled audits still run (weekly report, integration drift check, dependency audit);
- **no predictive tuning, no frontend work, no ML, and no new research experiment** unless new live or
  system evidence raises a genuinely new question;
- the frozen model `move_size_1h_v1` continues untouched, and the 2,000- and 5,000-hour checkpoints stay
  exactly as registered (`research/LIVE_EVALUATION.md`).

**New since 2026-10-13, by the user's decision of 2026-10-11:** three operational changes, one at a time,
each with tests and its own commit (the last section of this file). None of them touches prediction,
scoring, the model or the checkpoints.

This is a freeze **for the current prospective evaluation**, not a permanent one. Other work happens only
for: (1) a real production problem, (2) a security, data-integrity or reliability problem, (3) a scheduled
audit that is due, (4) genuinely new evidence from the live system, (5) a registered checkpoint, (6) the
approved operational changes, in their order.

## Snapshot — the only time-dependent figures in this file

**Snapshot taken 2026-10-13 19:46 UTC.** Each figure names the command that is its source of truth. If
this snapshot is old, run the command. The command is authoritative, not this file. The same figures are
in [`status.json`](status.json), and `tests/test_status_docs.py` fails if the two disagree with each
other or with the versions in the code. **Update both, together, from the commands below.**

| figure | value at the snapshot | source of truth (run it for the current value) |
|---|---|---|
| graded prospective shadow hours | **520 of 2000** | `python -m agent.reporting health` → `checkpoint_progress`, which applies the registered checkpoint's own selection function (`prospective_graded`). Since the 500-hour reading exists, `python -m agent.research.live_checkpoint` only says so until 2,000 is reached |
| 500-hour first look | **taken 2026-10-13 19:33 UTC**, no verdict (by registration); read in the readiness gate's revision 3 | `research/monitoring/checkpoint_500h.md` (written once by the command; never rewritten) |
| next checkpoint expected | **≈ 2026-12-14, late morning UTC**: the 2,000-hour E012 verdict (an estimate: 1,480 more hours at one per hour, if none are lost; each lost hour adds one) | derived from the count above |
| newest prediction | the 18:00 UTC hour, 0.8 h after its candle closed: **OK** | `python -m agent.healthcheck --max-age-hours 2` |
| published backend state | refreshed 19:34 UTC, health **ok** | the `backend_state` table (rewritten by every hourly run) |
| private stats read model | refreshed 19:35 UTC; `headline_status` **healthy** (it looks back 24 h) | `reporting_snapshot.generated_at` ([`docs/api/stats_access.md`](../api/stats_access.md)) |
| sealed holdout | **sealed** for evaluation (`research/HOLDOUT_ACCESS.log` does not exist): never scored, nothing learned from it. **Not "untouched"**: raw candles of its last weeks were fetched as warm-up inputs, and the whole period is stored on disk (`research/AUDIT_2026-10-08.md` §18.2) | the file's absence |
| run history, outcomes, running statistics, health (read-only, on demand) | see the reporting layer | `python -m agent.reporting all --pretty` ([`docs/api/reporting_v1.md`](../api/reporting_v1.md)) |
| everything else that moves (parity, cost, drift flags, the free-rule comparison) | see the latest weekly report | `python -m agent.research.weekly_report` → `research/monitoring/weekly_<date>.md` |

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
- Readiness gate, revision 3 (2026-10-13): **19 PASS, 3 PARTIAL**, a **RELEASE CANDIDATE, not FINAL**
  (`docs/research/readiness_gate.md`). The PARTIALs: calibration (not yet confirmed prospectively),
  observability (a single missed hour can pass with no alarm), and prospective monitoring (only time
  closes it).
- Research is isolated from production: E026–E029 ran on development data only, and no research module is
  imported by the live or shadow path (tested). None of them changed anything that runs.
- **Private stats read model (2026-09-27, `docs/api/stats_access.md`): the only thing readable through
  Supabase's API.** Three reporting tables (snapshot, run history, incidents; the last since 2026-10-05),
  SELECT only, for one signed-in viewer with an owner-set claim. No viewer account exists yet, and the
  website is a separate side project (frontend handoff: `docs/api/stats_website_handoff.md`). `anon`
  reads nothing. It is not the trading application, and nothing in the prediction system reads these tables.

## What happens automatically (no one needs to do anything)

1. **Every hour at :12 UTC** Supabase `pg_cron` starts the hourly workflow on GitHub (the reliable path).
   GitHub's own slots at :07/:22/:37/:52 are the backup and exit early once the hour is saved.
2. Each run: fetch candles (Binance; CoinGecko fallback, marked synthetic) → news → scoring → save the
   prediction → grade older outcomes → self-check the hour was saved → shadow probability → grade shadow
   rows → publish `backend_state` → **ping the heartbeat**.
3. A failed news or explanation call degrades the hour **visibly** (news weight 0, error recorded). It never
   fabricates a value. Missing price data fails the run loudly.
4. **Alarms:**
   - The **self-check** fails a run whose hour was not saved, i.e. the newest prediction is more than 2 h
     old (GitHub emails). A single missed hour followed by a good run does not fail it. That hour shows
     as missing in the weekly report, the published state and the stats incident history.
   - The **watchdog** runs on GitHub, nominally every 3 h but really every 5–7 h. It checks staleness,
     repeated shadow errors, public-API exposure, and that the jobs run as `bitcoin_agent` with exactly
     their proven rights.
   - The **heartbeat** (healthchecks.io, outside GitHub) emails if no successful run pings for 1 h 30 min,
     and at once on a failed run.
   - **A single missed hour** (since 2026-10-14): the run that saves the first hour after a gap sends the
     heartbeat check a failure signal naming the missing hour(s), so healthchecks.io emails "down" with
     the hours in the check's log. The success ping seconds later emails "up" again. Each gap is reported
     once, and a late run is never reported, because an hour is missing only once a later hour is saved
     (nothing is backfilled). A complete GitHub outage is still caught by the heartbeat's silence alarm.
5. **After each completed hourly or watchdog run**, the separate *Reporting snapshot* workflow:
   - first records a FAILED run as an incident (`python -m agent.reporting.incidents`, since 2026-10-05);
   - then refreshes the private stats read model (`python -m agent.reporting.publish`).

   It is downstream only: it reads the record read-only and writes only the three reporting tables. Its
   failure cannot touch the live record, and it emails only once the snapshot is more than 3 hours old.
6. **Every hour at :47 UTC** (since 2026-10-14) a second `pg_cron` job, `dispatch-response-log`, copies
   GitHub's answers to the :12 dispatch into `dispatch_responses`, before `pg_net` deletes them after
   6 h.
   - It keeps the status, timed-out flag, error text and GitHub's request id, redacted and
     length-capped. It never keeps a header otherwise, a successful answer's body, or the request with
     its token.
   - Rows are kept 90 days.
   - The table is owner-only; the job role and the public API hold nothing on it.
   - It is a separate job from the dispatch, so its failure can never stop one.
   - Read it with `python -m agent.database.dispatch_log [--hours 48 --list]`.

**Nothing routine needs the user.** Nothing in production depends on a PC being on, on a working session
happening, or on the weekly audit being run on time.

## Scheduled checks (Claude, at working sessions; none keeps the system running)

- **Every session:** the hourly-health loop. It covers every hour saved, roles, sources, errors, shadow
  rows and outcomes, heartbeat and watchdog runs, cost, and the snapshot above.
- **Weekly audit, last done 2026-10-13** (at the 500-hour checkpoint session: report
  `research/monitoring/weekly_2026-10-13.md`, integration 36/36, 0 known vulnerabilities), **next due
  ≈ 2026-10-20**: `python -m agent.research.weekly_report`,
  `BITCOIN_AGENT_DB_TESTS=1 python -m pytest tests/integration -q` (drift check), and
  `python tools/dependency_audit.py`.
- **The 2,000-hour checkpoint** (below), at the first session after 2,000 graded hours.

## Known, non-critical — nothing to do

- GitHub fires the watchdog irregularly (≈ 4 of 7 slots a day). The heartbeat covers the gap.
- **The heartbeat proves a successful workflow run, not a saved hour** (found 2026-10-08).
  - An early-exit backup run pings too, so until 2026-10-14 a single missed hour could pass with no alarm
    at all. On 2026-10-07 the pings were 87 min apart, against an allowance of 90 min.
  - **Closed 2026-10-14 by the missed-hour signal** (alarms, above). It is proven by tests and by a
    local delivery check, and its step is watched in the live runs. A real missed hour has not happened
    since, so the email itself has not been seen yet.
  - A missed hour still shows in the weekly report, `backend_state` health and the stats incident
    history.
- AI cost follows the news week. The first full measured week (to 2026-10-05) came to ≈ $0.0135 a run,
  ≈ $9.75 per 30 days, under the accepted ~$12. The weekly report flags a projection above $15.
- Supabase grants its `net` schema to PUBLIC (unrevocable by this project). It is not an exposed API
  schema (checked 2026-09-24), so it is unreachable from outside.
- Permanent, documented gaps, never backfilled:
  - 9 missing hours on go-live weekend (2026-09-19/20);
  - 7 missing shadow hours (incident 2026-09-21/22; first written as 8, corrected 2026-09-27);
  - 17 hours with news unavailable (2026-09-21/22, marked);
  - **1 missing hour, 2026-10-05 19:00 UTC.** GitHub had no runner free:
    - the 20:12 dispatched run waited 15 min without one and was cancelled;
    - the 21:12 run waited 10 min, then succeeded;
    - GitHub fired none of its backup slots between 20:12 and 22:32.

    Our code never started. The record, every other hour and the shadow record are unaffected. The
    stats incident history shows it, as the failed run (with its link) and as the missing hour.
  - **1 missing hour, 2026-10-07 14:00 UTC. No run started between 14:46 and 16:12 UTC.**
    - Supabase's `pg_cron` queued the 15:12 dispatch ("succeeded").
    - GitHub's answer to it is gone, because `pg_net` keeps responses about 6 h. *(Since 2026-10-14 the
      answers are kept for 90 days, item 6 above, so a future case can be told apart.)*
    - GitHub fired none of its backup slots.
    - The cause is therefore unknown. Nothing failed, so no incident was recorded; the stats history
      shows the missing hour.
- Runtime ≈ 75–80 s per real run, under a tenth of the 15-minute budget.
- The free 24h-EWMA reference (weekly report, checkpoint) downloads raw candles as warm-up, and at the
  500-hour checkpoint those reach into the holdout period's last weeks. No holdout performance is computed,
  shown or used, and their weight in any value used is below 2e-10. It is recorded precisely in
  `research/LIVE_EVALUATION.md` (500-hour procedure, item 3) and left unchanged as registered checkpoint
  code. Clipping the warm-up would be a separate, later decision.
  - *Added 2026-10-11:* the E000 backtest (2026-09-19) also used about 233 holdout-period candles
    (2026-08-10 → 08-19) as indicator warm-up. Its scored hours all lay in the buffer.
  - The 2026-09-19 snapshot stores the whole holdout period.
  - Full account: audit §18.2.
- **Watch item — the calm market (drift flag "outcomes" in the weekly report since 2026-09-26).** The live
  market is calmer than in development (large moves in ~34% of hours vs ~47% on validation). The pipeline
  is ruled out. The model may be over-stating slightly in this calm market. It is judged **only** at the
  registered checkpoints and never tuned. Context from development data, none of which changes a rule:
  - **E026:** the model family was calibrated in calm markets historically, so a *persistent* live
    over-statement would be a genuine deviation.
  - **E027:** it over-states at night and under-states in the US session.
  - **E029:** its calibration naturally wanders in multi-week runs about three to four times a year, so a
    few weeks of over-statement is not by itself a deviation.
  - **2026-10-05 weekly report (descriptive):** the market stays calm (large moves in 32% of live hours).
    Two inputs, `tr_mean_14_rel` and `trades_rel_168h`, now sit below the development 1st percentile in
    about 12% of live hours, so the model is partly working in calmer conditions than anything it was
    built on. On 328 graded hours it is still ahead of the free EWMA rule (Brier 0.1972 vs 0.2134).
    Recorded, never tuned on; read at the registered checkpoints.
  - **The 500-hour first look (2026-10-13, registered, no verdict):** all 500 hours were calm. The model
    stated 0.335 on average where large moves happened in 0.304 of hours, about 0.03 too high. Its ECE was
    0.059, ordinary at that size (E024). It was still ahead of the free EWMA rule (Brier 0.1927 vs
    0.2091). This remains a watch item for the 2,000- and 5,000-hour readings.

## Emergency-only — when the user should act

| you receive | what it most likely means | what to do |
|---|---|---|
| healthchecks.io "DOWN" email, and it stays down > 3 hours | no successful run for hours | Look at GitHub → Actions. If runs fail with *permission denied*, roll back the database switch: copy the `DATABASE_URL` line from your local `.env` into the GitHub secret `DATABASE_URL`. Otherwise wait for the next session. |
| GitHub "run failed" emails for several hours in a row | a persistent failure (a source down, a secret, a code defect) | Nothing is lost while it fails; the hour simply isn't recorded. Leave it for the next session unless it lasts > 1 day. |
| an Anthropic "credit balance" or billing email | the AI calls will start failing | Top up the Anthropic account. The runs keep saving predictions meanwhile, marked "news unavailable". |
| a Supabase email about pausing or limits | the free project is at risk | Open the dashboard and follow its instructions (hourly writes should prevent pausing; storage is ~28 MB of 500 MB). |
| a GitHub "Reporting snapshot" failed email | the private stats snapshot has not refreshed for over 3 hours | Nothing is lost and the live system is unaffected (the stats website would show older data). Leave it for the next session. |
| a GitHub email that scheduled workflows were disabled | 60 days without repository activity | Click "enable" in the Actions tab. Not expected before ≈ 2026-12-12; any commit resets the clock. |

**Calendar:** renew the GitHub token `supabase-dispatch` before **2027-09-20**
(`docs/ops/open_user_actions.md` item 3).

## The registered checkpoints (unchanged)

**500 hours: done, 2026-10-13.** `python -m agent.research.live_checkpoint` wrote
`research/monitoring/checkpoint_500h.md` (and `.json`) once, at 19:33 UTC, and they were committed
unchanged.

- It used exactly the first 500 graded hours, 2026-09-21 17:00 → 2026-10-12 21:00 UTC (rule 8).
- It is a first look with **no verdict**, by registration, and it is read in revision 3 of
  `docs/research/readiness_gate.md`.
- It was not blind (400 of its hours were reviewed in aggregate on 2026-10-08), and every one of its
  hours was in the low-volatility regime.

**Next: 2,000 hours, the E012 verdict (≈ 2026-12-14).** At the first working session after 2,000 graded
prospective hours, run `python -m agent.research.live_checkpoint`:

- First confirm that `research/monitoring/` holds no reading for 2,000 hours yet. The command skips
  anything already present, and on 2026-10-11 an empty stray file appeared under the 500-hour name.
- It reads **exactly the first 2,000** prospective graded hours in time order. Later hours belong to the
  5,000-hour reading.
- It refuses to run early and never rewrites a computed checkpoint (tested). It states whether every
  judged probability reproduces from its stored inputs (clarification 11).
- It gives **the E012 verdict**, calibration by bucket with intervals, the comparison with the free
  24h-EWMA rule, and weekday/weekend and hour-of-day blocks. The blocks are descriptive and are read
  against E027's development offsets.
- The user's "no separate approval" decision (2026-10-11) was given for the 500-hour reading. Confirm
  with the user that it also covers this one.
- E024: a model as good as on validation passes every E012 part in about 98% of 2,000-hour stretches.
  A fail there means something.
- Commit the reading together with this file's and `status.json`'s move to the next checkpoint:
  `tests/test_status_docs.py` requires every earlier reading to exist exactly when the status names a
  later checkpoint.
- Afterwards a dated readiness assessment is added to the gate, again.

**Then 5,000 hours:** the E013 verdict (≈ spring 2027).

## After the readiness audit, in order (the user's decisions, 2026-10-11)

1. The single-missed-hour alarm. **Done 2026-10-14** (alarms, above).
2. Then keeping GitHub's answers to the dispatch requests (trigger responses). **Done 2026-10-14**
   ("What happens automatically", item 6).
3. News cost and value, reviewed separately, with no change to the live weights or model.

Each comes one at a time, with tests and its own commit. Also waiting on the user:

- The registered **news first look** (descriptive) has enough hours (553 usable, weekly report
  2026-10-13) and waits for the user's go-ahead.
- A properly registered study for the 2,000-hour milestone may be considered; that is the user's
  decision. The calm-market study has lapsed.

The holdout opens only on the user's explicit instruction. Before any E014/E023 run, the E000 backtest
runner's bypass of the holdout guard must be fixed first.
