-- V11: news articles (Python-owned) + cached AI insights (Python-owned).

CREATE TABLE news_articles (
    id           BIGSERIAL PRIMARY KEY,
    symbol_id    BIGINT NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    external_id  VARCHAR(80) NOT NULL,          -- provider uuid (dedup key)
    title        VARCHAR(500) NOT NULL,
    publisher    VARCHAR(120),
    link         VARCHAR(1000),
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_news_symbol_external UNIQUE (symbol_id, external_id)
);

CREATE INDEX idx_news_symbol_published ON news_articles (symbol_id, published_at DESC);

-- One cached LLM insight per (symbol, kind). `fingerprint` identifies the inputs
-- the insight was generated from (e.g. latest article id / fundamentals timestamp);
-- when it no longer matches, the insight is regenerated.
CREATE TABLE ai_insights (
    symbol_id    BIGINT NOT NULL REFERENCES symbols (id) ON DELETE CASCADE,
    kind         VARCHAR(20) NOT NULL,          -- NEWS | FUNDAMENTALS
    content      JSONB NOT NULL,
    fingerprint  VARCHAR(120) NOT NULL,
    model_name   VARCHAR(60),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol_id, kind)
);
