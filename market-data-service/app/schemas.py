"""Pydantic request/response models for the internal API."""
from datetime import datetime

from pydantic import BaseModel


class IngestCsvRequest(BaseModel):
    directory: str | None = None   # defaults to settings.csv_dataset_dir


class SyncRequest(BaseModel):
    tickers: list[str] | None = None   # None = all active symbols


class RunSummary(BaseModel):
    status: str
    rows_inserted: int
    rows_rejected: int
    symbols: dict
    failures: list[str]


class QuoteResponse(BaseModel):
    ticker: str
    yahoo_symbol: str
    price: float
    prev_close: float | None
    change: float | None
    change_pct: float | None
    as_of: datetime
