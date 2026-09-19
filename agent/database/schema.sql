-- The stable, important fields (signal, confidence, timestamps, version stamps) are
-- strict typed columns. The parts still likely to change shape while the project is
-- being built (category scores, indicator snapshot, news used) live in JSONB columns
-- instead -- flexible now, without forcing a design that has to guess everything
-- perfectly upfront. All timestamps are UTC-aware (TIMESTAMPTZ) throughout.

CREATE TABLE IF NOT EXISTS predictions (
    id BIGSERIAL PRIMARY KEY,

    as_of TIMESTAMPTZ NOT NULL,              -- the hour this analysis is about
    fetched_at TIMESTAMPTZ NOT NULL,         -- when the underlying data was actually fetched
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

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
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    horizon_hours INTEGER NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    price_at_horizon DOUBLE PRECISION NOT NULL,
    pct_change_from_prediction DOUBLE PRECISION NOT NULL,
    UNIQUE (prediction_id, horizon_hours)
);

-- Migration: an earlier version had a separate baseline column that always held the
-- same value as pct_change_from_prediction (single asset: buy-and-hold IS the raw return).
ALTER TABLE prediction_outcomes DROP COLUMN IF EXISTS baseline_pct_change;
ALTER TABLE prediction_outcomes ALTER COLUMN price_at_horizon SET NOT NULL;
ALTER TABLE prediction_outcomes ALTER COLUMN pct_change_from_prediction SET NOT NULL;
