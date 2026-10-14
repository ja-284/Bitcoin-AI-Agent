-- Run once, as the owner role, AFTER `python -m agent.migrate` has created dispatch_responses and its
-- recorder (agent/database/dispatch_log.sql). Operational change 2, 2026-10-14.
--
-- Schedules the recorder as its OWN pg_cron job at :47 each hour: 35 minutes after the :12 dispatch,
-- far inside pg_net's six-hour retention, so up to five failed recorder runs in a row still lose
-- nothing. It is a separate job, in a separate transaction, from `github-hourly-dispatch`, which this
-- file never touches: a failing recorder cannot stop a dispatch. It holds no token and calls nothing
-- outside the database. Not part of the schema files on purpose: `agent.migrate` also builds scratch
-- schemas in the integration tests, and those must never schedule a job on the live database.
--
-- Re-running is safe (the old schedule is removed first). To remove it:
--   select cron.unschedule('dispatch-response-log');

select cron.unschedule('dispatch-response-log') where exists (select 1 from cron.job where jobname = 'dispatch-response-log');
select cron.schedule('dispatch-response-log', '47 * * * *', $$select public.record_dispatch_responses()$$);

-- Check: two jobs, both active.
select jobid, jobname, schedule, active from cron.job order by jobid;
