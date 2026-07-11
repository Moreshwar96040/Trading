-- V7: risk settings (Spring-owned) + alerts (definition: Spring; lifecycle: Python).

CREATE TABLE risk_settings (
    id                  BIGINT PRIMARY KEY,
    max_position_pct    NUMERIC(6,2) NOT NULL,   -- max single-position % of equity
    max_sector_pct      NUMERIC(6,2) NOT NULL,   -- max sector % of equity (report only)
    risk_per_trade_pct  NUMERIC(6,2) NOT NULL,   -- % of equity risked between entry and stop
    block_on_breach     BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

INSERT INTO risk_settings (id, max_position_pct, max_sector_pct, risk_per_trade_pct)
VALUES (1, 20.00, 40.00, 1.00);

CREATE TABLE alerts (
    id               BIGSERIAL PRIMARY KEY,
    symbol_id        BIGINT NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    field            VARCHAR(30)  NOT NULL,      -- screener-snapshot field name
    op               VARCHAR(5)   NOT NULL,      -- gt|gte|lt|lte|eq
    value            NUMERIC(18,4) NOT NULL,
    note             VARCHAR(200),
    status           VARCHAR(10)  NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE | TRIGGERED | DISABLED
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    triggered_at     TIMESTAMPTZ,
    triggered_value  NUMERIC(18,4)
);

CREATE INDEX idx_alerts_status ON alerts (status);
