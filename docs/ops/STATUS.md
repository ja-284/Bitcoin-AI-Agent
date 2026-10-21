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

**New since 2026-10-15, by the user's master plan (2026-10-14, Phase 3):** a separate prospective **direction
shadow track** (E034, `research/DIRECTION_TRACK.md`) collects its own pre-registered predictions in its own tables.
It never touches the live signal, `move_size_1h_v1` or its checkpoints, and its readings are blind (Amendment 1.1:
routine reports show only operational counts for it until each reading).

This is a freeze **for the current prospective evaluation**, not a permanent one. Other work happens only
for: (1) a real production problem, (2) a security, data-integrity or reliability problem, (3) a scheduled
audit that is due, (4) genuinely new evidence from the live system, (5) a registered checkpoint, (6) the
approved operational changes, in their order.

## Snapshot — the only time-dependent figures in this file

**Snapshot taken 2026-10-20 13:16 UTC.** Each figure names the command that is its source of truth. If
this snapshot is old, run the command. The command is authoritative, not this file. The same figures are
in [`status.json`](status.json), and `tests/test_status_docs.py` fails if the two disagree with each
other or with the versions in the code. **Update both, together, from the commands below.**

| figure | value at the snapshot | source of truth (run it for the current value) |
|---|---|---|
| graded prospective shadow hours | **682 of 2000** | `python -m agent.reporting health` → `checkpoint_progress`, which applies the registered checkpoint's own selection function (`prospective_graded`). Since the 500-hour reading exists, `python -m agent.research.live_checkpoint` only says so until 2,000 is reached |
| 500-hour first look | **taken 2026-10-13 19:33 UTC**, no verdict (by registration); read in the readiness gate's revision 3 | `research/monitoring/checkpoint_500h.md` (written once by the command; never rewritten) |
| next checkpoint expected | **≈ 2026-12-14, late morning UTC**: the 2,000-hour E012 verdict (an estimate: 1,318 more hours at one per hour, if none are lost; each lost hour adds one) | derived from the count above |
| newest prediction | the 12:00 UTC hour, 0.3 h after its candle closed: **OK** | `python -m agent.healthcheck --max-age-hours 2` |
| published backend state | refreshed 13:13 UTC, health **ok** | the `backend_state` table (rewritten by every hourly run) |
| private stats read model | refreshed 13:14 UTC; `headline_status` **healthy** (it looks back 24 h) | `reporting_snapshot.generated_at` ([`docs/api/stats_access.md`](../api/stats_access.md)) |
| sealed holdout | **sealed** for evaluation (`research/HOLDOUT_ACCESS.log` does not exist): never scored, nothing learned from it. **Not "untouched"**: raw candles of its last weeks were fetched as warm-up inputs, and the whole period is stored on disk (`research/AUDIT_2026-10-08.md` §18.2) | the file's absence |
| run history, outcomes, running statistics, health (read-only, on demand) | see the reporting layer | `python -m agent.reporting all --pretty` ([`docs/api/reporting_v1.md`](../api/reporting_v1.md)) |
| direction shadow track (E034) | **collecting since the 15:00 UTC hour of 2026-10-15**: 118 rows, 117 eligible graded, 0 errors, 0 lost hours, next reading at 1,000. Operational counts only, its readings are blind (Amendment 1.1). Integrity: `python -m agent.research.direction_integrity` 9 of 9 PASS (2026-10-20, weekly audit) | `python -m agent.research.direction_checkpoint` (prints counts; writes a reading only when due) |
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
- Readiness gate, revision 3 with addendum 2 (2026-10-15): **20 PASS, 2 PARTIAL**, a **RELEASE CANDIDATE, not
  FINAL** (`docs/research/readiness_gate.md`). Observability became PASS on 2026-10-15: the missed-hour email was
  seen delivered, and the dispatch answers are verified. The PARTIALs: calibration (not yet confirmed
  prospectively) and prospective monitoring (only time closes it).
- Research is isolated from production: E026–E029 ran on development data only, and no research module is
  imported by the live or shadow path (tested). None of them changed anything that runs.
