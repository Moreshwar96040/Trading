-- V19: conviction history — the training set for adaptive weighting.
--
-- The Alpha Stack's weights (technical 25, quality 25, news 18, momentum 14,
-- ml 7, macro 6, regime 5) are an asserted prior that has never been checked
-- against outcomes. This table records what was scored, so forward returns can
-- later tell us which layers actually predicted anything.
--
-- Written daily by the Python recorder for EVERY active symbol, not only the
-- ones with a live signal: scoring only signalled names leaves the technical
-- layer with almost no variance, and you cannot learn the weight of a feature
-- that never changes. Recording non-signal (posture) setups too is what makes
-- the regression identifiable.
--
-- Labels (fwd_return_*) are filled in later by the labeller once enough bars
-- have passed. NULL label = not matured yet.

CREATE TABLE conviction_history (
    symbol_id            BIGINT NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    as_of_date           DATE   NOT NULL,

    -- the decision that was made
    conviction           NUMERIC(6, 2) NOT NULL,
    verdict              VARCHAR(16)   NOT NULL,
    risk_multiplier      NUMERIC(6, 3),
    news_veto            BOOLEAN       NOT NULL DEFAULT FALSE,
    has_live_signal      BOOLEAN       NOT NULL DEFAULT FALSE,

    -- the features: each layer's 0..1 strength at scoring time
    technical_strength   NUMERIC(6, 4),
    quality_strength     NUMERIC(6, 4),
    news_strength        NUMERIC(6, 4),
    momentum_strength    NUMERIC(6, 4),
    ml_strength          NUMERIC(6, 4),
    macro_strength       NUMERIC(6, 4),
    regime_strength      NUMERIC(6, 4),

    -- controls / slicing
    regime_code          VARCHAR(16),
    sector               VARCHAR(60),
    atr_pct              NUMERIC(10, 4),
    data_quality         NUMERIC(6, 3),
    close                NUMERIC(14, 4),

    -- labels, filled once matured (NULL until then)
    fwd_return_5d        NUMERIC(10, 4),
    fwd_return_10d       NUMERIC(10, 4),
    fwd_return_20d       NUMERIC(10, 4),
    mfe_pct              NUMERIC(10, 4),   -- best excursion within 10 bars
    mae_pct              NUMERIC(10, 4),   -- worst excursion within 10 bars
    labelled_at          TIMESTAMPTZ,

    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol_id, as_of_date)
);

-- the labeller scans for matured-but-unlabelled rows
CREATE INDEX idx_conviction_unlabelled ON conviction_history (as_of_date)
    WHERE fwd_return_10d IS NULL;

-- calibration reads labelled rows in date order (walk-forward folds)
CREATE INDEX idx_conviction_labelled ON conviction_history (as_of_date, conviction)
    WHERE fwd_return_10d IS NOT NULL;
