-- V14: intraday OHLCV bars (Python-owned). Yahoo provides ~60 days of 15-minute
-- history for free — enough to trade intraday setups, honestly too little for
-- robust backtests (the UI says so).

CREATE TABLE ohlcv_intraday (
    id        BIGSERIAL PRIMARY KEY,
    symbol_id BIGINT NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    interval  VARCHAR(5) NOT NULL DEFAULT '15m',
    ts        TIMESTAMPTZ NOT NULL,
    open      NUMERIC(14,4) NOT NULL,
    high      NUMERIC(14,4) NOT NULL,
    low       NUMERIC(14,4) NOT NULL,
    close     NUMERIC(14,4) NOT NULL,
    volume    BIGINT NOT NULL,
    CONSTRAINT uq_intraday_bar UNIQUE (symbol_id, interval, ts)
);

CREATE INDEX idx_intraday_symbol_ts ON ohlcv_intraday (symbol_id, interval, ts DESC);
