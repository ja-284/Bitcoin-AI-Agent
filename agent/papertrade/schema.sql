-- Papirhandel framover (E042, research/experiments/E042_paper_trading.json). Egne tabeller: papirhandelen skriver
-- aldri i prediksjonstabellene, skyggesporene eller noe annet. Ingen ekte penger. Bare `python -m agent.migrate`
-- bruker denne filen; timesjobben kjører ingen DDL.

CREATE TABLE IF NOT EXISTS paper_days (
    day DATE PRIMARY KEY,                        -- UTC-dagen beslutningen gjelder (sluttkursen = 23:00-timens close)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    strategy_set TEXT NOT NULL CHECK (length(strategy_set) <= 32),
    code_commit TEXT CHECK (length(code_commit) <= 64),
    close DOUBLE PRECISION NOT NULL CHECK (close > 0),
    firi_bid DOUBLE PRECISION CHECK (firi_bid > 0),
    firi_ask DOUBLE PRECISION CHECK (firi_ask > 0),
    firi_fetched_at TIMESTAMPTZ,
    inputs JSONB NOT NULL,                       -- dagens inndata (signal, snitt, pbar, sigma30 osv.)
    strategies INTEGER NOT NULL CHECK (strategies > 0),
    CHECK ((firi_bid IS NULL) = (firi_ask IS NULL)),
    CHECK ((firi_bid IS NULL) = (firi_fetched_at IS NULL)),
    CHECK (firi_bid IS NULL OR firi_bid <= firi_ask)
);

CREATE TABLE IF NOT EXISTS paper_ledger (
    id BIGSERIAL PRIMARY KEY,
    day DATE NOT NULL REFERENCES paper_days (day),
    strategy TEXT NOT NULL CHECK (length(strategy) <= 64),
    book TEXT NOT NULL CHECK (book IN ('modell', 'firi')),
    active BOOLEAN NOT NULL,                     -- har strategien alle inndata den trenger denne dagen
    desired DOUBLE PRECISION,                    -- 1 eie, 0 kontanter, NULL behold
    size DOUBLE PRECISION CHECK (size IS NULL OR (size >= 0 AND size <= 1)),
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL', 'NONE')),
    notional DOUBLE PRECISION NOT NULL CHECK (notional >= 0),
    fee DOUBLE PRECISION NOT NULL CHECK (fee >= 0),
    cash DOUBLE PRECISION NOT NULL CHECK (cash >= -1e-9),
    btc DOUBLE PRECISION NOT NULL CHECK (btc >= 0),
    value DOUBLE PRECISION NOT NULL CHECK (value >= 0),
    state JSONB NOT NULL,                        -- motorens tilstand etter steget (nok til å fortsette i morgen)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (day, strategy, book)
);
CREATE INDEX IF NOT EXISTS idx_paper_ledger_strategy ON paper_ledger (strategy, book, day);

CREATE TABLE IF NOT EXISTS paper_errors (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    day DATE,
    step TEXT NOT NULL CHECK (length(step) <= 32),
    error_type TEXT NOT NULL CHECK (length(error_type) <= 200),
    error_message TEXT NOT NULL CHECK (length(error_message) <= 2000),
    code_commit TEXT CHECK (length(code_commit) <= 64)
);

-- (2026-11-16, E042 tillegg 1) hvorfor hver handel skjedde
ALTER TABLE paper_ledger ADD COLUMN IF NOT EXISTS reason TEXT
    CHECK (reason IS NULL OR reason IN ('signal', 'stop_loss', 'trailing_stop', 'time_stop', 'rebalance'));

-- (2026-11-16, E042 tillegg 1) Firis marked hver time: beste kjøps- og salgskurs, mengden der, hva 500 kr koster
-- gjennom ordreboken, og hvor mye som ligger innenfor 1 % av midtkursen. Én rad per time (reserveslottene legger ikke til).
CREATE TABLE IF NOT EXISTS firi_quotes (
    id BIGSERIAL PRIMARY KEY,
    hour TIMESTAMPTZ NOT NULL UNIQUE,
    fetched_at TIMESTAMPTZ NOT NULL,
    bid DOUBLE PRECISION NOT NULL CHECK (bid > 0),
    ask DOUBLE PRECISION NOT NULL CHECK (ask > 0),
    bid_qty DOUBLE PRECISION CHECK (bid_qty >= 0),
    ask_qty DOUBLE PRECISION CHECK (ask_qty >= 0),
    buy_500_avg DOUBLE PRECISION CHECK (buy_500_avg > 0),   -- snittkurs for et kjøp på 500 kr gjennom bøkene
    sell_500_avg DOUBLE PRECISION CHECK (sell_500_avg > 0), -- snittkurs for et salg verdt 500 kr
    depth_bid_nok DOUBLE PRECISION CHECK (depth_bid_nok >= 0),  -- kroner på kjøpssiden innenfor 1 % av midtkursen
    depth_ask_nok DOUBLE PRECISION CHECK (depth_ask_nok >= 0),
    CHECK (bid <= ask),
    CHECK (hour = date_trunc('hour', hour))
);