- **Private stats read model (2026-09-27, `docs/api/stats_access.md`): the only thing readable through
  Supabase's API.** Three reporting tables (snapshot, run history, incidents; the last since 2026-10-05), SELECT
  only.
  - **Since 2026-10-21 they are readable ONLY by the Bitcoin AI Control Center's dedicated account, in a two-factor
    (aal2) session** (policy `control_center_read`). The old flag rule is gone.
  - The dashboard is a separate Lovable project. It is not yet connected to these tables; that is a separate,
    approved step.
  - `anon` reads nothing. It is not the trading application, and nothing in the prediction system reads these
    tables.
  - Emergency deny-all: `docs/api/stats_access.md` §2.

## What happens automatically (no one needs to do anything)

1. **Every hour at :12 UTC** Supabase `pg_cron` starts the hourly workflow on GitHub (the reliable path).
   GitHub's own slots at :07/:22/:37/:52 are the backup and exit early once the hour is saved.
2. Each run: fetch candles (Binance; CoinGecko fallback, marked synthetic) → news → scoring → save the
   prediction → grade older outcomes → self-check the hour was saved → shadow probability → grade shadow
   rows → publish `backend_state` → direction shadow probabilities → grade direction rows (since 2026-10-15,
   E034; a failure is recorded in `shadow_direction_errors` and exits 0) → **ping the heartbeat**.
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
   - **Failed AI calls** (since 2026-10-17, the user's approval after the Anthropic key rotation;
     `python -m agent.healthcheck --ai-failure-body-file`). Every run, backup slots included, looks at the newest
     saved hour.
     - If that hour's news step or explanation failed, it sends the heartbeat check a failure signal naming the
       error types, with a key hint for authentication or permission errors.
     - It then holds back the success ping, so healthchecks.io emails "down" once and the check stays down until
       an hour is saved with working AI calls ("up" again).
     - It never fails a job. Its delivery path (`/fail` with a body) is the missed-hour signal's, proven
       2026-10-15. The failing case has been tested but not yet seen live.
     - While the check is down for this reason, a GitHub outage raises no second email. The check is already red.
   - **The direction track's own alert** (since 2026-10-16; `agent/direction_shadow/health.py`), on a SEPARATE
     healthchecks.io check, never the main one:
     - a success ping when the latest closed hour has a valid direction observation;
     - nothing for a late hour that a later run can still record before its deadline (`as_of` + 2 h);
     - ONE "down" email per incident when an hour is lost for good. Each lost hour and each recovery is recorded
       once in `shadow_direction_health` (append-only, unique per hour);
     - "up" again on recovery. The check's silence alarm covers no runs at all.
     - **Verified end to end on 2026-10-16** (`open_user_actions.md` item 7): the labelled test's "down" email at
       16:51:41 UTC, then the hourly run's real success ping at 16:53:47 UTC sent "up". Read the state with
       `python -m agent.direction_shadow.health --status`.
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
   - Read it with `python -m agent.database.dispatch_log [--hours 48 --list]`. Since 2026-10-15 the weekly report's
     health section shows the week's answers too, flagged **ATTENTION** if any was refused, timed out or left no
     answer. A refused dispatch alarms by itself only if no backup slot saves the hour.

**Nothing routine needs the user.** Nothing in production depends on a PC being on, on a working session
happening, or on the weekly audit being run on time.

## Scheduled checks (Claude, at working sessions; none keeps the system running)

- **Every session:** the hourly-health loop. It covers every hour saved, roles, sources, errors, shadow
  rows and outcomes, heartbeat and watchdog runs, cost, and the snapshot above.
- **Weekly audit, last done 2026-10-20** (report `research/monitoring/weekly_2026-10-20.md`, cutoff 12:59 UTC;
  integration 43/43 including the drift check; 0 known vulnerabilities of 43; direction integrity 9 of 9;
  security and role checks OK). **Its gate (`tools/gate.py check --integration --all-mutations`) FAILED at the
  mutation step:** one guard's anchor in `tools/guard_mutations.py` ("the sealed holdout is no longer truncated")
  no longer matches `agent/research/history.py` since `59aa794` (2026-10-17), so the full mutation suite cannot
  start. The protection itself is still guarded ("load_bars no longer cuts a request at the holdout's start").
  **Repaired the same day, on the user's post-audit plan:**
  - `f05606b` re-points the guard;
  - `368df96` makes every commit check that each guard still finds its target (`tests/test_guard_anchors.py`);
  - the complete suite then caught **166 of 166** in a disposable clone (135.6 min, both controls held), with the
    repository and data files unchanged.

  **Next due ≈ 2026-10-27**:
  `python -m agent.research.weekly_report`,
  `BITCOIN_AGENT_DB_TESTS=1 python -m pytest tests/integration -q` (drift check), and
  `python tools/dependency_audit.py`.
  - Since 2026-10-21 the audit also reads the **calendar** below for anything due within four weeks, and raises it
    with the user.
  - The backup round-trip tests are paused (opt-in only), so the integration suite runs no GPG command.
