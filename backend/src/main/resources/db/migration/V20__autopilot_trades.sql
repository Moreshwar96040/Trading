-- V20: autopilot trade attribution (Python-owned).
--
-- The conviction_history table (V19) answers "was the score predictive?" using
-- hypothetical forward returns. This table answers the harder question: "did the
-- whole system make money?" — because a real trade also involves position size,
-- a stop, an exit and a capital limit, any of which can turn a predictive signal
-- into a losing strategy.
--
-- One row per autopilot entry, carrying a COPY of the conviction and layer
-- strengths that justified it. Denormalised deliberately: the attribution must
-- survive even if the conviction_history row is pruned, and we want to compare
-- realised P&L by the score AS IT WAS at entry.
--
-- Paper only. The Spring backend remains the sole writer of paper_orders and
-- paper_positions; the autopilot is a *client* of that API, and this table is
-- its own bookkeeping.

CREATE TABLE autopilot_trades (
    id              BIGSERIAL PRIMARY KEY,
    symbol_id       BIGINT      NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    ticker          VARCHAR(20) NOT NULL,

    -- entry
    entry_date      DATE          NOT NULL,
    entry_price     NUMERIC(14, 4),
    quantity        INTEGER       NOT NULL,
    stop_price      NUMERIC(14, 4),
    target_price    NUMERIC(14, 4),
    paper_order_id  BIGINT,                       -- id returned by the Spring API

    -- the thesis at entry (attribution)
    conviction          NUMERIC(6, 2) NOT NULL,
    verdict             VARCHAR(16),
    risk_multiplier     NUMERIC(6, 3),
    technical_strength  NUMERIC(6, 4),
    quality_strength    NUMERIC(6, 4),
    news_strength       NUMERIC(6, 4),
    momentum_strength   NUMERIC(6, 4),
    ml_strength         NUMERIC(6, 4),
    macro_strength      NUMERIC(6, 4),
    regime_strength     NUMERIC(6, 4),
    regime_code         VARCHAR(16),
    sector              VARCHAR(60),

    -- outcome (filled when the position closes)
    status          VARCHAR(10)   NOT NULL DEFAULT 'OPEN',   -- OPEN | CLOSED
    exit_date       DATE,
    exit_price      NUMERIC(14, 4),
    realized_pnl    NUMERIC(16, 2),
    return_pct      NUMERIC(10, 4),
    hold_days       INTEGER,
    exit_reason     VARCHAR(40),

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_autopilot_open UNIQUE (symbol_id, entry_date)
);

CREATE INDEX idx_autopilot_open ON autopilot_trades (status, symbol_id);
CREATE INDEX idx_autopilot_closed ON autopilot_trades (status, conviction);
