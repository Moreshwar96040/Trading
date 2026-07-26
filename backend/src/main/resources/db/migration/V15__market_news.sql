-- V15: market-wide news headlines (Python-owned). Multi-source RSS: WSJ/Dow
-- Jones and FT official feeds + aggregated Indian market coverage (which carries
-- syndicated Reuters/Bloomberg reporting). Feeds the macro layer of the Alpha
-- Stack via a cached AI digest.

CREATE TABLE market_news (
    id           BIGSERIAL PRIMARY KEY,
    source       VARCHAR(60) NOT NULL,
    title        VARCHAR(500) NOT NULL,
    link         VARCHAR(1000),
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedup_key    VARCHAR(64) NOT NULL,
    CONSTRAINT uq_market_news UNIQUE (dedup_key)
);

CREATE INDEX idx_market_news_published ON market_news (published_at DESC);
