-- V1: Core market-data schema.
-- Owned by Flyway (Spring Boot). The Python service mirrors these tables in
-- SQLAlchemy models but never runs DDL outside unit tests.

CREATE TABLE symbols (
    id            BIGSERIAL PRIMARY KEY,
    ticker        VARCHAR(20)  NOT NULL,              -- e.g. RELIANCE
    yahoo_symbol  VARCHAR(30)  NOT NULL,              -- e.g. RELIANCE.NS
    name          VARCHAR(120) NOT NULL,
    sector        VARCHAR(60),
    exchange      VARCHAR(10)  NOT NULL DEFAULT 'NSE',
    currency      VARCHAR(3)   NOT NULL DEFAULT 'INR',  -- VARCHAR (not CHAR): Hibernate ddl-auto=validate rejects bpchar vs String mapping
    active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_symbols_ticker_exchange UNIQUE (ticker, exchange)
);

CREATE INDEX idx_symbols_active ON symbols (active) WHERE active;

CREATE TABLE ohlcv_daily (
    id          BIGSERIAL PRIMARY KEY,
    symbol_id   BIGINT       NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    trade_date  DATE         NOT NULL,
    open        NUMERIC(14,4) NOT NULL CHECK (open  > 0),
    high        NUMERIC(14,4) NOT NULL CHECK (high  > 0),
    low         NUMERIC(14,4) NOT NULL CHECK (low   > 0),
    close       NUMERIC(14,4) NOT NULL CHECK (close > 0),
    adj_close   NUMERIC(14,4),
    volume      BIGINT       NOT NULL CHECK (volume >= 0),
    CONSTRAINT uq_ohlcv_symbol_date UNIQUE (symbol_id, trade_date),
    CONSTRAINT ck_ohlcv_high_low CHECK (high >= low)
);

CREATE INDEX idx_ohlcv_symbol_date ON ohlcv_daily (symbol_id, trade_date DESC);

CREATE TABLE sync_audit (
    id             BIGSERIAL PRIMARY KEY,
    run_type       VARCHAR(20)  NOT NULL,             -- CSV_IMPORT | DAILY_SYNC
    ticker         VARCHAR(20),                       -- NULL for multi-symbol runs
    started_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    status         VARCHAR(15)  NOT NULL,             -- RUNNING | SUCCESS | PARTIAL | FAILED
    rows_inserted  INTEGER      NOT NULL DEFAULT 0,
    rows_rejected  INTEGER      NOT NULL DEFAULT 0,
    message        TEXT
);

CREATE INDEX idx_sync_audit_started ON sync_audit (started_at DESC);
