# Open user actions — the things I cannot do from the repository

Everything in this file needs an account or a service that only you can log into. For each one:
what it is, why it matters, exactly what to do, and — importantly — **what already protects you
while it is not done**, so you can judge the urgency honestly rather than from a scary-sounding
name.

None of these is blocking. The system runs correctly without them. They close gaps.

Last reviewed: 2026-09-23 (item 2 corrected, item 5 added after the public-API finding).

---

## 1. Heartbeat alarm (healthchecks.io) — the only one I would actually hurry

**What it is.** A free outside service that expects a ping from the hourly job. If the ping does
not arrive within a grace window, it emails you.

**Why it matters.** Every alarm this project currently has lives *inside* GitHub. If GitHub
stops running the job — as it already did once, in the first days, when its own scheduler fired
2 of 8 slots — nothing runs, so nothing complains. Silence looks identical to success. A
heartbeat is the only check that fails *because* nothing happened.

**Already done, in code.** The workflow's last step pings `$HEARTBEAT_URL` if that secret exists,
and it is placed after every other step, so a ping means the whole hour genuinely succeeded —
prediction saved, self-check passed, shadow row written and graded. Nothing else is needed from
me; the code path has been there since go-live and is inert until the secret is set.

**What to do** (about five minutes):

1. Sign up free at <https://healthchecks.io>.
2. Create a check. Set **Period** to 1 hour and **Grace** to 30 minutes (the job runs at :12;
   30 minutes covers an ordinary GitHub delay without crying wolf).
3. Copy its ping URL (it looks like `https://hc-ping.com/<a-long-id>`).
4. In GitHub: repository → *Settings* → *Secrets and variables* → *Actions* → *New repository
   secret*. Name it exactly `HEARTBEAT_URL`, paste the URL, save.

That is all. The next hourly run starts pinging, and you will be emailed if two hours pass in
silence. Do not paste the URL into a chat or commit it — anyone holding it can silence your alarm.

**What protects you meanwhile.** The job self-checks that the hour's prediction was saved; a
missed hour makes the *next* run fail, which GitHub emails you about; a watchdog workflow runs
every three hours; the weekly report lists missed hours and shadow errors. All of these depend on
GitHub running something. That is the hole.

---

## 2. A least-privilege database role — ready for you once one scheduled run confirms it

**What it is.** The hourly job currently connects as the Supabase project's `postgres` role, which
can do anything, including dropping tables and bypassing Row Level Security. It only ever needs to
read and append rows.

**Why it matters.** If the `DATABASE_URL` secret ever leaked, the damage would be bounded by what
the role can do. Today that bound is "everything".

**What had to happen first (done 2026-09-23).**

1. Since schema version 4 every table has Row Level Security on with no policies. `postgres`
   bypasses that; a new role does not, so it needs policies of its own, scoped to it alone.
2. The hourly job used to re-apply schema SQL every run, which only a table's owner may do. It no
   longer does (commit `17093f8`; schema changes now go through `python -m agent.migrate`). **The
   first scheduled run on that code is at 15:12 UTC on 2026-09-23** — once it is seen working, this
   item is ready.

**The permissions are in one file that a test proves: [`least_privilege_role.sql`](least_privilege_role.sql).**
An integration test creates a throwaway role, applies that exact file to it in a scratch schema, and
runs every write path the hourly job uses *as that role* — saving predictions, grading outcomes,
writing and grading shadow rows, recording errors, publishing the snapshot — then checks that
rewriting, deleting, changing a probability, moving the schema version, switching RLS off and
dropping a table are all refused.

That test exists because the SQL I first wrote here was **wrong twice on the same day**: the first
version had grants but no policies (the role would have seen and inserted nothing under RLS), and
the corrected version still had an UPDATE policy without `WITH CHECK`, which Postgres then applies
to the updated row — so every shadow grading would have been refused with "new row violates
row-level security policy". The test was run against that buggy version and fails exactly that way.

**What to do**, when the item is ready:

1. Supabase → *SQL Editor*: create the role with a long random password you generate yourself and
   never paste anywhere else —
   `CREATE ROLE bitcoin_agent LOGIN PASSWORD '...';`
2. In the same editor, run the whole of `docs/ops/least_privilege_role.sql`.
3. Build the connection string you already have, but with the new role and password (for Supabase's
   pooler the username is usually `bitcoin_agent.<project-ref>`), and replace the `DATABASE_URL`
   **repository secret** in GitHub. Keep the old `postgres` string for `python -m agent.migrate`.
4. Run the hourly workflow once by hand (Actions → *Hourly Bitcoin analysis* → *Run workflow*) and
   check it is green. If anything fails, put the old secret back: nothing is lost, the next hour
   recomputes.

**What protects you meanwhile.** The secret is not in git, is not printed by any log, and
psycopg's errors do not echo the connection string (checked). Append-only triggers on the four
record tables mean even a full-privilege connection cannot quietly rewrite history. And since
2026-09-23 nothing is reachable through the public API at all.

---

## 3. Renew the dispatch token before 2027-09-20 — a calendar item, nothing to do now

**What it is.** Supabase's `pg_cron` job starts the hourly workflow by calling GitHub's API with
a fine-grained token called `supabase-dispatch`. **That token expires 2027-09-20.**

**Why it matters.** When it expires, the reliable trigger stops. GitHub's own schedule remains as
a backup, but it is the unreliable one — that is the whole reason the Supabase trigger exists.