- **The 2,000-hour checkpoint** (below), at the first session after 2,000 graded hours.

## Unresolved operational risk: no database backup (recorded 2026-10-21)

**No verified, recoverable backup of the database exists.** The Supabase project holds the **only copy** of the
prospective record:
- the live BUY/HOLD/SELL record and its outcomes;
- the move-size shadow record behind the 2,000- and 5,000-hour readings;
- the blind direction track;
- the news scores.

Supabase's Free plan keeps no backups. Losing the project (deletion, account loss, a provider incident) would lose all
of it **permanently**: none of it can be re-collected, and every registered reading would lose its data.
- **History:** an encrypted backup tool was built and tested on synthetic data on 2026-10-20 (`1820d8a`,
  `docs/ops/BACKUP.md`). The owner's GPG key could not be created (a `keyboxd` error on Windows), and the user then
  **paused the backup work** (2026-10-21).
- **Current state:** the tool is inactive. It has never touched real data, and nothing runs it.
- **This is an open risk, not a completed safety measure.** Revisiting it is the user's separate decision.

## Known, non-critical — nothing to do

- GitHub fires the watchdog irregularly (≈ 4 of 7 slots a day). The heartbeat covers the gap.
- **The heartbeat proves a successful workflow run, not a saved hour** (found 2026-10-08).
  - An early-exit backup run pings too, so until 2026-10-14 a single missed hour could pass with no alarm
    at all. On 2026-10-07 the pings were 87 min apart, against an allowance of 90 min.
  - **Closed 2026-10-14 by the missed-hour signal** (alarms, above). It is proven by tests and by a
    local delivery check, and its step is watched in the live runs. A real missed hour has not happened
    since, so the email itself has not been seen yet.
  - **To see the email without a real missed hour:** the manual workflow *Alert delivery test*
    (`.github/workflows/alert_test.yml`, since 2026-10-14). It sends ONE report labelled "DELIVERY TEST …
    NO hour is missing" through the same code and curl line. It has no schedule, needs no database, and
    records no incident.
    - **Done 2026-10-15:** the user ran it once, and the "down" email arrived (13:36 UTC) with the labelled
      text. Readiness row 18 is PASS.
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
  - *Closed 2026-10-14:* the backtest runner now refuses any window touching the holdout, and every route into
    the holdout is reviewed and tested (`research/HOLDOUT_ROUTES.md`, `tests/test_holdout_routes.py`).
  - *Closed 2026-10-14 (Amendment A1, protocol 1.1):* the EWMA warm-up of the weekly report and of the
    checkpoints now starts no earlier than the buffer's first hour, so no holdout candle is read. The
    500-hour reading was made under the old warm-up and stays as written.
  - The 2026-09-19 snapshot stores the whole holdout period.
  - Full account: audit §18.2.
- **Watch item — the calm market (drift flag "outcomes" in the weekly report since 2026-09-26).** The live
  market is calmer than in development (large moves in ~34% of hours vs ~47% on validation). The pipeline
  is ruled out. Descriptively, the model's stated probabilities have run a little above the observed rate in
  this calm market, but that gap is **not established** (its interval includes zero, below). It is judged
  **only** at the registered checkpoints and never tuned. Context from development data, none of which changes
  a rule:
  - **E026:** the model family was calibrated in calm markets historically, so a *persistent* live
    over-statement would be a genuine deviation.
  - **E027:** it over-states at night and under-states in the US session.
  - **E029:** its calibration naturally wanders in multi-week runs about three to four times a year, so a
    few weeks of apparent over-statement is not by itself a deviation.
  - **2026-10-05 weekly report (descriptive):** the market stays calm (large moves in 32% of live hours).
    Two inputs, `tr_mean_14_rel` and `trades_rel_168h`, now sit below the development 1st percentile in
    about 12% of live hours, so the model is partly working in calmer conditions than anything it was
    built on. On 328 graded hours it is still ahead of the free EWMA rule (Brier 0.1972 vs 0.2134).
    Recorded, never tuned on; read at the registered checkpoints.
  - **The 500-hour first look (2026-10-13, registered, no verdict):** all 500 hours were calm. The model
    stated 0.335 on average where large moves happened in 0.304 of hours. That is a **descriptive** gap of
    +0.031. Its 48h block-bootstrap interval is [−0.013, +0.070], computed afterwards by the Phase 2 diagnosis
    with the reading's own settings (`research/DIAGNOSIS_2026-10-15.md`); the registered reading reports the two
    means without an interval. The interval includes zero, so **no systematic over-statement is established**.
    Its ECE was 0.059, ordinary at that size (E024). It was still ahead of the free EWMA rule (Brier 0.1927 vs
    0.2091). This remains a watch item for the 2,000- and 5,000-hour readings.

