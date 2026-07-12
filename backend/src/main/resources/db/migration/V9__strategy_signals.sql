-- V9: live strategy signals (Phase A of the trading loop).
-- Written by the Python service (it owns rule evaluation); read by Spring.

CREATE TABLE strategy_signals (
    id           BIGSERIAL PRIMARY KEY,
    strategy_id  BIGINT      NOT NULL REFERENCES strategies (id) ON DELETE CASCADE,
    symbol_id    BIGINT      NOT NULL REFERENCES symbols (id),
    signal       VARCHAR(8)  NOT NULL,          -- ENTRY | EXIT
    as_of_date   DATE        NOT NULL,          -- the bar the rules fired on
    close        NUMERIC(14,4),                 -- close on the signal bar (context for the UI)
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_strategy_signal UNIQUE (strategy_id, symbol_id, signal, as_of_date)
);

CREATE INDEX idx_signals_recent ON strategy_signals (as_of_date DESC, strategy_id);
