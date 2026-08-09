-- V21: append-only indicator history — the foundation for point-in-time features.
--
-- WHY: `screener_snapshot` holds ONE row per symbol and is overwritten on every
-- refresh. That makes it impossible to ask "what did this stock look like on
-- 12 March?", which in turn makes every backtest of the composite conviction
-- score silently invalid — you'd be scoring today's indicators against
-- yesterday's prices.
--
-- WHY A SEPARATE TABLE rather than adding as_of_date to the snapshot's primary
-- key: the Spring backend maps `screener_snapshot` with `@Id symbolId`. Changing
-- that PK would require an @IdClass across the JPA entity, repository and
-- screener DSL. A current+history pair is the standard pattern, keeps Spring
-- untouched, and keeps "latest" reads as fast as they are now.
--
-- BACKFILLABLE: unlike news digests or regime, every column here is a pure
-- function of `ohlcv_daily`, so history CAN be reconstructed retroactively.
-- See `backfill_snapshot_history()`.

CREATE TABLE screener_snapshot_history (
    symbol_id          BIGINT NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    as_of_date         DATE   NOT NULL,

    close              NUMERIC(14, 4) NOT NULL,
    change_1d_pct      NUMERIC(10, 4),
    volume             BIGINT,
    avg_volume_20      NUMERIC(18, 2),
    volume_ratio       NUMERIC(10, 4),
    sma_20             NUMERIC(14, 4),
    sma_50             NUMERIC(14, 4),
    sma_200            NUMERIC(14, 4),
    ema_20             NUMERIC(14, 4),
    rsi_14             NUMERIC(10, 4),
    macd               NUMERIC(14, 6),
    macd_signal        NUMERIC(14, 6),
    macd_hist          NUMERIC(14, 6),
    bb_upper           NUMERIC(14, 4),
    bb_lower           NUMERIC(14, 4),
    atr_14             NUMERIC(14, 4),
    high_52w           NUMERIC(14, 4),
    low_52w            NUMERIC(14, 4),
    pct_from_52w_high  NUMERIC(10, 4),
    pct_from_52w_low   NUMERIC(10, 4),
    return_1m_pct      NUMERIC(10, 4),
    return_3m_pct      NUMERIC(10, 4),
    return_1y_pct      NUMERIC(10, 4),

    -- Ichimoku (V17) and swing support (V18) travel with the rest
    tenkan_9           NUMERIC(14, 4),
    kijun_26           NUMERIC(14, 4),
    cloud_top          NUMERIC(14, 4),
    cloud_bottom       NUMERIC(14, 4),
    tk_cross_age_days  NUMERIC(6, 0),
    pct_above_cloud    NUMERIC(10, 4),
    ichimoku_bullish   NUMERIC(1, 0),
    support            NUMERIC(14, 4),
    pct_from_support   NUMERIC(10, 4),

    -- provenance: LIVE = written by the daily refresh, BACKFILL = reconstructed
    source             VARCHAR(10) NOT NULL DEFAULT 'LIVE',
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (symbol_id, as_of_date)
);

-- point-in-time lookup: "this symbol, as it was on/just before this date"
CREATE INDEX idx_snapshot_hist_pit ON screener_snapshot_history (symbol_id, as_of_date DESC);
-- cross-sectional reads for a single date (regime breadth, ranking)
CREATE INDEX idx_snapshot_hist_date ON screener_snapshot_history (as_of_date);
