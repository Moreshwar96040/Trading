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

    # --- scheduler ---
    scheduler_enabled: bool = True
    sync_cron: str = "30 18 * * 1-5"        # post-market IST, weekdays
    fundamentals_cron: str = "0 8 * * 6"    # Saturday morning IST (data changes quarterly)
    timezone: str = "Asia/Kolkata"

    # --- service ---
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
