"""Provider abstraction — the single seam for swapping market-data vendors.

Any provider (Yahoo today; Zerodha Kite / NSE bhavcopy later) implements this
interface. Nothing outside `app.providers` may import a concrete provider.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

#: Canonical columns every provider must return from fetch_daily().
OHLCV_COLUMNS = ["trade_date", "open", "high", "low", "close", "adj_close", "volume"]


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    prev_close: float | None
    change: float | None
    change_pct: float | None
    as_of: datetime


class MarketDataProvider(ABC):
    """Fetches raw market data from an external vendor."""

    @abstractmethod
    def fetch_daily(self, vendor_symbol: str, start: date, end: date) -> pd.DataFrame:
        """Return daily OHLCV rows for [start, end] inclusive with OHLCV_COLUMNS.

        Must return an empty DataFrame (with correct columns) when no data exists.
        Raises ProviderError on unrecoverable vendor failure.
        """

    @abstractmethod
    def get_quote(self, vendor_symbol: str) -> Quote:
        """Return the latest (possibly delayed) quote. Raises ProviderError on failure."""


class FundamentalDataProvider(ABC):
    """Fetches fundamental data. Separate interface so price-only providers/fakes
    don't have to implement it."""

    @abstractmethod
    def fetch_fundamentals(self, vendor_symbol: str) -> dict:
        """Ratios row (see fundamentals_mapping.map_ratios). Raises ProviderError."""

    @abstractmethod
    def fetch_statements(self, vendor_symbol: str) -> list[dict]:
        """Annual + quarterly financial_statements rows. Raises ProviderError."""


class ProviderError(RuntimeError):
    """Vendor call failed after retries."""
