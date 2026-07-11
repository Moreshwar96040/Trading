-- V8: trade journal (Spring-owned) + AI predictions (Python-owned).

CREATE TABLE journal_entries (
    id             BIGSERIAL PRIMARY KEY,
    symbol_id      BIGINT REFERENCES symbols (id) ON DELETE SET NULL,
    paper_order_id BIGINT REFERENCES paper_orders (id) ON DELETE SET NULL,
    title          VARCHAR(160) NOT NULL,
    body           TEXT NOT NULL,
    tags           VARCHAR(300),                 -- comma-separated, lowercase
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_journal_created ON journal_entries (created_at DESC);

CREATE TABLE ai_predictions (
    symbol_id              BIGINT PRIMARY KEY REFERENCES symbols (id) ON DELETE CASCADE,
    as_of_date             DATE NOT NULL,           -- last bar used
    predicted_return_pct   NUMERIC(10,4) NOT NULL,  -- next trading day
    direction              VARCHAR(4) NOT NULL,     -- UP | DOWN | FLAT
    test_direction_accuracy NUMERIC(6,2),           -- % on chronological test split
    test_mae_pct           NUMERIC(10,4),
    train_rows             INTEGER,
    model_name             VARCHAR(60),
    trained_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
