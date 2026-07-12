-- V10: close the loop — paper orders/positions know which strategy created them
-- and carry their risk plan (stop / target from the adaptive-risk engine).

ALTER TABLE paper_orders
    ADD COLUMN strategy_id  BIGINT REFERENCES strategies (id) ON DELETE SET NULL,
    ADD COLUMN stop_price   NUMERIC(14,4),
    ADD COLUMN target_price NUMERIC(14,4);

ALTER TABLE paper_positions
    ADD COLUMN strategy_id  BIGINT REFERENCES strategies (id) ON DELETE SET NULL,
    ADD COLUMN stop_price   NUMERIC(14,4),
    ADD COLUMN target_price NUMERIC(14,4);
