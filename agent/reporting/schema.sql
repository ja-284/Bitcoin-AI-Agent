-- The private stats read model (docs/api/stats_access.md): what the read-only reporting layer computes,
-- stored where ONE signed-in viewer's website may read it.
--
-- THIS IS A PRIVATE READ-ONLY STATISTICS INTERFACE. IT IS NOT THE FUTURE AUTOMATED-TRADING APPLICATION.
--
-- Two DERIVED caches, like backend_state: not records, no history of their own, rebuilt at any moment
-- by `python -m agent.reporting.publish`, and read by NOTHING in the system -- no scoring, prediction,
-- feature, threshold, model, checkpoint or research code ever reads them. They are written only by that
-- publisher, which runs in its own workflow AFTER each hourly run completes (never inside it).
--   reporting_snapshot  one row: the whole `all` document (latest run, statistics, breakdowns, health)
--   reporting_runs      one row per hour: that run's view, including its outcomes as known now
--   reporting_incidents one row per operational incident that leaves no trace in the record itself (2026-10-05):
--                       a failed hourly or watchdog run, a failed or long-stale stats publish. APPEND-ONLY,
--                       so an incident stays visible after the next hour succeeds.
-- Every value in them is exactly what agent/reporting produced; a website renders, never recomputes.

CREATE TABLE IF NOT EXISTS reporting_snapshot (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- exactly one row, always
    reporting_contract_version TEXT NOT NULL,          -- so a reader can refuse a shape it does not know
    as_known_at TIMESTAMPTZ NOT NULL,                  -- the moment the document describes
    generated_at TIMESTAMPTZ NOT NULL,                 -- when it was computed
    document JSONB NOT NULL                            -- agent.reporting.views.document("all", ...)
);

CREATE TABLE IF NOT EXISTS reporting_runs (
    hour TIMESTAMPTZ PRIMARY KEY,                      -- the run's reference hour (predictions.as_of)
    reporting_contract_version TEXT NOT NULL,
    as_known_at TIMESTAMPTZ NOT NULL,                  -- when this row's content last changed
    run JSONB NOT NULL                                 -- agent.reporting.views.run_view(...) with its detail
);

CREATE TABLE IF NOT EXISTS reporting_incidents (
    incident_key TEXT PRIMARY KEY,                     -- idempotent: 'github:<run id>:<attempt>' or 'publisher:<kind>:<time>'
    kind TEXT NOT NULL CHECK (kind IN ('hourly_run_failed', 'watchdog_failed', 'stats_publish_failed',
                                       'stats_snapshot_was_stale')),
    source TEXT NOT NULL CHECK (source IN ('workflow_event', 'github_api_backfill', 'publisher')),
    occurred_at TIMESTAMPTZ NOT NULL,                  -- when it happened (the failed run's start, the stale period's start)
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),    -- when it was written here (views 'as known at' use this)
    workflow TEXT,                                     -- the GitHub workflow name, for run incidents
    conclusion TEXT,                                   -- GitHub's conclusion, for run incidents
    run_url TEXT,                                      -- the public GitHub Actions run page, for run incidents
    detail TEXT NOT NULL                               -- one plain sentence; never an exception text or a secret
);
CREATE INDEX IF NOT EXISTS idx_reporting_incidents_time ON reporting_incidents (occurred_at);

-- Append-only: an incident, once recorded, can be neither edited nor erased by any code path. Its own guard
-- function, so this file stays self-contained.
CREATE OR REPLACE FUNCTION reporting_incidents_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'reporting_incidents is append-only: % refused (%)', TG_OP, COALESCE(OLD.incident_key, '?');
END $$;
DROP TRIGGER IF EXISTS reporting_incidents_append_only ON reporting_incidents;
CREATE TRIGGER reporting_incidents_append_only BEFORE UPDATE OR DELETE ON reporting_incidents
    FOR EACH ROW EXECUTE FUNCTION reporting_incidents_forbid_change();

-- Access lockdown (2026-09-27): first the same two layers as every other table -- RLS on, and the
-- Supabase API roles' privileges revoked -- so this file on its own leaves nothing open.
DO $$
DECLARE
    t text;
    r text;
BEGIN
    FOREACH t IN ARRAY ARRAY['reporting_snapshot', 'reporting_runs', 'reporting_incidents'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format('REVOKE ALL ON TABLE %I FROM %I', t, r);
            END IF;
        END LOOP;
    END LOOP;
END $$;

-- Then the ONE deliberate opening in this project, and nothing wider:
--   * SELECT only, on these three tables only;
--   * to `authenticated` only -- a Supabase Auth user who has signed in; `anon` (anyone holding the
--     public project key) gets nothing;
--   * and only for ONE named account, the Bitcoin AI Control Center's dedicated dashboard account, in a
--     session that passed two-factor sign-in (aal2). Since 2026-10-21, on the user's approval; until then any
--     account carrying the owner-set flag app_metadata.reporting_viewer = true could read (that rule,
--     `stats_viewer_read`, is dropped here). A password-only session, any other account and the old flag all
--     see zero rows.
-- `python -m agent.database.security` (the watchdog, every few hours) fails if anything here widens: a
-- second role, a second privilege, a second API-reaching policy (permissive policies combine with OR), or a
-- different condition. Guarded so the file still runs on a plain Postgres, where the Supabase roles and
-- auth.jwt() / auth.uid() do not exist.
-- Emergency deny-all (docs/api/stats_access.md): DROP POLICY control_center_read on the three tables; the
-- security check accepts the absence (closed), and `python -m agent.migrate` restores the policy.
DO $$
DECLARE
    t text;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated')
       AND to_regprocedure('auth.jwt()') IS NOT NULL AND to_regprocedure('auth.uid()') IS NOT NULL THEN
        FOREACH t IN ARRAY ARRAY['reporting_snapshot', 'reporting_runs', 'reporting_incidents'] LOOP
            EXECUTE format('GRANT SELECT ON TABLE %I TO authenticated', t);
            EXECUTE format('DROP POLICY IF EXISTS stats_viewer_read ON %I', t);
            EXECUTE format('DROP POLICY IF EXISTS control_center_read ON %I', t);
            EXECUTE format($p$CREATE POLICY control_center_read ON %I FOR SELECT TO authenticated
                             USING (auth.uid() = '9e021560-dd06-40f1-80ad-d58d44d9a3f6'::uuid
                                    AND (auth.jwt() ->> 'aal') = 'aal2')$p$, t);
        END LOOP;
    END IF;
END $$;

COMMENT ON TABLE reporting_snapshot IS
    'Private stats read model (docs/api/stats_access.md): derived cache of agent/reporting, written only by '
    'agent.reporting.publish, readable only by the dedicated dashboard account in a two-factor (aal2) session. '
    'Read by nothing in the prediction system. NOT the trading application.';
COMMENT ON TABLE reporting_runs IS
    'Private stats read model: one derived row per run hour (agent.reporting.views.run_view). Written only by '
    'agent.reporting.publish; readable only by the dedicated dashboard account (aal2); read by nothing in the prediction system.';
COMMENT ON TABLE reporting_incidents IS
    'Private stats read model: append-only operational incidents (failed hourly/watchdog runs, failed or stale stats '
    'publishes), written only by agent.reporting.incidents / publish; readable only by the dedicated dashboard account (aal2).';
