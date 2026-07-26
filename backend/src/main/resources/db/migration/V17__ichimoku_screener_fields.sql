-- V17: Ichimoku Kinko Hyo fields on the screener snapshot, so the "cloud
-- breakout with a Tenkan/Kijun cross" setup is filterable in the screener DSL.
--
-- Written by the Python snapshot refresher. The senkou spans are already shifted
-- forward when computed, so every value here is known at as_of_date (no lookahead).
--
-- tk_cross_age_days is NULL while Tenkan sits below Kijun (bearish) — a NULL age
-- is "no live bullish cross", which the DSL's comparisons correctly exclude.

ALTER TABLE screener_snapshot
    ADD COLUMN tenkan_9          NUMERIC(14, 4),   -- blue line (9-period midpoint)
    ADD COLUMN kijun_26          NUMERIC(14, 4),   -- red line (26-period midpoint)
    ADD COLUMN cloud_top         NUMERIC(14, 4),   -- max(senkou A, senkou B)
    ADD COLUMN cloud_bottom      NUMERIC(14, 4),   -- min(senkou A, senkou B)
    -- NUMERIC (not INTEGER) so every screener-filterable column shares one type:
    -- the DSL compares them all as BigDecimal via the Criteria API.
    ADD COLUMN tk_cross_age_days NUMERIC(6, 0),    -- bars since Tenkan crossed above Kijun
    ADD COLUMN pct_above_cloud   NUMERIC(10, 4),   -- % of price above the cloud top
    ADD COLUMN ichimoku_bullish  NUMERIC(1, 0);    -- 1 = Tenkan>Kijun and price above cloud

-- The screener's headline Ichimoku query: fresh cross, price clear of the cloud.
CREATE INDEX idx_snapshot_ichimoku
    ON screener_snapshot (ichimoku_bullish, tk_cross_age_days);