## Emergency-only — when the user should act

| you receive | what it most likely means | what to do |
|---|---|---|
| healthchecks.io "DOWN" email, and it stays down > 3 hours | no successful run for hours | Look at GitHub → Actions. If runs fail with *permission denied*, roll back the database switch: copy the `DATABASE_URL` line from your local `.env` into the GitHub secret `DATABASE_URL`. Otherwise wait for the next session. |
| GitHub "run failed" emails for several hours in a row | a persistent failure (a source down, a secret, a code defect) | Nothing is lost while it fails; the hour simply isn't recorded. Leave it for the next session unless it lasts > 1 day. |
| an Anthropic "credit balance" or billing email | the AI calls will start failing | Top up the Anthropic account. The runs keep saving predictions meanwhile, marked "news unavailable". |
| a Supabase email about pausing or limits | the free project is at risk | Open the dashboard and follow its instructions (hourly writes should prevent pausing; storage was 34 MB of 500 MB on 2026-10-20). **There is no backup** (see "Unresolved operational risk"), so never delete or reset the project, and act the same day. |
| a healthchecks.io email saying "AI calls FAILED … authentication" | the Anthropic key is invalid or has expired (it expires 2027-01-31) | Renew it: `docs/ops/open_user_actions.md` item 8. The hours are still saved, without news scores or explanations. |
| a GitHub "Reporting snapshot" failed email | the private stats snapshot has not refreshed for over 3 hours | Nothing is lost and the live system is unaffected (the stats website would show older data). Leave it for the next session. |
| a GitHub email that scheduled workflows were disabled | 60 days without repository activity | Click "enable" in the Actions tab. Not expected before ≈ 2026-12-19 (60 days after the 2026-10-20 weekly-audit commit); any commit resets the clock. |

**Calendar** (the weekly audit reads it; anything due within four weeks is raised with the user):
- **2027-01-17**: renew the **Anthropic API key**, which **expires 2027-01-31** (the user, 2026-10-20). This is two
  weeks ahead. The steps are in `docs/ops/open_user_actions.md` item 8. An expired key does not stop the record: news
  and explanations fail, visibly marked, and the AI-failure alarm emails.
- **2027-09-20**: renew the GitHub token `supabase-dispatch` before it expires (`docs/ops/open_user_actions.md`
  item 3).

**Heartbeat dashboard:** the user looked at healthchecks.io on 2026-10-20 and saw no visible issue. That is a manual
look, not a proof. It does not show that every alarm email would be delivered in every failure. The last proofs of
delivery are the user's labelled tests of 2026-10-15 (main check) and 2026-10-16 (direction check).

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

- First run the integrity pre-check, `python -m agent.research.checkpoint_precheck` (since 2026-10-15; fail-closed
  since 2026-10-16). It covers the master plan's eight requirements, reads no outcome value and writes nothing.
  - **Exit 0** = READY. **Exit 3** = no failure, but the size is not reached. **Exit 1** = a mandatory item failed:
    repair first, and never run the checkpoint as though it were valid.
  - A check that cannot be completed counts as a FAIL.
  - Every commit on the checkpoint's code path since the last reading must have a written, evidenced review in
    `research/CHECKPOINT_PATH_REVIEWS.json`, or rule 3 FAILS. Review the diff before adding an entry.
  - Rule 8 lists the facts the reading's report must state.
- Then confirm that `research/monitoring/` holds no reading for 2,000 hours yet. The command skips
  anything already present, and on 2026-10-11 an empty stray file appeared under the 500-hour name.
