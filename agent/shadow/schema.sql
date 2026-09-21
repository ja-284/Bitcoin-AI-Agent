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
