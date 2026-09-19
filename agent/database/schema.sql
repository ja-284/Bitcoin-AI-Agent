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
-- once enough real time has actually passed. baseline_pct_change is a plain
-- buy-and-hold comparison over the same window, so a rising market isn't mistaken
-- for the system actually having skill.
CREATE TABLE IF NOT EXISTS prediction_outcomes (
    id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    horizon_hours INTEGER NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    price_at_horizon DOUBLE PRECISION,
    pct_change_from_prediction DOUBLE PRECISION,
    baseline_pct_change DOUBLE PRECISION,
    UNIQUE (prediction_id, horizon_hours)
);
