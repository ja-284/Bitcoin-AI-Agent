-- The stable, important fields (signal, confidence, timestamps, version stamps) are
-- strict typed columns. The parts still likely to change shape while the project is
-- being built (category scores, indicator snapshot, news used) live in JSONB columns
-- instead -- flexible now, without forcing a design that has to guess everything
-- perfectly upfront. All timestamps are UTC-aware (TIMESTAMPTZ) throughout.

CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,

    as_of TIMESTAMPTZ NOT NULL,              -- open time of the reference candle (last fully-closed hour)
    cutoff_at TIMESTAMPTZ,                   -- information cutoff = close of the reference candle (as_of + 1h)
    fetched_at TIMESTAMPTZ NOT NULL,         -- when the underlying data was actually fetched (>= cutoff_at)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    pipeline_version TEXT,                   -- see agent/version.py; distinguishes the original 0.1.0 baseline from corrected runs
    run_meta JSONB,                          -- news exclusion counts, data-quality flags, lag: how much to trust this run

    close_price DOUBLE PRECISION NOT NULL,
    price_source TEXT NOT NULL,
    price_is_synthetic BOOLEAN NOT NULL DEFAULT FALSE,

    overall_score DOUBLE PRECISION NOT NULL,
    signal TEXT NOT NULL CHECK (signal IN ('BUY', 'HOLD', 'SELL')),

    agreement_score DOUBLE PRECISION NOT NULL,
    completeness_score DOUBLE PRECISION NOT NULL,
    overall_confidence DOUBLE PRECISION NOT NULL,

    -- version stamps: without these, later comparisons would silently mix predictions
    -- made by different formulas/models, corrupting any calibration or backtest.
    scoring_version TEXT NOT NULL,
    ai_model_news TEXT,
    ai_model_explanation TEXT,

    explanation TEXT,
    category_scores JSONB NOT NULL,          -- list of {name, score, weight, is_independent, detail}
    news_items JSONB,                        -- headlines actually used this run
    raw_indicators JSONB,                    -- full indicator snapshot

    UNIQUE (as_of)                           -- one prediction per hour
);

CREATE INDEX IF NOT EXISTS idx_predictions_as_of ON predictions (as_of);

-- One row per (prediction, time horizon). Filled in later by the outcome tracker,
-- once enough real time has actually passed. Only the raw price and return are
-- stored -- whether a signal was "right" is decided at analysis time, not here.
-- pct_change_from_prediction is also exactly what plain buy-and-hold would have
-- earned over the window, which is the baseline needed to tell real skill apart
-- from Bitcoin simply drifting up or down on its own.
-- status 'ok': graded. status 'unavailable': the target candle does not exist in the
-- exchange's history (downtime gap); price/pct are NULL and the row stops further retries.
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    horizon_hours INTEGER NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'unavailable')),
    price_at_horizon DOUBLE PRECISION,
    pct_change_from_prediction DOUBLE PRECISION,
    UNIQUE (prediction_id, horizon_hours)
);

-- Migration: an earlier version had a separate baseline column that always held the
-- same value as pct_change_from_prediction (single asset: buy-and-hold IS the raw return).
ALTER TABLE prediction_outcomes DROP COLUMN IF EXISTS baseline_pct_change;
-- Migration (pipeline 0.2.0): explicit 'unavailable' outcomes for missing target candles.
ALTER TABLE prediction_outcomes ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ok';
ALTER TABLE prediction_outcomes ALTER COLUMN price_at_horizon DROP NOT NULL;
ALTER TABLE prediction_outcomes ALTER COLUMN pct_change_from_prediction DROP NOT NULL;

-- Migration (pipeline 0.2.0): explicit information cutoff and version stamps.
-- Rows written before this existed were pipeline 0.1.0: their cutoff is derivable
-- (as_of + 1h) but their news was NOT limited to it -- see agent/version.py.
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS cutoff_at TIMESTAMPTZ;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS pipeline_version TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS run_meta JSONB;
UPDATE predictions SET cutoff_at = as_of + interval '1 hour' WHERE cutoff_at IS NULL;
UPDATE predictions SET pipeline_version = '0.1.0' WHERE pipeline_version IS NULL;
