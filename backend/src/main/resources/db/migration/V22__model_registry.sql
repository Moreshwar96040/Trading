-- V22: model registry — every artefact that affects a decision is versioned.
--
-- WHY: the moment you apply a learned weight suggestion, all prior attribution
-- becomes uninterpretable. You can no longer tell whether performance changed
-- because the market changed or because you changed the model. Stamping a
-- version id on every score and every trade is what keeps that answerable.
--
-- Status lifecycle:
--   SHADOW    scored alongside the champion, never traded
--   CHAMPION  the live model — exactly one per kind, enforced by a partial index
--   RETIRED   immutable history

CREATE TABLE model_versions (
    id           BIGSERIAL PRIMARY KEY,
    kind         VARCHAR(30) NOT NULL,          -- WEIGHTS | ML | THRESHOLDS
    label        VARCHAR(80) NOT NULL,
    params_json  JSONB       NOT NULL,          -- e.g. the seven layer weights
    metrics_json JSONB,                         -- OOS IC, turnover, stability
    status       VARCHAR(10) NOT NULL DEFAULT 'SHADOW',
    parent_id    BIGINT REFERENCES model_versions (id),
    notes        VARCHAR(500),
    created_by   VARCHAR(60) NOT NULL DEFAULT 'system',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_at  TIMESTAMPTZ,
    promoted_by  VARCHAR(60),
    CONSTRAINT ck_model_status CHECK (status IN ('SHADOW', 'CHAMPION', 'RETIRED'))
);

-- Exactly one champion per kind — enforced by the database, not by convention.
CREATE UNIQUE INDEX uq_model_champion ON model_versions (kind)
    WHERE status = 'CHAMPION';

CREATE INDEX idx_model_kind_status ON model_versions (kind, status);

-- Audit trail: every status change, who and when. Append-only by intent.
CREATE TABLE model_version_audit (
    id          BIGSERIAL PRIMARY KEY,
    version_id  BIGINT      NOT NULL REFERENCES model_versions (id) ON DELETE CASCADE,
    from_status VARCHAR(10),
    to_status   VARCHAR(10) NOT NULL,
    actor       VARCHAR(60) NOT NULL,
    reason      VARCHAR(300),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Trace every recorded score and every autopilot trade to the model behind it.
ALTER TABLE conviction_history ADD COLUMN model_version_id BIGINT
    REFERENCES model_versions (id);
ALTER TABLE autopilot_trades   ADD COLUMN model_version_id BIGINT
    REFERENCES model_versions (id);

-- Seed the currently hardcoded weights as the first champion, then backfill
-- existing rows to it: without this, history would look like it had no model.
INSERT INTO model_versions (kind, label, params_json, status, notes, created_by,
                            promoted_at, promoted_by)
VALUES ('WEIGHTS', 'baseline-v1',
        '{"technical":25,"quality":25,"news":18,"momentum":14,"ml":7,"macro":6,"regime":5}',
        'CHAMPION',
        'The original hand-set weights. A reasonable prior, never validated — this row exists so everything scored before the registry is still attributable.',
        'migration', now(), 'migration');

UPDATE conviction_history
   SET model_version_id = (SELECT id FROM model_versions WHERE label = 'baseline-v1')
 WHERE model_version_id IS NULL;

UPDATE autopilot_trades
   SET model_version_id = (SELECT id FROM model_versions WHERE label = 'baseline-v1')
 WHERE model_version_id IS NULL;
