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

**Latent, not demonstrated.** Using the exposure required two things together: the project's
API hostname and its anon key. **This project never published either** — checked, not assumed:
no Supabase hostname and no JWT-shaped key appears in any tracked file, and no commit in the
repository's entire history ever added or removed one (the repository is public, so history
matters as much as the current tree). No frontend exists to have leaked them. Both are visible in
the Supabase dashboard, which only the account owner can reach.

That is why this is "latent" and not "nothing": the anon key is **not a secret by design**, and
the exposure would have become immediate the day any frontend shipped — at which point both the
hostname and the key are in every visitor's browser.

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
(`docs/ops/open_user_actions.md`). **It has a deadline:** the Free plan keeps API logs for 1 day
(supabase.com/pricing, read 2026-09-23), so the logs can only ever cover about the last day of the
exposure, and from ~13:45 UTC on 2026-09-24 none of it. The days before that are UNKNOWN
permanently, and are recorded as such rather than as "not read".

**Checked 2026-09-23 ~18:20 UTC (user):** API Gateway logs, last 24 hours, search `rest/v1` — **no
results**; `graphql` searched as well, nothing reported. So: no REST reads between ≈ 2026-09-22 18:00 and the fix at 13:45 UTC. Neither this project
nor my verification probes use the REST API (the probes ran as `anon` inside a direct database
connection), so a single hit would have meant an outsider. 2026-09-19 → 2026-09-22 ~18:00: UNKNOWN,
permanently.

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
  **REVERSED the same evening — see "Evening review" below.** The reasoning above was weaker than it
  looked: the detector then covered only *tables*, so a new *view* (which ignores RLS) or *function*
  (callable at `/rest/v1/rpc`) would have been exposed with nothing to notice; and "a frontend table
  that works without anyone deciding to open it" is exactly the behaviour least privilege forbids.
  The original text is kept so the sequence of decisions stays visible.
- **`service_role` left alone.** It is the secret-key role, bypasses RLS by design, is used by
  nothing here, and is not what the advisor flagged.
- **No broad "allow all" policy, no data removed, no protection weakened.**

## Trying to break the fix — every other route to the data, checked

Closing the tables is only half the job if the data can leave by another door. Checked on the live
database the same day:

| route | finding |
|---|---|
| views in `public` (a view runs as its owner by default, which bypasses RLS) | **none exist** |
| Supabase Realtime (broadcasts changes for tables in its publication) | **none of our tables is published**; no publication covers all tables |
| functions callable through the API | **none** — the only functions in `public` are trigger functions, which cannot be called directly |
| Storage buckets | **none** |
| `cron`, `vault` schemas (the dispatch job; the Vault holding the GitHub token) | the public API roles **cannot even enter** them |
| **`net` schema (pg_net — the HTTP client the hourly dispatch uses)** | **`anon` and `authenticated` hold SELECT/INSERT/UPDATE/DELETE on `net.http_request_queue` and `net._http_response`** — Supabase's own default for that extension, not something this project set |

**The `net` finding, stated exactly.** Every hour the dispatch job puts one request into
`net.http_request_queue`, carrying `Authorization: Bearer <the GitHub dispatch token>`; pg_net's
worker sends it within seconds and removes it. The stored responses (`net._http_response`) are
GitHub's replies and contain **no token** (checked by pattern, nothing printed). At the moment of
checking the queue was empty.

**Whether that is reachable is UNKNOWN from inside the database.** Supabase's REST API serves only
the schemas listed under *Project Settings → API → Exposed schemas*, which by default are `public`
and `graphql_public`. If `net` is not on that list, none of the above is reachable from outside at
all. If it were — which would have been a deliberate change — anyone with the anon key could read a
request in the seconds it waits (and so the token), or insert requests and make the database send
arbitrary HTTP calls.

**Deliberately not changed by me:** the grants on `net`. It is a platform-managed extension, the
hourly dispatch — the fix for GitHub's own unreliable scheduler — depends on it, and a Supabase
upgrade may restore its default grants anyway. The right control is the exposed-schemas list, which
lives only in the dashboard: a user check, `docs/ops/open_user_actions.md` item 5.

## A correction to my own earlier work

The security audit of 2026-09-21 (`docs/ops/security.md`) and the readiness gate that relied on it
scored Security as PARTIAL, with the least-privilege database role as the only gap. **That was
wrong.** The audit checked secrets, workflow permissions, logs and the trading boundary, but never
asked what the database exposes to Supabase's own public API — and a critical exposure was there
the whole time. Security should have been **FAIL** until today. The gate is corrected, and the
original text is left in place so the sequence stays honest.

## Evening review (2026-09-23 ~19:00–19:45 UTC) — the root cause, and what the project cannot close

Re-opened on the user's instruction to resolve the public-access issue *properly*: every schema,
every grant, every policy, the intended access for each role, then least privilege applied and
tested both ways. Read-only audit first; nothing changed until the tests below existed.

**Intended access, per role — the reference the detector enforces:**

