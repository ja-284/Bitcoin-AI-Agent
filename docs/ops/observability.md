# Observability review — can every failure be told apart from a normal run?

Reviewed 2026-09-22 by reading every failure handler in the live path (`agent/`, excluding
`agent/research/`) and checking each against one standard:

> **A failure must never be indistinguishable from a real observation.**
> "No data", "could not be computed", "deliberately excluded" and "genuinely neutral" are four
> different things, and collapsing them is how a broken system comes to look like a working one.

## Every failure path, and what it leaves behind

| what fails | what happens | how you can tell |
|---|---|---|
| Binance responds with a bad shape | `KlineSchemaError`, no retry on a malformed body | job fails loudly |
| Binance unreachable | one bounded retry, then fall through to CoinGecko | `price_source`, `run_meta.price_data` |
| both price sources fail | the run **aborts** — price is the one input nothing can proceed without | job fails; next hour's self-check also fails |
| CoinGecko used instead | prices stored with `price_is_synthetic = true`; volume unavailable, not guessed | `price_is_estimated` in the contract; excluded from parity |
| impossible candle (high < low, etc.) | raises; nothing is repaired | job fails loudly |
| a gap in the candle history | indicators run on the longest unbroken run ending at the reference candle; anything whose warm-up does not fit becomes **unavailable** | `run_meta.price_data`, category weight 0, `window_hours` vs `consecutive_hours` |
| data older than the staleness rule | raises rather than being scored | job fails loudly |
| **one news feed down** | the other feeds are still collected and scored | `run_meta.news.sources_failed`; **contract `news.sources_failed` / `sources_used` / `sources_total`; weekly report §1** |
| all news feeds down | zero items → news category **weight 0** | `news.available = false`, `completeness_score` drops |
| the news AI call fails or is truncated | news left out entirely, never guessed at | `run_meta.news_error` + `news_error_type`, `ai_model_news` NULL, weight 0; **the AI-failure alarm since 2026-10-17** (below the table, and `docs/ops/STATUS.md` → Alarms) |
| the explanation fails or is truncated | the analysis is saved without it; the decision never depended on it | `run_meta.explanation_error`, `explanation_status`; **the AI-failure alarm since 2026-10-17** |
| an AI answer arrives without token figures | recorded as `usage_unavailable`, **never as zero**; the run's cost is left out of the average and counted | `run_meta.ai_usage`; weekly report §1 ("without figures") (added 2026-09-23) |
| a database write fails | the run fails; the next hour recomputes from scratch | job fails; writes are idempotent so a retry cannot duplicate |
| the same hour runs twice | early exit **before** the AI calls | no duplicate row (`ON CONFLICT DO NOTHING`, proven on real Postgres) |
| the research shadow step fails | recorded in `shadow_run_errors`; the hourly job stays green because the live record is unaffected | weekly report §3; watchdog alarms only if it persists (> 2 in 6h) |
| the direction shadow step or its grading fails (E034, since 2026-10-15) | recorded in `shadow_direction_errors`; exit 0, so the hourly job stays green; exit 1 only if even the recording fails. Its steps come after the publish step, so neither case can skip the publish or cost a live hour | **its own alert since 2026-10-16** (`agent/direction_shadow/health.py`, a separate healthchecks.io check): a lost hour is recorded once in `shadow_direction_health` and alerts once per incident; a late but recoverable hour does not alert; no runs at all trip the check's silence alarm. Also the weekly report's operational line |
| an outcome candle does not exist | status `unavailable`; price and return stay NULL | `prediction_outcomes.status`, never a fabricated price |
| an hourly run is skipped | the hour stays missing (never backfilled). The next run's self-check fails only if the newest prediction is more than 2 h old, so a **single** missed hour followed by a good run does **not** fail it (corrected 2026-10-08; this row used to say it did) | a failed run: GitHub emails it, and it is recorded as a stats incident. No run at all: the heartbeat alarms only if no successful run, including an early-exit backup run, pings for 1 h 30 min. On 2026-10-07 the 14:00 hour was lost with pings 87 min apart, so most likely no alarm went out. After the fact the hour shows in the weekly report, `backend_state` health and the stats incident history. **Since 2026-10-14 (operational change 1):** the run that saves the first hour after a gap sends the heartbeat check a failure signal whose body names the missing hour(s) (`python -m agent.healthcheck --new-gap-since`, step *Heartbeat missed-hour signal*). Each gap is reported once, and a late run is never reported. The success ping seconds later turns the check green again, so the next silence still alarms on its own. healthchecks.io sends the "down" email even when the check is already "up" again: its alert sender does not drop superseded flips (read in its source, 2026-10-14). The delivery chain can be proven without a real missed hour by the manual *Alert delivery test* workflow: one report labelled as a test (2026-10-14). |
| a table becomes reachable through Supabase's public API (RLS switched off by hand, a privilege re-granted, or a new table made outside the schema files, which Supabase's defaults expose at once) | nothing in the hourly job changes — this is invisible from the record itself | `python -m agent.database.security` in the watchdog, every 3 hours: the job fails and GitHub emails you (added 2026-09-23) |
| a **view or function** is added to `public`, or the standing default grant to the public API returns | nothing in the hourly job changes | the same security check, extended 2026-09-23 evening: views readable by the API (they ignore RLS), functions callable at `/rest/v1/rpc`, default grants for new objects — each fails the watchdog |
| the database is on an older schema than the code (a restore, or a rebuild from old files) | the run stops before writing anything | `assert_schema_current`; the job fails loudly naming both versions |
| **GitHub itself stops running anything** | **nothing happens, and nothing complains** | **NOT DETECTABLE — see below** |

