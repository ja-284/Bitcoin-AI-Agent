# Private stats access: how the statistics website may read the statistics

> **THIS IS A PRIVATE READ-ONLY STATISTICS INTERFACE. IT IS NOT THE FUTURE AUTOMATED-TRADING APPLICATION.**
> A small side project that lets one signed-in person see how the analysis system is doing. It cannot
> change, trigger or influence anything in the system, and it has nothing to do with the NOT ACTIVE
> execution goal (`docs/FUTURE_EXECUTION_ARCHITECTURE.md`). The main system always has priority.

**Status:**
- The backend side is built and live since 2026-09-27.
- Incident history and the predicted-vs-actual, trends and overview fields were added 2026-10-05.
- **No website exists yet.** Building it in Lovable is a separate project.
- **The frontend handoff is `docs/api/stats_website_handoff.md`.** This document is the security boundary
  behind it.

```
live hourly system (unchanged)          watchdog (unchanged)
      |  completes                            |  completes
      v                                       v
authoritative production records ---- read-only ----> agent/reporting (computes the statistics)
                                                            |
                         "Reporting snapshot" workflow (a separate workflow, started by those completions)
                                                            v
              reporting_snapshot + reporting_runs + reporting_incidents   (the reporting tables)
                                                            |
                                   SELECT only, signed-in viewer with the owner-set claim
                                                            v
                                            Lovable stats website  ->  you
```

Nothing flows back up. Nothing in the prediction system reads the reporting tables.

## 0. Who reads and who writes what (the precise model)

| data | the reporting layer's computing side (`source.py`, `views.py`) | the two writers (`publish.py`, `incidents.py`) | the website |
|---|---|---|---|
| **production records** (predictions, outcomes, shadow rows, shadow errors, backend state, schema version) | **read only**, on a connection the database server itself holds READ ONLY (writes are refused by Postgres, not just avoided) | read only, through that same read-only path | **no access at all** |
| **reporting tables** (`reporting_snapshot`, `reporting_runs`, `reporting_incidents`) | reads `reporting_incidents` back, read-only, to show it | the **only** code that writes them: the publisher replaces the snapshot and changed run rows; the recorder appends incidents (append-only: a trigger refuses any edit or delete, even by the owner) | **SELECT only** |

"The reporting layer is read-only" means exactly this: it never writes a production record, and its
computations run on a read-only connection. Its only writes are the publisher's and the recorder's, into
the three reporting tables, as the least-privilege role. That role's rights there are listed in
`docs/ops/least_privilege_role.sql` and checked by the watchdog.

## 1. What the website may read, and nothing else

Three tables in the Supabase database, **read-only**:

| table | rows | content |
|---|---|---|
| `reporting_snapshot` | exactly one | `document`: the full reporting-contract document of kind `all`. It holds the overview, the latest and latest-matured run, direction-signal statistics, the shadow model's running calibration and breakdowns, trends by week, system health with the full incident history, and checkpoint progress. Also `generated_at`, `as_known_at` and `reporting_contract_version`. |
| `reporting_runs` | one per hourly run since go-live | `hour`, and `run`: that run's full view. This is the prediction, the confidence (labelled a heuristic), versions, run status, the explanation, the category scores, its outcomes for every registered horizon (graded / pending / overdue / unavailable, with predicted-vs-actual once graded) and the shadow move-size probability with its outcome. |
| `reporting_incidents` | one per recorded incident, append-only | failed hourly or watchdog runs, failed or long-stale stats publishes: when, what, and a link to the public GitHub run page |

These are the reporting layer's own outputs, stored unchanged. **The website renders them; it never
recalculates a statistic, relabels a number, or computes a target of its own.** Every figure already
carries its sample size and evidence label, every quantity says whether it is a probability, and every
document carries `never_use_for` and `limitations`. The website must show them.

**It cannot read anything else.** That includes the predictions, outcomes and shadow tables, the error
log, the published backend state, the schema version, anything in other schemas, and any function. It
cannot write, update, delete, truncate or create anything, cannot trigger a prediction, scoring or any
job, and cannot run arbitrary SQL. Supabase's API offers only table reads and writes, and function
calls, to the roles the database allows; this database allows the website's role exactly three table
reads.

**No sealed-holdout data exists in any of them:** the record starts 2026-09-19, and the publisher refuses
to publish any hour dated inside the holdout (2025-07-01 → 2026-08-19).

