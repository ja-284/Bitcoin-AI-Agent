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

## 2. A least-privilege database role — worth doing, but NOT yet (a prerequisite is missing)

**What it is.** The hourly job currently connects as the Supabase project's `postgres` role, which
can do anything, including dropping tables and bypassing Row Level Security. It only ever needs to
read and insert.

**Why it matters.** If the `DATABASE_URL` secret ever leaked, the damage would be bounded by what
the role can do. Today that bound is "everything".

**Why not yet (updated 2026-09-23).** The SQL this section originally gave would no longer work, and
following it would have broken the hourly job:

1. Since schema version 4, **every table has Row Level Security on with no policies**
   (`docs/ops/security_2026-09-23_public_api_exposure.md`). `postgres` bypasses that; a new role
   does not, so with grants alone it would see zero rows and be unable to insert anything. It needs
   policies of its own, scoped to it and nothing else.
2. **The hourly shadow step re-applies its schema file on every run**, which includes `ALTER TABLE`
   statements, and only a table's owner may run those. Under a restricted role the shadow step
   would fail every hour. This has to change first — schema application belongs to a deliberate
   migration step, not to every hourly run. It is scheduled as the next controlled change.

**When the prerequisite is done**, the SQL will be this (run in Supabase → *SQL Editor*, with a long
random password you generate yourself and never paste anywhere else):

```sql
CREATE ROLE bitcoin_agent LOGIN PASSWORD 'replace-with-a-long-random-password';
GRANT USAGE ON SCHEMA public TO bitcoin_agent;

-- privileges: read and append the record, grade shadow rows, publish the snapshot
GRANT SELECT, INSERT ON predictions, prediction_outcomes, shadow_move_size, shadow_run_errors TO bitcoin_agent;
GRANT SELECT ON schema_meta TO bitcoin_agent;
GRANT UPDATE (outcome_status, outcome_close, outcome_return, outcome_large, outcome_checked_at)
  ON shadow_move_size TO bitcoin_agent;
GRANT SELECT, INSERT, UPDATE ON backend_state TO bitcoin_agent;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bitcoin_agent;

-- RLS is on everywhere, and this role does not bypass it: it needs policies, scoped TO it only,
-- so none of them can ever be reached through the public API.
CREATE POLICY backend_read   ON predictions         FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON predictions         FOR INSERT TO bitcoin_agent WITH CHECK (true);
CREATE POLICY backend_read   ON prediction_outcomes FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON prediction_outcomes FOR INSERT TO bitcoin_agent WITH CHECK (true);
CREATE POLICY backend_read   ON shadow_move_size    FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON shadow_move_size    FOR INSERT TO bitcoin_agent WITH CHECK (true);
CREATE POLICY backend_grade  ON shadow_move_size    FOR UPDATE TO bitcoin_agent USING (outcome_status IS NULL);
CREATE POLICY backend_read   ON shadow_run_errors   FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON shadow_run_errors   FOR INSERT TO bitcoin_agent WITH CHECK (true);
CREATE POLICY backend_read   ON schema_meta         FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_all    ON backend_state       FOR ALL    TO bitcoin_agent USING (true) WITH CHECK (true);
```

The live security check (`python -m agent.database.security`) deliberately ignores policies scoped
to a private role like this one, and would still fail loudly if any of them reached `anon`,
`authenticated` or `public`.

**What protects you meanwhile.** The secret is not in git, is not printed by any log, and
psycopg's errors do not echo the connection string (checked). Append-only triggers on the four
record tables mean even a full-privilege connection cannot quietly rewrite history — a change
attempt raises instead. And since 2026-09-23, nothing is reachable through the public API at all.

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
structured score. The schema asks it to echo each headline back. At roughly 60 headlines an hour
that costs about **$0.02 a run, near $15 a month** — above the "well under $10/month" estimate
made when the window held about 16 headlines.

**The options.**

- **Leave it.** Simplest, and the news component has been validated as it stands (E009).
- **Drop the echoed headline from the schema.** Roughly halves the cost. But it changes the AI's
  task, so E009's validation would no longer apply and would need re-running (a few API calls and
  an afternoon). It also makes debugging harder: today a mis-scored headline is visible in the
  stored answer.

I have not done this, because it trades a validated component for money and that is your call, not
a technical one. Tell me either way and I will implement it or close the item.

---

## 5. Check Supabase's API logs for anonymous requests — once, soon

**What it is.** Until 2026-09-23 every table was readable and writable through Supabase's public API
by anyone holding the project's anon key (`docs/ops/security_2026-09-23_public_api_exposure.md`).
That is now closed. The data shows **no sign of any outside write**. What the data cannot show is
whether anyone **read** it, because reads leave no trace in tables.

**What to do.** Supabase dashboard → *Logs* → *API Gateway* (or *Edge / PostgREST* logs), and look
for requests to `/rest/v1/` or `/graphql/v1` made with the anon key before 2026-09-23 ~13:45 UTC.
The backend never uses the REST API — it connects to Postgres directly — so **any** such request
did not come from this project. If there are none, the exposure was never used. If there are some,
tell me which tables and when, and I will check them against the record.

**Also expect** the security advisor to show *"RLS enabled, no policy"* on each table from now on.
That is informational and is the intended state: deny everything until a policy is added on purpose.

## Not on this list, deliberately

- **Anything involving real money, orders, wallets or exchanges.** The project is analysis-only and
  stays that way.
- **Opening the sealed holdout.** That is a one-way door and needs your explicit go-ahead, which is
  tracked with the research work, not here.
