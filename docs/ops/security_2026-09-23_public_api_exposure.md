# Security finding 2026-09-23 — every table was reachable through Supabase's public API

**Status: closed on the live database and in the repository, 2026-09-23 ~13:45 UTC.**
Verified by behaviour, detected continuously from now on.

## What was reported

Supabase's security advisor warned that a table was publicly accessible because Row Level
Security (RLS) was disabled. The instruction was to investigate before touching anything, and
not to make the warning go away with a broad policy.

## What was actually true — worse than the warning

It was not one table. It was **all six** tables in the `public` schema:
`predictions`, `prediction_outcomes`, `shadow_move_size`, `shadow_run_errors`, `schema_meta`,
`backend_state`.

| | state found |
|---|---|
| Row Level Security | **off** on every table |
| `anon` role | **SELECT, INSERT, UPDATE, DELETE, TRUNCATE** on every table |
| `authenticated` role | the same |
| policies | none |
| why | Supabase's default privileges grant those roles full access to every new table in `public`; nothing here ever took it away. Yesterday's `backend_state` got it the moment it was created. |

`anon` is the role Supabase's REST and GraphQL APIs act as for **anyone holding the project's anon
key**. That key is designed to be public — it is embedded in every browser app built on the
project — and RLS is what is supposed to make that safe. Here there was nothing behind it.

## What that exposure allowed

For anyone who had the anon key and the project URL:

- **read everything** — every prediction, outcome, shadow probability and error;
- **insert fake rows** into the research record. The worst case: pre-insert a prediction for a
  *future* hour. The real hourly run would then hit `ON CONFLICT DO NOTHING` and silently skip
  that hour — and the append-only triggers, built to protect the record, would then protect the
  forgery from deletion;
- **rewrite `schema_meta`**, which would make the live job's schema guard refuse to run every hour;
- **rewrite `backend_state`**, which a future frontend would display as the backend's word.

Blocked even then: UPDATE and DELETE on the four record tables (the append-only triggers), and
TRUNCATE through the API (PostgREST has no TRUNCATE; its `safeupdate` extension also refuses an
unfiltered UPDATE or DELETE).

## How exposed it was in practice

**Latent, not demonstrated.** No frontend exists, so the anon key is not published anywhere
known; it is visible in the Supabase dashboard. A scan of the repository for key-shaped strings
found none. But the anon key is not a secret by design, and the exposure would have become
immediate the day any frontend shipped.

## Was anything touched? — the data says no

| check | result |
|---|---|
| predictions | 91 rows for 91 distinct hours; **0** dated in the future |
| commit stamps | every stamp is a commit in this repository's history |
| unstamped rows | all 48 predate stamping (2026-09-19 09:00 → 2026-09-21 17:00); **0** after it began |
| timing | every row's `created_at` follows its `fetched_at` within 10 minutes |
| outcomes | **0** orphaned; **0** graded before their target candle closed |
| shadow rows | all `move_size_1h_v1`, none future-dated, every commit known |
| `schema_meta` | `3`, as the backend wrote it |
| `backend_state` | only the one row written by the backend on 2026-09-22 20:10 UTC |

**What the data cannot show is whether anyone read it** — reads leave no trace in tables. Only
Supabase's API logs can answer that: *Supabase dashboard → Logs → API Gateway*, filtered to
requests made with the anon key. That check needs the dashboard, so it is the user's
(`docs/ops/open_user_actions.md`).

## The fix — two independent layers, in the repository and live

Each schema file now locks down the tables it creates, so a database rebuilt from the repository
gets the same protection:

1. **RLS enabled with no policies** — the API roles see no rows and can write none;
2. **the API roles' table and sequence privileges revoked** — so even a careless future policy
   grants nothing on its own.

The backend is unaffected: it connects as the tables' owner, `postgres`, which bypasses RLS.
The SQL is guarded so it still runs on a plain Postgres without the Supabase roles.

Recorded as **schema version 4**, so a database with the lockdown and one without can never carry
the same stamp — and the hourly job now refuses to write to a database older than 4. The
migration was applied database-first, then code, with no moment in which they disagreed (which
needed the schema guard to accept a database *ahead* of the code — see `CHANGELOG.md`).

## How it was proven

- **Behaviour, not flags:** acting as `anon` and as `authenticated`, **48 of 48** probes (six
  tables × read/insert/update/delete × two roles) were refused on the live database. As
  `postgres`, every table was still readable and a real write succeeded (then rolled back).
- **Each layer on its own**, against real Postgres in a scratch schema: re-grant SELECT and RLS
  still hides every row; switch RLS off with the grant in place and the row appears (so the test
  measures RLS, not something else); switch RLS off and the revoke still refuses a write.
- **Static:** every `CREATE TABLE` in every schema file must be covered by that file's lockdown,
  and the checker is shown to fail when a table, a revoke or the RLS line is removed.
- **Continuously:** `python -m agent.database.security` checks the live posture of every table in
  `public`, and the watchdog runs it every three hours. It is a detector, never a fixer.

## What was deliberately NOT done

- **No read access for a frontend.** None exists. When one is built, opening `backend_state`
  read-only is a one-table, one-policy, reviewable change (`docs/api/contract_v1.md`).
- **Supabase's project-wide default privileges left alone.** Changing them would alter behaviour
  for tables the user may later create for a frontend; the per-table rule plus the detector covers
  the same risk without that.
- **`service_role` left alone.** It is the secret-key role, bypasses RLS by design, is used by
  nothing here, and is not what the advisor flagged.
- **No broad "allow all" policy, no data removed, no protection weakened.**

## A correction to my own earlier work

The security audit of 2026-09-21 (`docs/ops/security.md`) and the readiness gate that relied on it
scored Security as PARTIAL, with the least-privilege database role as the only gap. **That was
wrong.** The audit checked secrets, workflow permissions, logs and the trading boundary, but never
asked what the database exposes to Supabase's own public API — and a critical exposure was there
the whole time. Security should have been **FAIL** until today. The gate is corrected, and the
original text is left in place so the sequence stays honest.

## Remaining, and who owns it

- **Check the API logs for anon-key requests** — user (dashboard only).
- **The advisor may now show "RLS enabled, no policy"** on each table. That is informational and
  is the intended state: deny-all until a policy is deliberately added.
- **The hourly shadow step re-applies its schema file every run**, so it re-runs the lockdown DDL
  hourly. It works (the job connects as the owner) but is unnecessary, and it blocks a
  least-privilege role. Scheduled as the next controlled change.
