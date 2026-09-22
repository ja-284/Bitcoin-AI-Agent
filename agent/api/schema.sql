-- The published backend state: one row, replaced each hour.
--
-- This is the ONLY mutable table in the project, and the exception is deliberate. Every other
-- table is an append-only RECORD -- predictions, outcomes, shadow rows, shadow errors -- and
-- rewriting one would destroy evidence. This table is not a record: it is a cache of what
-- `agent/api/state.py` says about the other tables at a moment in time. It holds no history,
-- nothing is ever derived from it, and it can be rebuilt at any moment by re-running the
-- module. Losing it or overwriting it costs nothing.
--
-- It exists so a frontend can read ONE row instead of the raw tables, and so the honesty rules
-- in the contract (what is a probability, what is a heuristic, what has no demonstrated
-- predictive value) live in one place rather than being re-implemented in a UI.

CREATE TABLE IF NOT EXISTS backend_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- exactly one row, always
    contract_version TEXT NOT NULL,                    -- so a reader can refuse a shape it does not know
    generated_at TIMESTAMPTZ NOT NULL,                 -- when the snapshot was assembled
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),     -- when this row was last written
    state JSONB NOT NULL                               -- the whole contract, exactly as the module emits it
);

COMMENT ON TABLE backend_state IS
    'Derived cache of agent/api/state.py, one row, safe to overwrite. Not a record: no history, '
    'nothing depends on it, rebuild with "python -m agent.api.publish". A frontend reads this; '
    'it must not write to it, and it must not read the raw tables instead and re-label them itself.';
