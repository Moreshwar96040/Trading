"""Pydantic request/response models for the internal API."""
from datetime import date, datetime

from pydantic import BaseModel


class IngestCsvRequest(BaseModel):
    directory: str | None = None   # defaults to settings.csv_dataset_dir


class SyncRequest(BaseModel):
    tickers: list[str] | None = None   # None = all active symbols
    from_date: date | None = None      # backfill history at least back to this date


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


class SeedSymbolRequest(BaseModel):
    ticker: str


class SeedSymbolResponse(BaseModel):
    id: int
    ticker: str
    name: str
    sector: str | None
    exchange: str
    currency: str
    yahoo_symbol: str
    seeded: bool
