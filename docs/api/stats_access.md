# Private stats access: how a future website may read the statistics

> **THIS IS A PRIVATE READ-ONLY STATISTICS INTERFACE. IT IS NOT THE FUTURE AUTOMATED-TRADING APPLICATION.**
> It lets one signed-in person look at how the analysis system is doing. It cannot change, trigger or
> influence anything in the system, and it has nothing to do with the NOT ACTIVE execution goal
> (`docs/FUTURE_EXECUTION_ARCHITECTURE.md`).

**Status:** the backend side is built and live since 2026-09-27. **No website exists yet**; building it
(in Lovable) is a separate, later step. This document is what that step must follow.

```
live hourly system (unchanged)
      |  completes
      v
authoritative database records ---- read-only ----> agent/reporting (the statistics, reporting contract v1)
                                                            |
                                          "Reporting snapshot" workflow, after each hourly run
                                                            v
                                  reporting_snapshot + reporting_runs   (two derived caches)
                                                            |
                                   SELECT only, signed-in viewer with the owner-set claim
                                                            v
                                            future Lovable stats website  ->  you
```

Nothing flows back up. The two caches are read by nothing in the system.

## 1. What the website may read, and nothing else

Two tables in the Supabase database, **read-only**:

| table | rows | content |
|---|---|---|
| `reporting_snapshot` | exactly one | `document`: the full reporting-contract document of kind `all`, meaning the latest run, direction-signal statistics, the shadow model's running calibration and breakdowns, system health and checkpoint progress (`docs/api/reporting_v1.md` §3–7). Also `generated_at`, `as_known_at` and `reporting_contract_version`. |
| `reporting_runs` | one per hourly run since go-live | `hour`, and `run`: that run's full view. This is the prediction, the confidence (labelled a heuristic), versions, run status, the explanation, the category scores, its outcomes for every registered horizon (graded / pending / overdue / unavailable) and the shadow move-size probability with its outcome. |

These are the reporting layer's own outputs, stored unchanged. **The website renders them; it never
recalculates a statistic, relabels a number, or computes a target of its own.** Every figure already
carries its sample size and evidence label, every quantity says whether it is a probability, and every
document carries `never_use_for` and `limitations`. The website must show them.

**It cannot read anything else.** That includes the predictions, outcomes and shadow tables, the error
log, the published backend state, the schema version, anything in other schemas, and any function. It
cannot write, update, delete, truncate or create anything, cannot trigger a prediction, scoring or any
job, and cannot run arbitrary SQL. Supabase's API offers only table reads and writes, and function
calls, to the roles the database allows; this database allows the website's role exactly two table
reads.

**No sealed-holdout data exists in either table:** the record starts 2026-09-19, and the publisher
refuses to publish any hour dated inside the holdout (2025-07-01 → 2026-08-19).

## 2. Who may read: authentication

Three conditions, all required:

1. **Signed in.** The website uses Supabase Auth. An anonymous request (holding only the public
   project key) acts as the `anon` role, which holds **no** privilege on these tables and is refused.
2. **Signed in as the viewer.** The signed-in user's token must carry
   **`app_metadata.reporting_viewer = true`**. Only the project owner can set `app_metadata`: a user can
   edit their own `user_metadata`, never `app_metadata`. So an account created by anyone else, even if
   sign-ups were left open, sees **zero rows**. Putting the flag in `user_metadata` does not work either,
   and a test proves it.
3. **Reading only.** The database grants `authenticated` SELECT on these two tables and nothing else,
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

## 3. How the website reads (for the Lovable build)

```js
await supabase.auth.signInWithPassword({ email, password })

// everything on the statistics page
const { data: snap } = await supabase.from('reporting_snapshot')
  .select('generated_at, as_known_at, reporting_contract_version, document').single()

// the run history, newest first, 24 at a time
const { data: page } = await supabase.from('reporting_runs')
  .select('hour, run').order('hour', { ascending: false }).range(0, 23)

// one hour in detail
const { data: one } = await supabase.from('reporting_runs')
  .select('hour, run').eq('hour', '2026-09-27T07:00:00+00:00').single()
```

Rules for the website:
- Refuse a `reporting_contract_version` it does not know.
- Always show how old the data is (`generated_at`). If it is more than about three hours old, say that
  the data may be stale.
