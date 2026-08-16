-- V23: autonomous, regime-conditional weight adaptation.
--
-- Two changes, each closing a specific hole.
--
-- 1. SCOPE. Until now there was exactly one champion, so the weights could not
--    respond to market conditions at all — regime affected the *inputs* to the
--    score but never the weights themselves. A scope column lets each regime
--    bucket carry its own champion, with the global set as fallback. Buckets
--    are risk_on / neutral / risk_off: three, not five, because seven weights
--    across five regimes divides thin data five ways to fit 35 parameters.
--
-- 2. ANCHORING. Once the learner may promote itself, "how far has it drifted?"
--    must be measured against the last HUMAN-approved set, not against the
--    incumbent. Measuring against the incumbent lets drift ratchet: ten points
--    per promotion, indefinitely, each step individually within bounds. The
--    is_anchor flag marks the sets a person actually sanctioned.

-- Scope: NULL/'global' is the fallback used when a regime has no champion.
ALTER TABLE model_versions ADD COLUMN scope VARCHAR(16) NOT NULL DEFAULT 'global';

ALTER TABLE model_versions ADD CONSTRAINT ck_model_scope
    CHECK (scope IN ('global', 'risk_on', 'neutral', 'risk_off'));

-- A human-approved set. Drift is always measured from the most recent one of
-- these, which is what stops small automatic steps accumulating into a large
-- unreviewed change.
ALTER TABLE model_versions ADD COLUMN is_anchor BOOLEAN NOT NULL DEFAULT FALSE;

-- The single-champion rule now applies per (kind, scope), not per kind.
DROP INDEX IF EXISTS uq_model_champion;
CREATE UNIQUE INDEX uq_model_champion ON model_versions (kind, scope)
    WHERE status = 'CHAMPION';

CREATE INDEX idx_model_scope_status ON model_versions (kind, scope, status);
CREATE INDEX idx_model_anchor ON model_versions (kind, scope, is_anchor)
    WHERE is_anchor;

-- The seeded baseline is the founding human decision, so it is the first anchor.
UPDATE model_versions
   SET is_anchor = TRUE, scope = 'global'
 WHERE label = 'baseline-v1';

-- Record of every automatic adaptation: what changed, why it was allowed, and
-- what it was measured against. Separate from model_version_audit, which records
-- status transitions; this records the *reasoning*.
CREATE TABLE adaptation_events (
    id             BIGSERIAL PRIMARY KEY,
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    scope          VARCHAR(16) NOT NULL,
    action         VARCHAR(24) NOT NULL,   -- PROMOTED | REJECTED | ROLLED_BACK | SKIPPED
    version_id     BIGINT REFERENCES model_versions (id),
    anchor_id      BIGINT REFERENCES model_versions (id),
    samples        INTEGER,
    oos_ic         NUMERIC(10, 4),
    champion_ic    NUMERIC(10, 4),
    max_drift      NUMERIC(10, 4),
    gates_json     JSONB,                  -- every gate verdict, pass or fail
    weights_json   JSONB,
    reason         VARCHAR(500) NOT NULL,
    triggered_by   VARCHAR(60) NOT NULL DEFAULT 'learner'
);

CREATE INDEX idx_adaptation_occurred ON adaptation_events (occurred_at DESC);
CREATE INDEX idx_adaptation_scope ON adaptation_events (scope, occurred_at DESC);