## The AI-failure alarm (since 2026-10-17)

Found during the Anthropic key rotation: a failed news or explanation call degrades the hour visibly in the record,
but **no alarm** fired. The job stays green and the heartbeat keeps pinging. So an expired key would have left every
hour without news or an explanation, seen only in the weekly report.

Since 2026-10-17 (the user's approval; only this change) it works like this:
- **Every run checks.** The step *Heartbeat AI-failure signal* runs `python -m agent.healthcheck --ai-failure-body-file`
  on every run, backup slots included. It looks at the newest saved hour.
- **Report.** If that hour's news step or explanation failed, it sends the heartbeat check `/fail`. The body names the
  error *types* only, never the error text, the key or a URL, with a key hint for authentication or permission errors.
- **One email per incident.** It sets `AI_FAILING`, which holds back the success ping, so healthchecks.io emails
  "down" once and the check stays down. The first run that saves an hour with working AI calls pings "up" again.
- **It never fails a job.** Like every heartbeat step it is `continue-on-error`. If the check itself cannot run, the
  ping goes out as before.
- **Proof so far:**
  - Tested in `tests/test_ai_failure_signal.py`, with five mutation guards (area *ai-alarm*).
  - Its delivery path is the missed-hour signal's `/fail`, proven by the user on 2026-10-15.
  - The clean case runs every hour. A real failure has not been seen live.
- **The trade-off:** while the check is down for this reason, a GitHub outage raises no second email. The check is
  already red.

## Which alarm paths fail safe (reviewed 2026-10-20, post-audit plan Phase 2A)

A green GitHub step does not prove that healthchecks.io received anything. Every heartbeat step is
`continue-on-error`, so a failed `curl` still shows green. The question is therefore what happens when a delivery is
lost. Read from `.github/workflows/hourly.yml` and `agent/healthcheck.py`; nothing was triggered to test it.

| signal | if its delivery is lost | fails safe? |
|---|---|---|
| the success ping | the check hears silence and emails "down" after 1 h 30 min | **yes** |
| `/fail` from a failed run | the success ping is skipped as well, because it runs only when every earlier step succeeded (GitHub's implicit `success()`), so the silence alarm follows | **yes**, about 90 min later |
| the missed-hour `/fail` | the success ping right after it still arrives, so no email goes out | **no**. The hour stays in the record (weekly report, `backend_state`, stats incident history), and a single missed hour needs no action |
| the AI-failure `/fail` | `AI_FAILING` is written before the `/fail` is sent, so the ping is held back anyway and the silence alarm follows while the failure lasts | **yes**, while it lasts. A failure that clears within the hour and loses its `/fail` leaves only the record. If the check itself crashes, that run pings as before, and the next run looks again |
| the direction track's own check | the same design on its own check | the same as above |
| the watchdog | it has no heartbeat. If GitHub stops scheduling it, nothing alarms | **no**. Seen only in the weekly audit's run count. GitHub emails before it disables schedules after 60 days without a commit, and weekly audit commits reset that clock |

**The one material blind spot is the external chain itself:** the healthchecks.io account, its two checks and their
email integration.
- If any of these broke, every heartbeat-based alarm would go quiet together, and nothing in the repository could
  tell. A ping to a deleted check also shows green on GitHub.
- It was last proven end to end on 2026-10-15 (main check) and 2026-10-16 (direction check), by the user's
  labelled delivery tests.
- GitHub's own failure emails and the record are unaffected.

*2026-10-20:* the user looked at the dashboard and saw no visible issue. That is a manual look at one moment, not a
proof that every alarm email would be delivered in every failure.

**Smallest mitigation, proposed and not adopted:** at each weekly audit the user spends a minute on the
healthchecks.io dashboard and checks three things: both checks "up", the last ping within the hour, and recent
notifications marked delivered.
- It needs no code, no service and no alert change.
- Anything heavier would change production alert behaviour, so it needs the user's approval first. Examples:
  recording each `curl` result in the run, failing the job on an undelivered ping, or a second alert service.

## The one real gap

Every alarm above lives inside GitHub. If GitHub stops running the workflow — which it already
did in the first days, firing 2 of 8 scheduled slots — then no job runs, so no job fails, so
nothing is reported. **Silence is indistinguishable from success.**

**CLOSED 2026-09-25.** The heartbeat is live and verified: the user's healthchecks.io check (1 h period,
30 min grace) received the 19:13 UTC ping, and a failed run sends `/fail` at once. An alarm that does not
depend on GitHub now exists. *(As written before that:)* The fix is written and inert: the hourly
workflow's last step pings `$HEARTBEAT_URL` if that
secret exists, placed after every other step so a ping means the whole hour genuinely succeeded.
It needs a free healthchecks.io account and one repository secret — a user action, five minutes,
written up in [`open_user_actions.md`](open_user_actions.md).

**Measured 2026-09-23, and it matters:** the watchdog itself is scheduled by GitHub, and GitHub ran
**3 of its 8 three-hourly slots** in the preceding day (05:04, 12:02, 17:25 UTC — the 15:33 slot ran
1 h 52 min late). Its checks all passed when it ran, including the first public-API security check
from GitHub's side, but "every 3 hours" is really "every 5–7 hours" on this repository. The hourly
analysis is unaffected (it is dispatched from Supabase at :12). An option for the user, not taken
without asking because it adds a standing job to Supabase: dispatch the watchdog from the same
Supabase `pg_cron` trigger. The heartbeat remains the only alarm that does not depend on GitHub.

Until then the mitigations are: the Supabase `pg_cron` trigger (independent of GitHub's own
scheduler), the self-check, the 3-hourly watchdog, and the weekly report's missing-hours list.
All of them still require GitHub to run *something*.

## Two things found during this review

**1. A partial news failure was invisible.** A feed going down is the quiet case: unlike a total
outage it still produces a number, and nothing downstream distinguished "three feeds, all
healthy" from "one feed, two down". The fact was recorded in `run_meta.news.sources_failed` but
never surfaced or tested. It has never happened in 69 live runs, which is exactly why it needed
a test rather than a watch. Now: shown in the backend contract (`sources_used` / `sources_total`),
counted in the weekly report, and covered by four tests.

**2. A decision deliberately NOT taken.** It would be defensible to reduce the news category's
weight in proportion to how many sources answered — `completeness_score` claims full
completeness today even if two of three feeds were down. It is not done, for three reasons: it
changes live scoring, which is the thing currently under test and would need a new version and a
re-run of the baseline; the effect has never once occurred in production; and the honesty goal is
met by making the shortfall visible instead. If feeds start failing regularly, this is the first
thing to revisit, and it is written here so that revisit starts from a decision rather than an
oversight.

## Data quality, measured rather than assumed (2026-09-22)

Across the 69 live runs with a news block: **95.2** items fetched per hour on average, **34.7**
used. Every exclusion is one of the intended rules — **59.8** outside the 24-hour window, **0.4**
published after the information cutoff, **0.2** duplicates across feeds, **0.0** undated. Nothing
is dropped for an unexplained reason, and nothing undated is ever admitted.

`used` has since risen to about 50 per hour, which is what overran the news scorer's old
2,048-token limit on 2026-09-21. The limit is now 16,384, so there is roughly a 5× margin.

## What is deliberately *not* logged

Secrets, in any form — checked by scanning both tracked files and every stored row. Raw exception
text never reaches the outward-facing contract either: it stays in the database, where it is
needed for diagnosis and where it identified the 2026-09-21 truncation, and the contract reports
a plain sentence plus the exception type.
