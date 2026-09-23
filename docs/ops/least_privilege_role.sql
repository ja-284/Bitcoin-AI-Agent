-- Permissions for a least-privilege role for the hourly job (docs/ops/open_user_actions.md, item 2).
--
-- THIS FILE IS EXECUTED BY A TEST. tests/integration/test_db_idempotency.py creates a throwaway
-- role, applies exactly this file to it in a scratch schema, and then runs the backend's real
-- write paths AS that role -- saving predictions, grading outcomes, writing and grading shadow
-- rows, recording errors, publishing the snapshot -- and checks that everything the role must
-- NOT be able to do is refused. The SQL shown to a human and the SQL that was proven are the
-- same text, because an earlier hand-written version of this was wrong twice (see below).
--
-- Deliberately NOT in this file: CREATE ROLE. Creating a login role with a password is an
-- account-creation step and belongs to the project owner:
--
--     CREATE ROLE bitcoin_agent LOGIN PASSWORD '<a long random password you generate yourself>';
--
-- then run this file, then change the DATABASE_URL secret to the new role. Keep the `postgres`
-- connection string for `python -m agent.migrate`: schema changes need the tables' owner, and
-- since 2026-09-23 the hourly job never makes schema changes.
--
-- Why policies at all: since schema version 4 every table has Row Level Security on with no
-- policies. `postgres` bypasses RLS; this role must not, so it gets policies of its own, each
-- scoped TO this role alone -- none of them is reachable through Supabase's public API, and the
-- live security check (python -m agent.database.security) would report any that were.
--
-- Two mistakes this file exists to prevent, both made in the hand-written version on 2026-09-23:
--   1. grants alone, no policies: under RLS the role would have seen no rows and inserted nothing;
--   2. an UPDATE policy with USING but no WITH CHECK: Postgres then applies the USING condition to
--      the UPDATED row too, so "outcome_status IS NULL" would have rejected every grading, since
--      grading is precisely what sets outcome_status.

GRANT USAGE ON SCHEMA public TO bitcoin_agent;

-- the record: read and append, never change (the append-only triggers refuse that anyway)
GRANT SELECT, INSERT ON predictions, prediction_outcomes TO bitcoin_agent;
CREATE POLICY backend_read   ON predictions         FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON predictions         FOR INSERT TO bitcoin_agent WITH CHECK (true);
CREATE POLICY backend_read   ON prediction_outcomes FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON prediction_outcomes FOR INSERT TO bitcoin_agent WITH CHECK (true);

-- the schema version: read only
GRANT SELECT ON schema_meta TO bitcoin_agent;
CREATE POLICY backend_read ON schema_meta FOR SELECT TO bitcoin_agent USING (true);

-- the shadow record: append, and write each row's outcome exactly once
GRANT SELECT, INSERT ON shadow_move_size, shadow_run_errors TO bitcoin_agent;
GRANT UPDATE (outcome_status, outcome_close, outcome_return, outcome_large, outcome_checked_at)
  ON shadow_move_size TO bitcoin_agent;
CREATE POLICY backend_read   ON shadow_move_size  FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON shadow_move_size  FOR INSERT TO bitcoin_agent WITH CHECK (true);
-- USING: only rows not yet graded may be touched. WITH CHECK (true): the graded result is allowed,
-- because without it the USING condition would be applied to the new row and refuse every grading.
CREATE POLICY backend_grade  ON shadow_move_size  FOR UPDATE TO bitcoin_agent
  USING (outcome_status IS NULL) WITH CHECK (true);
CREATE POLICY backend_read   ON shadow_run_errors FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert ON shadow_run_errors FOR INSERT TO bitcoin_agent WITH CHECK (true);

-- the published snapshot: one row, replaced every hour
GRANT SELECT, INSERT, UPDATE ON backend_state TO bitcoin_agent;
CREATE POLICY backend_read    ON backend_state FOR SELECT TO bitcoin_agent USING (true);
CREATE POLICY backend_insert  ON backend_state FOR INSERT TO bitcoin_agent WITH CHECK (true);
CREATE POLICY backend_replace ON backend_state FOR UPDATE TO bitcoin_agent USING (true) WITH CHECK (true);

-- the BIGSERIAL ids
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bitcoin_agent;