## 2. Who may read: authentication

Three conditions, all required:

1. **Signed in.** The website uses Supabase Auth. An anonymous request (holding only the public
   project key) acts as the `anon` role, which holds **no** privilege on these tables and is refused.
2. **Signed in as the viewer.** The signed-in user's token must carry
   **`app_metadata.reporting_viewer = true`**. Only the project owner can set `app_metadata`: a user can
   edit their own `user_metadata`, never `app_metadata`. So an account created by anyone else, even if
   sign-ups were left open, sees **zero rows**. Putting the flag in `user_metadata` does not work either,
   and a test proves it.
3. **Reading only.** The database grants `authenticated` SELECT on these three tables and nothing else,
   and each table has one policy: `FOR SELECT TO authenticated USING ((auth.jwt() -> 'app_metadata' ->>
   'reporting_viewer') = 'true')`.

What the website's code holds: the Supabase **project URL** and its **publishable (anon) key**. Both
are designed to be public, and with this setup they reveal nothing on their own. **Never** put the
`service_role` key, the database URL, or the `bitcoin_agent` password into the website or into Lovable.

### The one-time setup, when the website is being built (the owner's steps, not now)

1. Supabase → Authentication → Users → **Add user**: your email and a strong password.
2. Supabase → Authentication → sign-in settings → **turn off "Allow new users to sign up"**. This is
   defence in depth: new accounts would see nothing anyway.
3. Supabase → SQL Editor, run once with your own email:

   ```sql
   update auth.users
      set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb) || '{"reporting_viewer": true}'::jsonb
    where email = 'YOUR-EMAIL-HERE';
   ```

   Then sign out and in again: a token carries the claims it was issued with.
4. In Lovable, connect the Supabase project (URL + publishable key only).

**To revoke:** remove the flag (`raw_app_meta_data - 'reporting_viewer'`), or delete the user. It takes
effect when the current token expires, at most the token lifetime (one hour by default).

## 3. How the website reads

See `docs/api/stats_website_handoff.md` for the reads, paging, page map, freshness rules, error states and
labelling rules.

## 4. How new data arrives, and how failures stay visible

1. The hourly workflow and the watchdog run exactly as before. **Neither is changed, and neither knows the
   stats website exists.**
2. When a run of either **completes**, GitHub starts the separate **"Reporting snapshot"** workflow
   (`.github/workflows/reporting.yml`). This is an event trigger, not a scheduler: it cannot run before,
   inside or instead of them, and it starts no analysis, AI call, market-data fetch or scoring.
3. **If the run failed** (failure, timeout, startup failure), the workflow's first job records it as an
   incident, using `python -m agent.reporting.incidents record-workflow-run`.
   - GitHub's event fields reach it only as environment variables, and each is validated strictly. Only the
     two known workflows and failure conclusions are accepted, ids must be numeric, the time must carry a
     timezone, and the link must be this repository's run page. Nothing free-form is stored.
   - This job has its own concurrency group per failed run, so later runs cannot cancel it.
4. Then, after a success **or** a failure, `python -m agent.reporting.publish` refreshes the snapshot and the
   changed run rows:
   - it reads through the read-only connection and computes with the reporting layer's own functions;
   - a failure is therefore *reflected* (its incident, its missing or stale hour), never hidden behind the
     last success;
   - cancelled and skipped runs (superseded backup slots) trigger nothing.
5. The publisher also records its own problems:
   - a failed publish (when the database can still be reached);
   - a refresh gap of more than 3 hours (`stats_snapshot_was_stale`, recorded when publishing resumes).

   The workflow fails loudly (a GitHub email) only once the snapshot is more than 3 hours old.

**What is captured as an incident, and what is not:**

| captured | how |
|---|---|
| a failed hourly run, even if a later backup run filled its hour | recorded from GitHub's event (since 2026-10-05; the 16 failed runs of 2026-09-21/22 backfilled from GitHub's run history, source `github_api_backfill`) |
| a failed watchdog run | recorded from GitHub's event (none has ever failed) |
| a failed stats publish; a stats refresh gap of more than 3 h | recorded by the publisher |
| a missing hour; a run with news unavailable, fallback data, no explanation or a missing category; a shadow error; an hour without a shadow row | derived from the record itself, so permanent by construction |
| **not captured:** a heartbeat alarm (it lives on healthchecks.io); a reporting-workflow run that failed before writing anything (its symptom, a stale snapshot, is recorded when publishing resumes); anything while the database itself is unreachable | stated in every document (`health.incidents.capture`), so silence is not read as "nothing happened" |

