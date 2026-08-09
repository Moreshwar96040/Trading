-- V18: major swing-support level on the screener snapshot, so "quality stock
-- coiled near support" is a filterable setup.
--
-- Written by the Python snapshot refresher. `support` is the most recent 5-bar
-- swing low, lagged so it's known without lookahead. `pct_from_support` is how
-- far price sits ABOVE it: a small positive value is the buy-the-dip zone, a
-- negative value means support has broken.

ALTER TABLE screener_snapshot
    ADD COLUMN support           NUMERIC(14, 4),
    ADD COLUMN pct_from_support  NUMERIC(10, 4);

CREATE INDEX idx_snapshot_support ON screener_snapshot (pct_from_support);