- It reads **exactly the first 2,000** prospective graded hours in time order. Later hours belong to the
  5,000-hour reading.
- It refuses to run early and never rewrites a computed checkpoint (tested). It states whether every
  judged probability reproduces from its stored inputs (clarification 11).
- It gives **the E012 verdict**, calibration by bucket with intervals, the comparison with the free
  24h-EWMA rule, and weekday/weekend and hour-of-day blocks. The blocks are descriptive and are read
  against E027's development offsets.
- **No separate approval is needed** (the user's post-500h plan, 2026-10-14): run it at the first active session
  when the authoritative counter confirms 2,000, exactly as written. Never open the holdout.
- E024: a model as good as on validation passes every E012 part in about 98% of 2,000-hour stretches.
  A fail there means something.
- Commit the reading together with this file's and `status.json`'s move to the next checkpoint:
  `tests/test_status_docs.py` requires every earlier reading to exist exactly when the status names a
  later checkpoint.
- Afterwards a dated readiness assessment is added to the gate, again.

**Then 5,000 hours:** the E013 verdict (≈ spring 2027).

**The direction shadow track (E034, separate; `research/DIRECTION_TRACK.md` v1.1).** Collecting since the 15:00 UTC hour of 2026-10-15 (written 16:13 UTC by the dispatched run at f47e7bd: every step green, both live cross-checks matched).
- Readings at **1,000** eligible hours (≈ late November 2026, first look, no verdict), **3,000** (≈ late February
  2027, no verdict) and **6,500** (≈ late July 2027, the verdict). E033 sized them: no direction conclusion is
  possible by 2026-12-14.
- Command: `python -m agent.research.direction_checkpoint`. It prints only operational counts until a reading is
  due, then writes `research/monitoring/direction_checkpoint_<N>h.md/.json` once.
- **Blind (Amendment 1.1):** until each reading, look only at operational figures for this track (rows, statuses,
  coverage, errors, the prospective rule, integrity flags, graded/pending counts), never an outcome-based one.

## After the readiness audit, in order (the user's decisions, 2026-10-11)

1. The single-missed-hour alarm. **Done 2026-10-14** (alarms, above).
2. Then keeping GitHub's answers to the dispatch requests (trigger responses). **Done 2026-10-14**
   ("What happens automatically", item 6).
3. News cost and value, reviewed separately, with no change to the live weights or model. **Done 2026-10-15,
   read-only** (`research/NEWS_COST_VALUE_2026-10-15.md`): ≈ $7.66 per 30 days, 74% of the AI cost; it changes 5.5%
   of signals, mostly to HOLD; its value is unknown until the registered verdict (≈ 2027-02). Nothing changed.

All three are done (items 1 and 2 verified live 2026-10-14; item 3 read-only, 2026-10-15). The questions that
were waiting on the user were answered by the user's master plan (2026-10-14):
- **E031** (block-wise calibration) is not a candidate: H_c fails. **Answer:** one new move-size hypothesis may be
  registered after the diagnosis, if the diagnosis justifies it. The diagnosis (`research/DIAGNOSIS_2026-10-15.md`,
  row 5) names it: one shared slope plus four block intercepts, on development data only, registered first.
- **E032** (direction) finds the faint 1h P(UP) real, calibrated and year-stable, but one feature and economically
  negligible. **Answer:** yes, a prospective direction shadow track, isolated and registered before collection
  (master plan Phase 3).
- **The checkpoint's EWMA warm-up** must not read the holdout. **Done:** Amendment A1 (protocol 1.1).

- The registered **news first look**: **done 2026-10-14 (E030, `research/results/E030/`)**. It was blind until
  it ran, it used exactly the first 500 usable hours, and it gives no verdict, by registration.
  - 1h ρ +0.046 [−0.052, +0.151], 6h +0.001, 24h −0.096. Every interval includes zero.
  - That is not evidence of no effect: this size can only see |ρ| ≥ 0.125.
  - The verdict needs 3,140 usable hours (≈ 2027-02). Nothing changed.
- A properly registered study for the 2,000-hour milestone may be considered; that is the user's
  decision. The calm-market study has lapsed.

The holdout opens only on the user's explicit instruction. Before any E014/E023 run, the E000 backtest
runner's bypass of the holdout guard must be fixed first.
