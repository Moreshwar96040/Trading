-- V13: per-call AI usage log (Python-owned) so the app can show exactly what
-- the LLM insights cost — no trips to the provider console needed.

CREATE TABLE ai_usage (
    id            BIGSERIAL PRIMARY KEY,
    kind          VARCHAR(20) NOT NULL,        -- NEWS | FUNDAMENTALS | REVIEW | ...
    model         VARCHAR(60) NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd      NUMERIC(10, 6) NOT NULL,     -- computed at call time from configured prices
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_usage_created ON ai_usage (created_at DESC);
