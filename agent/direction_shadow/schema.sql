-- The prospective direction shadow track (E034, research/DIRECTION_TRACK.md, section 4). Its own tables: the live
-- prediction tables and the move-size shadow tables are never written by this track. Applied only by
-- `python -m agent.migrate`; the hourly job runs no DDL.
CREATE TABLE IF NOT EXISTS shadow_direction (
    id BIGSERIAL PRIMARY KEY,
    as_of TIMESTAMPTZ NOT NULL UNIQUE,       -- reference candle (last closed hour); one row per hour
    cutoff_at TIMESTAMPTZ NOT NULL,          -- as_of + 1h: nothing after this instant is an input
    fetched_at TIMESTAMPTZ NOT NULL,         -- when the candles were fetched (>= cutoff_at)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    model_version TEXT NOT NULL,             -- frozen artefact in agent/direction_shadow/models/
    artefact_sha256 TEXT NOT NULL,           -- canonical sha256 of that artefact as loaded
    pipeline_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,           -- the scoring code that produced the category-score inputs
    code_commit TEXT,                        -- git commit of the running code (GITHUB_SHA) when known
    price_source TEXT NOT NULL,
    reference_close DOUBLE PRECISION NOT NULL,
    -- the last trade price at fetched_at, from the still-open target candle: for the economics only, NEVER an input
    price_at_prediction DOUBLE PRECISION,
    live_close_match BOOLEAN,                -- reference close equals the live prediction's (NULL: no live row)
    live_scores_match BOOLEAN,               -- the four category scores equal the live prediction's (NULL: no live row)

    status TEXT NOT NULL CHECK (status IN ('ok', 'unavailable')),
    status_reason TEXT,                      -- why no probability could be computed
    features JSONB,                          -- the eight raw inputs: enough to recompute every probability exactly
    regime_rv_168 DOUBLE PRECISION,          -- previous 168h realised volatility: descriptive regime split only
    p_model DOUBLE PRECISION CHECK (p_model > 0 AND p_model < 1),
    p_one_feature DOUBLE PRECISION CHECK (p_one_feature > 0 AND p_one_feature < 1),
    p_base DOUBLE PRECISION CHECK (p_base > 0 AND p_base < 1),
    horizon_hours INTEGER NOT NULL CHECK (horizon_hours = 1),

    -- filled later by agent.direction_shadow.outcomes, once the target candle has closed
    outcome_status TEXT CHECK (outcome_status IN ('ok', 'unavailable')),
    outcome_close DOUBLE PRECISION,
    outcome_return DOUBLE PRECISION,         -- (outcome_close - reference_close) / reference_close, a FRACTION
    outcome_up BOOLEAN,                      -- outcome_return > 0 (a tie is not UP)
    outcome_checked_at TIMESTAMPTZ,

    CHECK (cutoff_at = as_of + interval '1 hour'),
    CHECK (fetched_at >= cutoff_at),
    -- all three probabilities exist on exactly the same rows (the registered identical-rows rule)
    CHECK ((status = 'ok') = (p_model IS NOT NULL AND p_one_feature IS NOT NULL AND p_base IS NOT NULL)),
    CHECK (status = 'ok' OR (p_model IS NULL AND p_one_feature IS NULL AND p_base IS NULL)),
    CHECK (outcome_status IS DISTINCT FROM 'ok' OR (outcome_close IS NOT NULL AND outcome_return IS NOT NULL AND outcome_up IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_shadow_direction_as_of ON shadow_direction (as_of);

-- Immutable once written: only the outcome part may be filled, exactly once (from NULL). Deletes are refused.
-- The row is compared as a whole minus the outcome columns, so a column added later is protected too.
CREATE OR REPLACE FUNCTION shadow_direction_guard_update() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    outcome text[] := ARRAY['outcome_status', 'outcome_close', 'outcome_return', 'outcome_up', 'outcome_checked_at'];
BEGIN
    IF OLD.outcome_status IS NOT NULL THEN
        RAISE EXCEPTION 'shadow_direction row % already has an outcome: update refused', OLD.id;
    END IF;
    IF (to_jsonb(NEW) - outcome) IS DISTINCT FROM (to_jsonb(OLD) - outcome) THEN
        RAISE EXCEPTION 'shadow_direction row %: only the outcome columns may change', OLD.id;
    END IF;
    RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION shadow_direction_forbid_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'shadow_direction is append-only: delete refused (row id %)', OLD.id;
END $$;
DROP TRIGGER IF EXISTS shadow_direction_guard_update ON shadow_direction;
CREATE TRIGGER shadow_direction_guard_update BEFORE UPDATE ON shadow_direction FOR EACH ROW EXECUTE FUNCTION shadow_direction_guard_update();
DROP TRIGGER IF EXISTS shadow_direction_forbid_delete ON shadow_direction;
CREATE TRIGGER shadow_direction_forbid_delete BEFORE DELETE ON shadow_direction FOR EACH ROW EXECUTE FUNCTION shadow_direction_forbid_delete();

-- Operational failures of the direction step. It must never cost the live record an hour, and nothing may be
-- swallowed either: every failure lands here with its reason. Append-only.
CREATE TABLE IF NOT EXISTS shadow_direction_errors (
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
CREATE INDEX IF NOT EXISTS idx_shadow_direction_errors_time ON shadow_direction_errors (occurred_at);
CREATE OR REPLACE FUNCTION shadow_direction_errors_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'shadow_direction_errors is append-only: % refused (row id %)', TG_OP, COALESCE(OLD.id, -1);
END $$;
DROP TRIGGER IF EXISTS shadow_direction_errors_append_only ON shadow_direction_errors;
CREATE TRIGGER shadow_direction_errors_append_only BEFORE UPDATE OR DELETE ON shadow_direction_errors FOR EACH ROW EXECUTE FUNCTION shadow_direction_errors_forbid_change();

-- Access lockdown, as in every schema file (reasoning in agent/database/schema.sql): RLS on with no policies for
-- the API roles, and their privileges revoked. Repeated here as code so this file stays self-contained.
DO $$
DECLARE
    t text;
    r text;
    s text;
BEGIN
    FOREACH t IN ARRAY ARRAY['shadow_direction', 'shadow_direction_errors'] LOOP
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