The workflow holds only the database secret, which connects as the least-privilege role `bitcoin_agent`.
It holds no AI key and no heartbeat URL, so it cannot call a model and cannot fake or silence an alarm.

## 5. The security boundary, and how each part is proven

| guarantee | enforced by | proven by |
|---|---|---|
| Anonymous requests read nothing | no privilege for `anon` on any table | `tests/integration/test_stats_access.py` (real Postgres, acting as `anon`); security check; mutation |
| Only the owner-flagged account reads, and only these three tables | SELECT grant to `authenticated` on three tables + one claim policy each | integration: the viewer reads; five non-viewer tokens, including a self-set `user_metadata` flag, see 0 rows |
| No write, delete, truncate or create; no access to the record | no other privilege; RLS on every table; no CREATE on `public` | integration: every write, create and record-read attempt as the viewer refused; a read-only check of the live `public` schema |
| An incident can never be edited or erased | append-only trigger, applied to every role including the owner; the job role holds INSERT only | integration (UPDATE and DELETE refused even as the owner); static test; mutations |
| The surface cannot widen quietly | `python -m agent.database.security` (watchdog): exactly these tables, `authenticated` only, SELECT only, exactly the claim condition, no view, no callable function | unit tests (12 widening variants), integration (5 live-style widenings reported), mutations |
| The writers write only the reporting tables | their SQL; the job role's grants (checked by the watchdog's role check) | `tests/test_reporting_separation.py`; integration: the job role publishes and records, and is refused DELETE, TRUNCATE, DROP, RLS-off, incident edits and record writes; mutations |
| Recorded events are trustworthy | strict validation of every event field; event data never in a shell line | `tests/test_reporting_incidents.py` (12 hostile inputs refused); separation test; mutations |
| The website and reporting cannot reach the prediction system | nothing in `agent/` (outside the reporting package), `run.py`, `tools/` or any other workflow imports or runs the reporting layer or names its tables; separate concurrency groups | `tests/test_reporting_separation.py`; mutations |
| No second scheduler; the hourly workflow and watchdog untouched | the reporting workflow has no schedule, only `workflow_run` after "Hourly Bitcoin analysis" / "Watchdog" + manual dispatch; it runs only its two commands | `tests/test_reporting_separation.py`; mutations (schedule, prediction job, AI key, shell-line event data, success-only publishing) |
| No holdout data | the record starts 2026-09-19; the publisher refuses holdout-dated hours | `tests/test_reporting_publish.py`; mutation |
| No figure computed differently for the website | the publisher stores `views.document(...)` / `views.all_runs(...)` unchanged; the acted-hour comparison is checked equal to the weekly report's | `tests/test_reporting_publish.py`, `tests/test_reporting.py` |
| No future outcome changes a past view | every view is computed "as known at" its moment, incidents included | `tests/test_reporting.py`; mutations |

## 6. What this changed, and what it did not

**Changed:**
- Three reporting tables and their read policy (`agent/reporting/schema.sql`, applied live with
  `python -m agent.migrate`: two on 2026-09-27, the incident table on 2026-10-05).
- One reporting workflow, the publisher and the incident recorder.
- The job role's rights on the reporting tables, in the proven file.
- The security check's allowlist, from empty to this one exact surface.

**Not changed:**
- The hourly workflow, the watchdog, the heartbeat.
- The prediction, scoring, thresholds and features.
- The shadow model.
- The checkpoint code and rules, LIVE_EVALUATION.md, and the target definitions.
- The sealed holdout.
- The schema version (4).
- Every other table's lockdown.

## 7. Never

- Never expose anything else to make the website easier: no other table, no view, no function, no `anon` access, no second policy.
- Never give the website a secret: no `service_role` key, no database URL, no role password.
- Never let the website write, or let anything in the prediction system read the reporting tables.
- Never use what the website shows to tune, select or change anything (`never_use_for` in every document).
- This is a private statistics page. **It is not the trading application**, and it must never become the place that one is built.