| role | who it is | intended access | actual (live, 19:40 UTC) |
|---|---|---|---|
| `anon` | anyone holding the public anon key | **nothing** (a future frontend: SELECT on `backend_state` only, by an explicit, reviewed change) | nothing on the 6 tables; no view, no callable function; **no standing grant for new objects** |
| `authenticated` | anyone signed in via Supabase Auth — possibly *anyone*, if sign-ups are on | **nothing** — never treated as trusted | as `anon` |
| `service_role` | Supabase's secret admin key | unused by this project; bypasses RLS by design | unchanged (Supabase-managed); the key is not in the repository or `.env`, and no workflow references one |
| `postgres` | the hourly job today (owner) | everything, until the least-privilege role replaces it | as intended |
| `bitcoin_agent` | the prepared least-privilege role | exactly the job's reads and appends (`docs/ops/least_privilege_role.sql`, proven by integration test) | not created yet — needs a password, so it is the user's step |

**Finding 1 — the root cause was still live, and is now closed.** The morning's lockdown closed the
six tables that existed. The exposure itself came from **default privileges**: a standing rule that
every *new* table, view, sequence and function the owner role creates in `public` is granted in
full to `anon` and `authenticated` — **24 grants**, found by the audit. The next table created from
the dashboard, or a view a frontend added, would have been public the moment it existed.
`agent/database/schema.sql` now removes that rule (scoped to the owner role, the current schema, and
the two API roles), applied live with `python -m agent.migrate` at ~19:25 UTC: **24 → 0**.

- *Proved on live, in a transaction that was rolled back:* a brand-new table, view and sequence
  gave `anon`/`authenticated` nothing, and an `anon` read of the new table was refused; nothing was
  left behind.
- *Proved on real Postgres (scratch schema):* the Supabase rule re-created there does grant a new
  table (control), and after the schema files it no longer does — while the object made under the
  old rule keeps its grant, showing the change touched the rule and nothing else.
- *Drift:* the repository-vs-live check now compares default privileges too. Run **before** the
  migration it failed, listing exactly the 24 live grants; after it, 18/18 integration tests pass.
- *Function EXECUTE* also comes from a Postgres-wide default to PUBLIC that no per-schema rule can
  remove — so functions are policed by the detector instead (below).

**Finding 2 — the detector only knew about tables. It now sees every door in `public`:** views
readable by the API roles (a view runs as its owner and ignores RLS; an intended one must be
`security_invoker`), functions the API roles can execute (served at `/rest/v1/rpc`, with SECURITY
DEFINER named), and the standing default grants. Each new check was broken on purpose and caught
(`tools/guard_mutations.py`, now 31 of 31). Watchdog cost: the whole check runs in ~1.3 s.

**Finding 3 — what this project's role cannot close (reported as NOTES, never as failures).**
Supabase's own admin role owns and granted these; revoking them was *tried* inside a rolled-back
transaction and Postgres answered "no privileges could be revoked" for every object:

- `net.http_request_queue`, `net._http_response` (full rights, RLS off) and `net.http_post/get/delete`
  (EXECUTE) — the queue holds each hourly dispatch request, **GitHub token included, for a few
  seconds**; `http_post` would let a caller make the database send arbitrary HTTP requests;
- `extensions.pg_stat_statements` (query statistics). *Checked, count-only, nothing printed:* of
  2,081 stored statement texts, none holds an Anthropic key, a classic GitHub token, a Bearer value,
  a JWT or a database URL with a password. One matched the fine-grained-token pattern — examined with
  the match redacted inside the database, it is the **placeholder in the setup script's comment**
  ("after replacing github_pat_… with a … token"), and it does **not** equal the token in Vault. The
  cron job reads the real token from Vault at run time. And `anon` cannot read other roles'
  statement texts at all (0 of the matches visible as `anon`);
- `realtime.subscription`.

All of them are reachable **only if their schema is listed under Project Settings → API → Exposed
schemas** (Supabase's default is `public, graphql_public`). That setting is invisible from the
database, so its state stays **UNKNOWN until the user looks** — and it is now the *single* control
standing between the internet and the dispatch token. This is the one remaining check in
`docs/ops/open_user_actions.md` item 5.

**Also confirmed:** Realtime publishes no table; no storage bucket exists; `cron` and `vault` cannot
even be entered by the API roles; `auth.users` is empty.

## Remaining, and who owns it

- ~~Check the API logs for anon-key requests~~ — **done 2026-09-23 ~18:20 UTC** (user): nothing in the
  retained window; earlier days UNKNOWN permanently (see above).
- **Check "Exposed schemas"** (Project Settings → API) lists only `public` and `graphql_public` —
  user, ten seconds, now the one control over `net`.
- **The advisor may now show "RLS enabled, no policy"** on each table. That is informational and
  is the intended state: deny-all until a policy is deliberately added.
- ~~The hourly shadow step re-applies its schema file every run~~ — **fixed** (`17093f8`; schema
  changes go only through `python -m agent.migrate`, verified in a scheduled run 2026-09-23).
- **Least-privilege login role** — SQL ready and proven; creating a login role with a password is
  the user's step (`docs/ops/open_user_actions.md` item 2).