**What to do, when the time comes.** Generate a new fine-grained token with the same single
permission (Actions: read and write, on this repository only), then in Supabase → *SQL Editor*
re-run the vault update from `docs/ops/external_trigger.md` with the new value.

**How you will notice if it slips.** A 401 in Supabase's `net._http_response`, and the weekly
report showing hours covered only by GitHub's own slots. Put a calendar reminder for
**September 2027** — that is the most reliable mechanism available.

---

## 4. Decide about the AI cost of news — a judgement call, not a task

**What it is.** The news scorer sends each hour's headlines to Claude Haiku and gets back a
structured score. The schema asks it to echo each headline back.

**Measured, no longer estimated (2026-09-23).** Every run now records the token counts the API
itself reports (`run_meta.ai_usage`), and the weekly report prices them. First real measurement,
56 headlines: news 1,753 in / 2,188 out tokens ($0.0127), explanation 509 in / 266 out ($0.0037),
**$0.0164 a run ≈ $11.80 a month** at today's list prices (Haiku 4.5 $1/$5, Sonnet 5 $2/$10 per
million tokens). The earlier "$0.02 a run, near $15 a month" was a little high. It still exceeds the
original "well under $10/month" estimate, made when the window held about 16 headlines. Most of the
news cost is the answer (2,188 of the 3,941 news tokens, at five times the input price), and
echoing the headline is a large share of that answer.

**The options.**

- **Leave it.** Simplest, and the news component has been validated as it stands (E009).
- **Drop the echoed headline from the schema.** Roughly halves the news cost (a few dollars a
  month at today's volume; the weekly report will show the real before-and-after). But it changes the AI's
  task, so E009's validation would no longer apply and would need re-running (a few API calls and
  an afternoon). It also makes debugging harder: today a mis-scored headline is visible in the
  stored answer.

I have not done this, because it trades a validated component for money and that is your call, not
a technical one. Tell me either way and I will implement it or close the item.

---

## 5. Check Supabase's API logs for anonymous requests — once, BEFORE 2026-09-24 ~13:45 UTC

**DONE, 2026-09-23 ~18:20–18:35 UTC, by the user:** Logs → API Gateway, last 24 hours, search
`rest/v1` → **no results**; the `graphql` search was done too, with nothing reported. What this
proves, and what it does not:

- **Proves:** no request reached either API door in the retained window, ≈ 2026-09-22 18:00 →
  2026-09-23 13:45 UTC (the last ~19 hours of the exposure).
- **Does not prove:** anything about 2026-09-19 → 2026-09-22 ~18:00. Those days had already left the
  Free plan's 1-day log before anyone looked. **They stay UNKNOWN permanently** — not "not read".
- **Weight of the evidence:** the project's hostname and anon key were never published (checked), and
  the one window we can see is empty, which makes access in the unseen days unlikely but not
  excluded. The data involved is non-secret research output, and nothing was written (proven from the
  data itself).

**Deadline, and why.** Supabase's Free plan keeps API and database logs for **1 day** (Pro 7, Team
28, Enterprise 90 — supabase.com/pricing, read 2026-09-23). The exposure closed at ~13:45 UTC on
2026-09-23, so by ~13:45 UTC on **2026-09-24** the last log line from the exposed period is gone and
this question becomes permanently unanswerable. Even checked today, the logs reach back only one day:
they cover roughly the last 21 hours of an exposure that existed since the project was created
(2026-09-19). **"No anonymous requests in the logs" therefore means "none in the last day of the
exposure", not "none ever"** — the earlier days stay UNKNOWN whatever the logs show.

**What it is.** Until 2026-09-23 every table was readable and writable through Supabase's public API
by anyone holding the project's anon key (`docs/ops/security_2026-09-23_public_api_exposure.md`).
That is now closed. The data shows **no sign of any outside write**. What the data cannot show is
whether anyone **read** it, because reads leave no trace in tables.

**What to do.** Supabase dashboard → *Logs* → *API Gateway* (or *Edge / PostgREST* logs), and look
for requests to `/rest/v1/` or `/graphql/v1` made with the anon key before 2026-09-23 ~13:45 UTC.
The backend never uses the REST API — it connects to Postgres directly — so **any** such request
did not come from this project. If there are none, the exposure was never used. If there are some,
tell me which tables and when, and I will check them against the record.

**STILL OPEN — and since 2026-09-23 evening, the single control over the dispatch token.** The
evening review showed that Supabase's own admin role grants the public API roles full rights on the
`net` schema, and this project's role cannot revoke them (tried; Postgres refused). So whether the
token can be read in the seconds it waits in `net.http_request_queue` depends only on this setting.

**Check one setting while you are there** (ten seconds): *Project Settings → API → Exposed
schemas*. It should list only `public` and `graphql_public`. If `net`, `vault`, `cron` or anything
else is listed, remove it — `net` in particular holds each hourly dispatch request, GitHub token
included, for a few seconds, and Supabase's defaults let the anon role read it if the schema is
exposed. I cannot see this setting from inside the database, which is why it is marked UNKNOWN
rather than assumed safe.

**Also expect** the security advisor to show *"RLS enabled, no policy"* on each table from now on.
That is informational and is the intended state: deny everything until a policy is added on purpose.

## Not on this list, deliberately

- **Anything involving real money, orders, wallets or exchanges.** The project is analysis-only and
  stays that way.
- **Opening the sealed holdout.** That is a one-way door and needs your explicit go-ahead, which is
  tracked with the research work, not here.
