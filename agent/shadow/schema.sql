-- The live shadow record of the research move-size model (Phase 13). Its own table:
-- the live prediction tables are never touched by the shadow job. Applied by
-- agent.shadow.db.ensure_schema() on every run (idempotent), so a fresh database or a
-- fresh job runner needs no manual step.
CREATE TABLE IF NOT EXISTS shadow_move_size (
    id BIGSERIAL PRIMARY KEY,
    as_of TIMESTAMPTZ NOT NULL UNIQUE,       -- reference candle (last closed hour); one row per hour
    cutoff_at TIMESTAMPTZ NOT NULL,          -- as_of + 1h: nothing after this instant may be used
    fetched_at TIMESTAMPTZ NOT NULL,         -- when the candles were fetched (>= cutoff_at)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    model_version TEXT NOT NULL,             -- frozen artefact in agent/shadow/models/
    pipeline_version TEXT NOT NULL,
    code_commit TEXT,                        -- git commit of the running code (GITHUB_SHA) when known
    price_source TEXT NOT NULL,
    reference_close DOUBLE PRECISION NOT NULL,
    live_close_match BOOLEAN,                -- reference close equals the live prediction's close for this hour (NULL: no live row yet)

    status TEXT NOT NULL CHECK (status IN ('ok', 'unavailable')),
    status_reason TEXT,                      -- why no probability could be computed
    features JSONB,                          -- raw input values before log/scaling: enough to recompute p exactly
    p_raw DOUBLE PRECISION,
    p_calibrated DOUBLE PRECISION,
    threshold DOUBLE PRECISION NOT NULL,
    horizon_hours INTEGER NOT NULL,

    -- filled later by agent.shadow.outcomes, once the target candle has closed
    outcome_status TEXT CHECK (outcome_status IN ('ok', 'unavailable')),
    outcome_close DOUBLE PRECISION,
    outcome_return DOUBLE PRECISION,         -- (outcome_close - reference_close) / reference_close, a FRACTION
    outcome_large BOOLEAN,                   -- |outcome_return| > threshold
    outcome_checked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_shadow_move_size_as_of ON shadow_move_size (as_of);

-- Backend Phase E: a shadow row's prediction part is immutable; only the outcome part may be
-- filled, exactly once (from NULL). Deletes are refused.
CREATE OR REPLACE FUNCTION shadow_guard_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.outcome_status IS NOT NULL THEN
        RAISE EXCEPTION 'shadow_move_size row % already has an outcome: update refused', OLD.id;
    END IF;
    IF NEW.as_of IS DISTINCT FROM OLD.as_of OR NEW.cutoff_at IS DISTINCT FROM OLD.cutoff_at OR NEW.fetched_at IS DISTINCT FROM OLD.fetched_at
       OR NEW.model_version IS DISTINCT FROM OLD.model_version OR NEW.pipeline_version IS DISTINCT FROM OLD.pipeline_version
       OR NEW.code_commit IS DISTINCT FROM OLD.code_commit OR NEW.price_source IS DISTINCT FROM OLD.price_source
       OR NEW.reference_close IS DISTINCT FROM OLD.reference_close OR NEW.live_close_match IS DISTINCT FROM OLD.live_close_match
       OR NEW.status IS DISTINCT FROM OLD.status OR NEW.status_reason IS DISTINCT FROM OLD.status_reason
       OR NEW.features IS DISTINCT FROM OLD.features OR NEW.p_raw IS DISTINCT FROM OLD.p_raw OR NEW.p_calibrated IS DISTINCT FROM OLD.p_calibrated
       OR NEW.threshold IS DISTINCT FROM OLD.threshold OR NEW.horizon_hours IS DISTINCT FROM OLD.horizon_hours OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'shadow_move_size row %: only the outcome columns may change', OLD.id;
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION shadow_forbid_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'shadow_move_size is append-only: delete refused (row id %)', OLD.id;
END $$;
DROP TRIGGER IF EXISTS shadow_move_size_guard_update ON shadow_move_size;
CREATE TRIGGER shadow_move_size_guard_update BEFORE UPDATE ON shadow_move_size FOR EACH ROW EXECUTE FUNCTION shadow_guard_update();
DROP TRIGGER IF EXISTS shadow_move_size_forbid_delete ON shadow_move_size;
CREATE TRIGGER shadow_move_size_forbid_delete BEFORE DELETE ON shadow_move_size FOR EACH ROW EXECUTE FUNCTION shadow_forbid_delete();

-- Operational failures of the shadow job (Backend Phase C/I follow-up, 2026-09-22). A research
-- add-on must not drag the live hourly job down, but nothing may be swallowed either: every
-- failure is recorded here with its reason, the weekly report prints them, and the watchdog
-- fails when they persist. Append-only, like the rest of the record.
CREATE TABLE IF NOT EXISTS shadow_run_errors (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expected_as_of TIMESTAMPTZ,              -- the hour the run was trying to score (from the clock)
    step TEXT NOT NULL,                      -- load_model | fetch | compute | save | outcomes
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    model_version TEXT,
    pipeline_version TEXT,
    code_commit TEXT
);
CREATE INDEX IF NOT EXISTS idx_shadow_run_errors_time ON shadow_run_errors (occurred_at);
-- Own guard function so this file stays self-contained (the predictions schema has its own).
CREATE OR REPLACE FUNCTION shadow_errors_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'shadow_run_errors is append-only: % refused (row id %)', TG_OP, COALESCE(OLD.id, -1);
END $$;
DROP TRIGGER IF EXISTS shadow_run_errors_append_only ON shadow_run_errors;
CREATE TRIGGER shadow_run_errors_append_only BEFORE UPDATE OR DELETE ON shadow_run_errors FOR EACH ROW EXECUTE FUNCTION shadow_errors_forbid_change();

-- Access lockdown (2026-09-23): RLS on with no policies, and the Supabase API roles' privileges
-- revoked. The reasoning is written out in agent/database/schema.sql; it is repeated here as
-- code, not as a reference, so this file stays self-contained and its tables are protected
-- whichever schema file is applied first.
DO $$
DECLARE
    t text;
    r text;
    s text;
BEGIN
    FOREACH t IN ARRAY ARRAY['shadow_move_size', 'shadow_run_errors'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format('REVOKE ALL ON TABLE %I FROM %I', t, r);
                s := pg_get_serial_sequence(t, 'id');
                IF s IS NOT NULL THEN
                    EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM %I', s, r);
                END IF;
            END IF;
        END LOOP;
    END LOOP;
END $$;
