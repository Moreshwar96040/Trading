"""Central configuration. Every knob is an environment variable — no hardcoded values.

Reads a `.env` file if present (repo root or service dir). See `.env.example`.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads the repo-root .env first, then a service-local .env (which wins if both exist).
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8",
                                      extra="ignore")

    # --- database ---
    database_url: str = "postgresql+psycopg2://trading:trading@localhost:5432/trading"

    # --- ingestion ---
    csv_dataset_dir: str = "../nse_dataset"

    # --- Yahoo provider ---
    yahoo_throttle_seconds: float = 1.0     # pause between symbols (be polite, it's unofficial)
    yahoo_max_retries: int = 3
    yahoo_backoff_seconds: float = 2.0      # base for exponential backoff
    sync_default_lookback_days: int = 730   # backfill window for a symbol with no data yet

    # --- news & AI insights ---
    anthropic_api_key: str = ""             # empty = LLM insights disabled (articles still shown)
    anthropic_model: str = "claude-haiku-4-5"
    anthropic_max_tokens: int = 1000
    news_max_articles: int = 12             # per symbol, per fetch
    # Per-STOCK news feeds, "Name|url-template" comma-separated. Placeholders:
    # {query} = URL-encoded '"Company Name" OR "TICKER"', {symbol} = Yahoo symbol.
    # yfinance's news API covers only a fraction of NSE tickers, so these keyless
    # RSS sources are fanned out and merged per symbol (see stock_news_sources.py).
    stock_news_feeds: str = (
        "GoogleNews|https://news.google.com/rss/search?q={query}+when:21d&hl=en-IN&gl=IN&ceid=IN:en,"
        "BingNews|https://www.bing.com/news/search?q={query}&format=RSS,"
        "YahooRSS|https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=IN&lang=en-IN")
    stock_news_max_age_days: int = 21       # ignore headlines older than this
    # Market-wide RSS feeds, "Name|url" comma-separated. Defaults: WSJ (official
    # Dow Jones feed), FT markets, Google News India business (carries syndicated
    # Reuters/Bloomberg reporting), Economic Times & Mint markets.
    market_news_feeds: str = (
        "WSJ|https://feeds.content.dowjones.io/public/rss/RSSMarketsMain,"
        "FT|https://www.ft.com/markets?format=rss,"
        "GoogleNews-IN|https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-IN&gl=IN&ceid=IN:en,"
        "EconomicTimes|https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms,"
        "Mint|https://www.livemint.com/rss/markets")
    # $/million tokens for cost tracking (match your model's price card)
    anthropic_price_input_per_mtok: float = 1.0
    anthropic_price_output_per_mtok: float = 5.0
    usd_to_inr: float = 84.0                # for the ₹ display in the UI

    # --- MetaTrader 5 (Exness FX/crypto), read-only ---
    # Exness has no retail REST API; we attach to a locally running MT5 terminal
    # via the MetaTrader5 package (Windows only). Leave login blank to use
    # whatever account the terminal is already logged into — the normal case.
    mt5_login: int | None = None
    mt5_password: str = ""
    mt5_server: str = ""                    # e.g. "Exness-MT5Real"
    mt5_terminal_path: str = ""             # optional explicit terminal64.exe path

    # --- paper autopilot (Alpha Stack trades its own signals) ---
    # OFF by default and PAPER ONLY — there is no live code path. When enabled,
    # the daily job opens paper positions for setups scoring >= 55 (max 8 open)
    # so realised P&L can be attributed back to conviction.
    autopilot_enabled: bool = False
    # Spring owns the paper book; the autopilot places orders through its API.
    backend_base_url: str = "http://localhost:8080"

    # --- scheduler ---
    scheduler_enabled: bool = True
    sync_cron: str = "30 18 * * 1-5"        # post-market IST, weekdays
    fundamentals_cron: str = "0 8 * * 6"    # Saturday morning IST (data changes quarterly)
    briefing_cron: str = "45 8 * * 1-5"     # pre-market IST: warm the morning briefing
    timezone: str = "Asia/Kolkata"

    # --- service ---
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
