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

-- Access lockdown (2026-09-23): RLS on with no policies, and the Supabase API roles' privileges
-- revoked -- the same two layers as every other table (reasoning in agent/database/schema.sql).
-- This table is the one a frontend WILL read, and that is exactly why it is locked by default:
-- read access is granted deliberately, with one narrow read-only policy, when a frontend
-- actually exists (docs/api/contract_v1.md). Being meant for display is not the same as being
-- meant to be writable by anyone holding the public key.
DO $$
DECLARE
    r text;
BEGIN
    EXECUTE 'ALTER TABLE backend_state ENABLE ROW LEVEL SECURITY';
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON TABLE backend_state FROM %I', r);
        END IF;
    END LOOP;
END $$;

COMMENT ON TABLE backend_state IS
    'Derived cache of agent/api/state.py, one row, safe to overwrite. Not a record: no history, '
    'nothing depends on it, rebuild with "python -m agent.api.publish". A frontend reads this; '
    'it must not write to it, and it must not read the raw tables instead and re-label them itself.';
