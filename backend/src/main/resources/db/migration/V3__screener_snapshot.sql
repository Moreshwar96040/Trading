-- V3: one row per symbol with the latest computed indicator values.
-- Written (upserted) by the Python service after each daily sync; read by the
-- Spring screener via dynamic JPA Specifications.

CREATE TABLE screener_snapshot (
    symbol_id          BIGINT PRIMARY KEY REFERENCES symbols (id) ON DELETE CASCADE,
    as_of_date         DATE          NOT NULL,
    close              NUMERIC(14,4) NOT NULL,
    change_1d_pct      NUMERIC(10,4),
    volume             BIGINT,
    avg_volume_20      NUMERIC(18,2),
    volume_ratio       NUMERIC(10,4),          -- volume / avg_volume_20
    sma_20             NUMERIC(14,4),
    sma_50             NUMERIC(14,4),
    sma_200            NUMERIC(14,4),
    ema_20             NUMERIC(14,4),
    rsi_14             NUMERIC(7,4),
    macd               NUMERIC(14,6),
    macd_signal        NUMERIC(14,6),
    macd_hist          NUMERIC(14,6),
    bb_upper           NUMERIC(14,4),
    bb_lower           NUMERIC(14,4),
    atr_14             NUMERIC(14,4),
    high_52w           NUMERIC(14,4),
    low_52w            NUMERIC(14,4),
    pct_from_52w_high  NUMERIC(10,4),          -- negative = below the high
    pct_from_52w_low   NUMERIC(10,4),
    return_1m_pct      NUMERIC(10,4),
    return_3m_pct      NUMERIC(10,4),
    return_1y_pct      NUMERIC(10,4),
    computed_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_snapshot_as_of ON screener_snapshot (as_of_date);
