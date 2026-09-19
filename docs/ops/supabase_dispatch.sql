-- Run once in Supabase -> SQL Editor, after replacing PASTE-TOKEN-HERE with a
-- fine-grained GitHub token that has Actions: Read and write on Bitcoin-AI-Agent only.
-- See docs/ops/external_trigger.md. Never commit a real token.

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- Store the token encrypted in Supabase Vault (re-running replaces the old secret).
delete from vault.secrets where name = 'github_dispatch_token';
select vault.create_secret('PASTE-TOKEN-HERE', 'github_dispatch_token');

-- Every hour at :12, ask GitHub to run the hourly workflow on main.
select cron.unschedule('github-hourly-dispatch') where exists (select 1 from cron.job where jobname = 'github-hourly-dispatch');
select cron.schedule(
  'github-hourly-dispatch',
  '12 * * * *',
  $$
  select net.http_post(
    url := 'https://api.github.com/repos/ja-284/Bitcoin-AI-Agent/actions/workflows/hourly.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || (select decrypted_secret from vault.decrypted_secrets where name = 'github_dispatch_token'),
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'Content-Type', 'application/json',
      'User-Agent', 'bitcoin-agent-dispatch'
    ),
    body := '{"ref":"main"}'::jsonb
  );
  $$
);

-- Check it is registered:
select jobid, jobname, schedule, active from cron.job;
