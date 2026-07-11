-- V4: fundamental data (Phase 3). Written by the Python service, read by Spring.

CREATE TABLE fundamentals (
    symbol_id            BIGINT PRIMARY KEY REFERENCES symbols (id) ON DELETE CASCADE,
    market_cap           NUMERIC(22,2),
    pe_trailing          NUMERIC(12,4),
    pe_forward           NUMERIC(12,4),
    pb                   NUMERIC(12,4),
    ps                   NUMERIC(12,4),
    dividend_yield_pct   NUMERIC(8,4),
    roe_pct              NUMERIC(9,2),
    debt_to_equity       NUMERIC(10,4),
    profit_margin_pct    NUMERIC(8,2),
    operating_margin_pct NUMERIC(8,2),
    revenue_growth_pct   NUMERIC(9,2),
    earnings_growth_pct  NUMERIC(9,2),
    eps_trailing         NUMERIC(12,4),
    book_value           NUMERIC(14,4),
    beta                 NUMERIC(8,4),
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE financial_statements (
    id                   BIGSERIAL PRIMARY KEY,
    symbol_id            BIGINT NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    period_end           DATE NOT NULL,
    period_type          VARCHAR(10) NOT NULL,        -- ANNUAL | QUARTERLY
    revenue              NUMERIC(22,2),
    operating_income     NUMERIC(22,2),
    net_income           NUMERIC(22,2),
    eps                  NUMERIC(12,4),
    total_assets         NUMERIC(22,2),
    total_liabilities    NUMERIC(22,2),
    shareholders_equity  NUMERIC(22,2),
    operating_cash_flow  NUMERIC(22,2),
    free_cash_flow       NUMERIC(22,2),
    CONSTRAINT uq_fin_stmt UNIQUE (symbol_id, period_end, period_type)
);

CREATE INDEX idx_fin_stmt_symbol ON financial_statements (symbol_id, period_type, period_end DESC);

-- Denormalized ratios on the snapshot so the screener stays single-table.
ALTER TABLE screener_snapshot
    ADD COLUMN market_cap         NUMERIC(22,2),
    ADD COLUMN pe_trailing        NUMERIC(12,4),
    ADD COLUMN pb                 NUMERIC(12,4),
    ADD COLUMN dividend_yield_pct NUMERIC(8,4),
    ADD COLUMN roe_pct            NUMERIC(9,2),
    ADD COLUMN debt_to_equity     NUMERIC(10,4),
    ADD COLUMN profit_margin_pct  NUMERIC(8,2),
    ADD COLUMN revenue_growth_pct NUMERIC(9,2);
