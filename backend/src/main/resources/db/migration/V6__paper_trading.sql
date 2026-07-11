-- V6: paper trading (Phase 5). Written by the Spring backend (pure domain logic).

CREATE TABLE paper_accounts (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(60)   NOT NULL,
    initial_cash  NUMERIC(16,2) NOT NULL,
    cash          NUMERIC(16,2) NOT NULL,
    realized_pnl  NUMERIC(16,2) NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE paper_positions (
    id          BIGSERIAL PRIMARY KEY,
    account_id  BIGINT NOT NULL REFERENCES paper_accounts (id) ON DELETE CASCADE,
    symbol_id   BIGINT NOT NULL REFERENCES symbols (id),
    quantity    INTEGER NOT NULL CHECK (quantity >= 0),
    avg_cost    NUMERIC(14,4) NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_position UNIQUE (account_id, symbol_id)
);

CREATE TABLE paper_orders (
    id            BIGSERIAL PRIMARY KEY,
    account_id    BIGINT NOT NULL REFERENCES paper_accounts (id) ON DELETE CASCADE,
    symbol_id     BIGINT NOT NULL REFERENCES symbols (id),
    side          VARCHAR(4)  NOT NULL,          -- BUY | SELL
    quantity      INTEGER     NOT NULL CHECK (quantity > 0),
    price         NUMERIC(14,4),                 -- fill price (NULL when rejected)
    price_source  VARCHAR(10),                   -- QUOTE | CLOSE
    commission    NUMERIC(12,2),
    realized_pnl  NUMERIC(16,2),                 -- set on SELL fills
    status        VARCHAR(10) NOT NULL,          -- FILLED | REJECTED
    reject_reason VARCHAR(200),
    placed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_paper_orders_account ON paper_orders (account_id, placed_at DESC);

-- One default account for the single-user phase.
INSERT INTO paper_accounts (name, initial_cash, cash)
VALUES ('Default', 1000000.00, 1000000.00);
