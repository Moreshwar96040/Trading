-- V16: per-symbol daily news-sentiment history (Python-owned). One row per
-- symbol per day, written pre-market by the briefing job. Gives the Alpha Stack
-- news layer a memory so it can score sentiment *momentum* (improving vs
-- deteriorating over days) and volume velocity, not just a single day's tone.

CREATE TABLE news_sentiment_history (
    symbol_id     BIGINT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    as_of_date    DATE   NOT NULL,
    sentiment     VARCHAR(10),
    article_count INT    NOT NULL DEFAULT 0,
    catalysts     JSONB,
    score         NUMERIC(6, 2),
    generated_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (symbol_id, as_of_date)
);

CREATE INDEX idx_news_sent_hist_symbol_date
    ON news_sentiment_history (symbol_id, as_of_date DESC);
