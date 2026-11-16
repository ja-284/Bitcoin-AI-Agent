-- Markedskontekst for retningsforskningen (research/RETNINGSPLAN_2026-11-16.md, kandidat B; eierens ja 2026-11-16):
-- terminmarked (belåning, funding, likvidasjoner), opsjoner (frykt) og ordrebok, samlet framover fra seks gratis kilder.
-- Egne tabeller, bare tillegg; ingenting her kan leses utenfra. Bare `python -m agent.migrate` bruker denne filen.

CREATE TABLE IF NOT EXISTS context_hourly (
    id BIGSERIAL PRIMARY KEY,
    hour TIMESTAMPTZ NOT NULL CHECK (hour = date_trunc('hour', hour)),   -- klokketimen da raden ble hentet
    source TEXT NOT NULL CHECK (source IN ('okx', 'deribit', 'kraken', 'hyperliquid', 'bitfinex', 'binance_book')),
    fetched_at TIMESTAMPTZ NOT NULL,              -- punkt i tid: raden kan bare brukes for prediksjoner med grense etter dette
    code_commit TEXT CHECK (length(code_commit) <= 64),
    data JSONB NOT NULL CHECK (octet_length(data::text) <= 8000),  -- et kort sammendrag, aldri hele svaret
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (fetched_at >= hour AND fetched_at < hour + interval '2 hours'),  -- en kjøring kan krysse timeskiftet
    UNIQUE (hour, source)
);

CREATE TABLE IF NOT EXISTS context_errors (
    id BIGSERIAL PRIMARY KEY,
    hour TIMESTAMPTZ NOT NULL CHECK (hour = date_trunc('hour', hour)),
    source TEXT NOT NULL CHECK (length(source) <= 32),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_type TEXT NOT NULL CHECK (length(error_type) <= 200),
    error_message TEXT NOT NULL CHECK (length(error_message) <= 2000),
    code_commit TEXT CHECK (length(code_commit) <= 64),
    UNIQUE (hour, source)                         -- én feilrad per kilde og time; neste kjøring prøver igjen
);

-- Bare tillegg: ingen rad kan endres eller slettes, heller ikke av eieren uten å fjerne triggeren først.
CREATE OR REPLACE FUNCTION context_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (research/RETNINGSPLAN_2026-11-16.md)', TG_TABLE_NAME;
END $$;
DROP TRIGGER IF EXISTS context_hourly_append_only ON context_hourly;
CREATE TRIGGER context_hourly_append_only BEFORE UPDATE OR DELETE ON context_hourly FOR EACH ROW EXECUTE FUNCTION context_forbid_change();
DROP TRIGGER IF EXISTS context_errors_append_only ON context_errors;
CREATE TRIGGER context_errors_append_only BEFORE UPDATE OR DELETE ON context_errors FOR EACH ROW EXECUTE FUNCTION context_forbid_change();

-- Access lockdown (the same two layers as every other schema file): RLS on with no policy for the API roles,
-- and every privilege of the API roles revoked.
DO $$
DECLARE
    t text;
    r text;
    s text;
BEGIN
    FOREACH t IN ARRAY ARRAY['context_hourly', 'context_errors'] LOOP
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
