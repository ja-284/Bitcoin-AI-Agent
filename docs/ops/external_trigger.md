# Triggering the hourly job from outside GitHub's scheduler

**Why:** on go-live day GitHub's built-in scheduler ran only 2 of the first 8 hourly
slots for this repository, each 20–40 minutes late. That is the widely reported
behaviour for new, low-activity repositories, and it is not something the workflow file
can fix. GitHub *does* reliably start a run when asked to through its API
(`workflow_dispatch`), so the fix is to have something reliable ask it, once an hour.

Both options below are free and use accounts this project already has. The job itself
is unchanged: if the hour is already saved, a triggered run exits in seconds.

## Option A (recommended): Supabase `pg_cron` calls GitHub

The database we already run has a built-in scheduler (`pg_cron`) and an HTTP client
(`pg_net`). A scheduled SQL job posts to GitHub's API every hour. The GitHub token is
stored encrypted in Supabase Vault, not in this repository.

1. **Create a GitHub token** (a password that only allows starting this workflow):
   GitHub → your profile picture → *Settings* → *Developer settings* → *Personal access
   tokens* → *Fine-grained tokens* → *Generate new token*.
   - Name: `supabase-dispatch`; expiration: 1 year (set a reminder).
   - Repository access: *Only select repositories* → `Bitcoin-AI-Agent`.
   - Permissions → Repository permissions → **Actions: Read and write**. Nothing else.
   - Generate, then copy the token (shown once).
2. **Enable the two extensions** in Supabase: *Database* → *Extensions* → enable
   `pg_cron` and `pg_net`.
3. **Run the script** `docs/ops/supabase_dispatch.sql` in Supabase → *SQL Editor*,
   after replacing `PASTE-TOKEN-HERE` with the token. Run it once. Do not commit the
   token anywhere.
4. **Verify**: within about 15 minutes, the Actions tab should show a run whose event is
   `workflow_dispatch` at :12 past the hour, and then one every hour.

To change the minute, edit the cron expression in the script and re-run it (the
`cron.unschedule` line removes the old job first).

## Option B: cron-job.org

A free external cron service can make the same API call. Create a job with:
URL `https://api.github.com/repos/ja-284/Bitcoin-AI-Agent/actions/workflows/hourly.yml/dispatches`,
method POST, body `{"ref":"main"}`, headers `Authorization: Bearer <token>`,
`Accept: application/vnd.github+json`, `User-Agent: bitcoin-agent`, schedule hourly at :12.
Simpler UI, but a third party holds the token — which is why Option A is preferred.

## Independent alarm (still recommended)

The self-check step turns a *failed* run into an email, but a trigger that silently
stops firing produces no run at all. A heartbeat monitor outside both GitHub and
Supabase catches that: healthchecks.io (free) → create a check, period 1 hour, grace
1 hour → add its ping URL as the `HEARTBEAT_URL` repository secret. The workflow already
pings it after every successful run.