- Show each figure's `sample` headline next to it.
- Never style a figure with `is_probability: false` as a probability.
- Keep the direction signal's evidence text next to the signal.

## 4. How new data arrives every hour

1. The hourly workflow runs exactly as before (Supabase's `pg_cron` starts it at :12; GitHub's slots are
   the backup). **It is unchanged, and it does not know the stats website exists.**
2. When a run of it **completes successfully**, GitHub starts the separate **"Reporting snapshot"**
   workflow (`.github/workflows/reporting.yml`). This is an event trigger, not a scheduler: it cannot
   run before, inside or instead of the hourly job.
3. That workflow runs one command, `python -m agent.reporting.publish`. It reads the record through the
   reporting layer's read-only connection, computes with the reporting layer's own functions, and
   replaces the snapshot row and the run rows whose content changed.
4. Data is usually fresh a few minutes after each hour's run. If a publish fails, the previous snapshot
   stays, visibly older by its own `generated_at`. The workflow fails loudly (a GitHub email) only once
   the snapshot is more than three hours old.

The workflow holds only the database secret, which connects as the least-privilege role
`bitcoin_agent`. It holds no AI key and no heartbeat URL, so it cannot call a model and cannot fake or
silence the alarm.

## 5. The security boundary, and how each part is proven

| guarantee | enforced by | proven by |
|---|---|---|
| Anonymous requests read nothing | no privilege for `anon` on any table | `tests/integration/test_stats_access.py` (real Postgres, acting as `anon`); security check; mutation |
| Only the owner-flagged account reads, and only these two tables | SELECT grant to `authenticated` on two tables + one claim policy each | integration: the viewer reads; five non-viewer tokens, including a self-set `user_metadata` flag, see 0 rows |
| No write, delete, truncate or create; no access to the record | no other privilege; RLS on every table; no CREATE on `public` | integration: 17 refused statements as the viewer; a read-only check of the live `public` schema |
| The surface cannot widen quietly | `python -m agent.database.security` (watchdog): exactly these tables, `authenticated` only, SELECT only, exactly the claim condition, no view, no callable function | unit tests (12 widening variants), integration (5 live-style widenings reported), mutations |
| The publisher writes only the two caches | its SQL; the job role's grants (`docs/ops/least_privilege_role.sql`, checked by the watchdog's role check) | `tests/test_reporting_separation.py`; integration: the job role publishes and is refused DELETE, TRUNCATE, DROP, RLS-off and record writes; mutation |
| The website cannot reach the prediction system | nothing in `agent/`, `run.py`, `tools/` or any other workflow imports or runs the reporting layer; the caches are read by nothing | `tests/test_reporting_separation.py`; mutations |
| No second scheduler; the hourly workflow untouched | the reporting workflow has no schedule, only `workflow_run` after "Hourly Bitcoin analysis" + manual dispatch; it runs only the publisher | `tests/test_reporting_separation.py`; mutations (schedule added, prediction job added, AI key added) |
| No holdout data | the record starts 2026-09-19; the publisher refuses holdout-dated hours | `tests/test_reporting_publish.py`; mutation |
| No figure computed differently for the website | the publisher stores `views.document(...)` / `views.all_runs(...)` unchanged | `tests/test_reporting_publish.py` (equality with the reporting layer) |

## 6. What this changed, and what it did not

**Changed:**
- Two new tables and their read policy (`agent/reporting/schema.sql`, applied live with
  `python -m agent.migrate` on 2026-09-27).
- One new workflow, and the publisher.
- The job role's rights on the two caches (added to the proven file).
- The security check's allowlist, from empty to this one exact surface.

**Not changed:** the hourly workflow, the prediction, scoring, thresholds, features, the shadow model,
the checkpoint code and rules, the sealed holdout, the watchdog and heartbeat, the schema version (4),
and every other table's lockdown.

## 7. Never

- Never expose anything else to make the website easier: no other table, no view, no function, no `anon` access, no second policy.
- Never give the website a secret: no `service_role` key, no database URL, no role password.
- Never let the website write, or let anything in the system read the two caches.
- Never use what the website shows to tune, select or change anything (`never_use_for` in every document).
- This is a private statistics page. **It is not the trading application**, and it must never become the place that one is built.
