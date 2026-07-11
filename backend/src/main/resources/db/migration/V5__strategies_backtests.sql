-- V5: strategy definitions (written by Spring) and backtest results (written by Python).

CREATE TABLE strategies (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(80)  NOT NULL UNIQUE,
    description VARCHAR(500),
    definition  JSONB        NOT NULL,      -- {entry:[...], exit:[...], stop_loss_pct, take_profit_pct, max_holding_days}
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE backtests (
    id            BIGSERIAL PRIMARY KEY,
    strategy_id   BIGINT NOT NULL REFERENCES strategies (id) ON DELETE CASCADE,
    params        JSONB  NOT NULL,          -- {tickers, from, to, initial_capital, max_positions, commission_pct}
    status        VARCHAR(15) NOT NULL,     -- RUNNING | SUCCESS | FAILED
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    metrics       JSONB,                    -- {total_return_pct, cagr_pct, max_drawdown_pct, sharpe, win_rate_pct, ...}
    equity_curve  JSONB,                    -- [{"d":"2026-01-01","v":1000000}, ...]
    error         TEXT
);

CREATE INDEX idx_backtests_strategy ON backtests (strategy_id, started_at DESC);

CREATE TABLE backtest_trades (
    id           BIGSERIAL PRIMARY KEY,
    backtest_id  BIGINT NOT NULL REFERENCES backtests (id) ON DELETE CASCADE,
    ticker       VARCHAR(20) NOT NULL,
    entry_date   DATE NOT NULL,
    entry_price  NUMERIC(14,4) NOT NULL,
    exit_date    DATE,
    exit_price   NUMERIC(14,4),
    quantity     INTEGER NOT NULL,
    pnl          NUMERIC(16,2),
    pnl_pct      NUMERIC(10,4),
    exit_reason  VARCHAR(20)               -- SIGNAL | STOP_LOSS | TAKE_PROFIT | MAX_DAYS | END_OF_DATA
);

CREATE INDEX idx_bt_trades_backtest ON backtest_trades (backtest_id);