-- (2026-11-16, E042 tillegg 1) Firis offentlige handler, slik at tålmodige ordrer (kjøp på kjøpskursen) kan regnes ut
-- i ettertid. Firi gir ingen handels-id, så en handel kjennes igjen på tid, side, kurs, mengde og et løpenummer n for
-- helt like handler (3 av 1000 var like 2026-11-16). «type» bid = kjøperen tok initiativet (handlet på ask), ask = selgeren.
CREATE TABLE IF NOT EXISTS firi_trades (
    id BIGSERIAL PRIMARY KEY,
    traded_at TIMESTAMPTZ NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('bid', 'ask')),      -- Firis «type»: hvilken side som tok initiativet
    price DOUBLE PRECISION NOT NULL CHECK (price > 0),
    amount DOUBLE PRECISION NOT NULL CHECK (amount > 0),
    n SMALLINT NOT NULL DEFAULT 1 CHECK (n >= 1),
    total DOUBLE PRECISION NOT NULL CHECK (total >= 0),
    fetched_at TIMESTAMPTZ NOT NULL,
    UNIQUE (traded_at, side, price, amount, n)
);
CREATE INDEX IF NOT EXISTS idx_firi_trades_time ON firi_trades (traded_at);

-- Bare tillegg: ingen rad kan endres eller slettes, heller ikke av eieren uten å fjerne triggeren først.
CREATE OR REPLACE FUNCTION paper_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP;
END $$;
DROP TRIGGER IF EXISTS paper_days_append_only ON paper_days;
CREATE TRIGGER paper_days_append_only BEFORE UPDATE OR DELETE ON paper_days FOR EACH ROW EXECUTE FUNCTION paper_forbid_change();
DROP TRIGGER IF EXISTS paper_ledger_append_only ON paper_ledger;
CREATE TRIGGER paper_ledger_append_only BEFORE UPDATE OR DELETE ON paper_ledger FOR EACH ROW EXECUTE FUNCTION paper_forbid_change();
DROP TRIGGER IF EXISTS paper_errors_append_only ON paper_errors;
CREATE TRIGGER paper_errors_append_only BEFORE UPDATE OR DELETE ON paper_errors FOR EACH ROW EXECUTE FUNCTION paper_forbid_change();
DROP TRIGGER IF EXISTS firi_quotes_append_only ON firi_quotes;
CREATE TRIGGER firi_quotes_append_only BEFORE UPDATE OR DELETE ON firi_quotes FOR EACH ROW EXECUTE FUNCTION paper_forbid_change();
DROP TRIGGER IF EXISTS firi_trades_append_only ON firi_trades;
CREATE TRIGGER firi_trades_append_only BEFORE UPDATE OR DELETE ON firi_trades FOR EACH ROW EXECUTE FUNCTION paper_forbid_change();

-- Access lockdown (the same two layers as every other schema file): RLS on with no policy for the API roles,
-- and every privilege of the API roles revoked.
DO $$
DECLARE
    t text;
    r text;
    s text;
BEGIN
    FOREACH t IN ARRAY ARRAY['paper_days', 'paper_ledger', 'paper_errors', 'firi_quotes', 'firi_trades'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format('REVOKE ALL ON TABLE %I FROM %I', t, r);
                -- paper_days has no id column (its key is the day), so only tables with one have a sequence
                IF EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_schema = current_schema() AND table_name = t AND column_name = 'id') THEN
                    s := pg_get_serial_sequence(t, 'id');
                    IF s IS NOT NULL THEN
                        EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM %I', s, r);
                    END IF;
                END IF;
            END IF;
        END LOOP;
    END LOOP;
END $$;
