-- Diagnostics for the hourly dispatch (operational change 2, 2026-10-14).
--
-- Every hour at :12 Supabase's pg_cron asks GitHub to start the hourly workflow (net.http_post;
-- docs/ops/supabase_dispatch.sql). pg_net keeps GitHub's answer in net._http_response for only six
-- hours (pg_net.ttl), so when an hour went missing on 2026-10-07 the one fact that would have told
-- "GitHub refused or never answered" apart from "GitHub accepted and then ran nothing" was already
-- gone. This table keeps that fact, and nothing more:
--   kept:    pg_net's response id and time, the HTTP status, pg_net's timed-out flag and error text,
--            GitHub's request id (x-github-request-id, what GitHub support asks for), and -- only for an
--            answer that is not 2xx -- the first 300 characters of GitHub's error message;
--   never:   any header except the request id, the request (its Authorization header holds the token),
--            or a successful answer's body. Free text passes through dispatch_redact() before it is kept.
-- Kept 90 days, then deleted by the recorder itself.
--
-- Written ONLY by record_dispatch_responses(), which its own pg_cron job runs at :47 each hour
-- (docs/ops/dispatch_responses_cron.sql) -- a separate job and transaction from the dispatch, so a
-- failure here can never stop a dispatch, and nothing on the hourly job's path reads or writes it.
-- A missed recorder run loses nothing: the next one, within pg_net's six hours, copies what is there.
-- Owner-only: Row Level Security on with no policies, the public API roles revoked, the functions not
-- executable by PUBLIC, and nothing granted to the job role `bitcoin_agent`.
-- No sequence (the id is pg_net's), so the job role's sequence grant does not reach it.
-- Assumes pg_net is used by the dispatch alone (true since 2026-09-20: response ids track the dispatch
-- runs one for one). If anything else ever uses pg_net, revisit this file.

CREATE TABLE IF NOT EXISTS dispatch_responses (
    response_id BIGINT NOT NULL,                     -- net._http_response.id (pg_net's request id)
    responded_at TIMESTAMPTZ NOT NULL,               -- when pg_net stored the answer (or its failure)
    status_code INTEGER,                             -- 204 = GitHub accepted the dispatch; NULL = no HTTP answer
    timed_out BOOLEAN,
    error_msg TEXT CHECK (length(error_msg) <= 500),             -- pg_net's own error, redacted
    github_request_id TEXT CHECK (length(github_request_id) <= 100),
    detail TEXT CHECK (length(detail) <= 300),                   -- GitHub's error message, non-2xx only, redacted
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- pg_net's ids restart if the extension is ever reinstalled; the time keeps two answers apart
    PRIMARY KEY (response_id, responded_at)
);

CREATE INDEX IF NOT EXISTS idx_dispatch_responses_responded_at ON dispatch_responses (responded_at);

-- Removes anything token-shaped from free text: GitHub token prefixes, a bearer/token value, and an
-- Authorization value. Runs before truncation, so a cut can never leave half a token behind.
CREATE OR REPLACE FUNCTION dispatch_redact(t text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT regexp_replace(regexp_replace(regexp_replace(t,
        '(gh[pousr]_|github_pat_)[A-Za-z0-9_]+', '[redacted]', 'g'),
        '([Bb]earer|[Tt]oken)\s+[A-Za-z0-9._~+/=-]+', '\1 [redacted]', 'g'),
        '([Aa]uthorization"?\s*[:=]\s*)[^\n,}]*', '\1[redacted]', 'g')
$$;

-- Copies every answer pg_net still holds (idempotent), then applies the 90-day retention.
-- Returns how many new answers it kept. Deliberately unqualified names: it acts in the schema it is
-- called from, so a test's scratch schema never reaches `public`.
CREATE OR REPLACE FUNCTION record_dispatch_responses() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
    copied integer;
BEGIN
    INSERT INTO dispatch_responses (response_id, responded_at, status_code, timed_out, error_msg, github_request_id, detail)
    SELECT r.id, r.created, r.status_code, r.timed_out,
           left(dispatch_redact(r.error_msg), 500),
           left(r.headers ->> 'x-github-request-id', 100),
           CASE WHEN r.status_code BETWEEN 200 AND 299 THEN NULL ELSE left(dispatch_redact(r.content), 300) END
    FROM net._http_response r
    ON CONFLICT (response_id, responded_at) DO NOTHING;
    GET DIAGNOSTICS copied = ROW_COUNT;
    DELETE FROM dispatch_responses WHERE responded_at < now() - interval '90 days';
    RETURN copied;
END $$;

-- Access lockdown: owner-only, the same two layers as every other table (RLS with no policy, and the
-- public API roles revoked). Postgres also gives every new function EXECUTE to PUBLIC, which `anon`
-- inherits, so that is revoked explicitly (the security check fails on any function the API could call).
DO $$
DECLARE
    r text;
BEGIN
    ALTER TABLE dispatch_responses ENABLE ROW LEVEL SECURITY;
    REVOKE ALL ON FUNCTION record_dispatch_responses() FROM PUBLIC;
    REVOKE ALL ON FUNCTION dispatch_redact(text) FROM PUBLIC;
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON TABLE dispatch_responses FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION record_dispatch_responses() FROM %I', r);
            EXECUTE format('REVOKE ALL ON FUNCTION dispatch_redact(text) FROM %I', r);
        END IF;
    END LOOP;
END $$;
