"""Yahoo Finance provider (via yfinance). Free, unofficial, 15-min delayed quotes.

Politeness: throttled per call, exponential-backoff retries. If Yahoo breaks,
only this file changes (or a new provider replaces it behind the interface).
"""
import logging
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

from app.providers.base import (FundamentalDataProvider, MarketDataProvider, OHLCV_COLUMNS,
                                ProviderError, Quote)
from app.services.fundamentals_mapping import map_ratios, map_statements

log = logging.getLogger(__name__)


class YahooProvider(MarketDataProvider, FundamentalDataProvider):
    def __init__(self, throttle_seconds: float = 1.0, max_retries: int = 3,
                 backoff_seconds: float = 2.0) -> None:
        self._throttle = throttle_seconds
        self._max_retries = max_retries
        self._backoff = backoff_seconds

    # ------------------------------------------------------------------ daily
    def fetch_daily(self, vendor_symbol: str, start: date, end: date) -> pd.DataFrame:
        raw = self._with_retries(
            lambda: yf.Ticker(vendor_symbol).history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),  # yfinance end is exclusive
                interval="1d",
                auto_adjust=False,
            ),
            what=f"history {vendor_symbol} {start}..{end}",
        )
        time.sleep(self._throttle)
        if raw is None or raw.empty:
            return pd.DataFrame(columns=OHLCV_COLUMNS)
        df = raw.reset_index()
        df["trade_date"] = pd.to_datetime(df["Date"]).dt.date
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                                "Close": "close", "Adj Close": "adj_close", "Volume": "volume"})
        if "adj_close" not in df.columns:      # auto_adjust quirk safety
            df["adj_close"] = df["close"]
        return df[OHLCV_COLUMNS]

    # ------------------------------------------------------------------ quote
    def get_quote(self, vendor_symbol: str) -> Quote:
        def _fetch() -> Quote:
            info = yf.Ticker(vendor_symbol).fast_info
            price = float(info["last_price"])
            try:  # fast_info is dict-like but not a dict; missing keys raise
                prev = float(info["previous_close"])
            except (KeyError, TypeError, ValueError):
                prev = None
            change = price - prev if prev else None
            change_pct = (change / prev * 100.0) if (change is not None and prev) else None
            return Quote(symbol=vendor_symbol, price=price, prev_close=prev,
                         change=change, change_pct=change_pct,
                         as_of=datetime.now(timezone.utc))

        quote = self._with_retries(_fetch, what=f"quote {vendor_symbol}")
        time.sleep(self._throttle)
        return quote

    # ----------------------------------------------------------- fundamentals
    def fetch_fundamentals(self, vendor_symbol: str) -> dict:
        def _fetch() -> dict:
            ratios = map_ratios(yf.Ticker(vendor_symbol).info or {})
            if all(v is None for v in ratios.values()):
                # Yahoo sometimes returns an empty/blocked payload without raising —
                # treat as failure so it retries and audits properly instead of
                # silently storing a row of NULLs.
                raise RuntimeError("Yahoo returned no usable fundamental fields")
            return ratios

        ratios = self._with_retries(_fetch, what=f"fundamentals {vendor_symbol}")
        time.sleep(self._throttle)
        return ratios

    def fetch_statements(self, vendor_symbol: str) -> list[dict]:
        def _fetch() -> list[dict]:
            t = yf.Ticker(vendor_symbol)
            rows = map_statements(t.income_stmt, t.balance_sheet, t.cashflow, "ANNUAL")
            rows += map_statements(t.quarterly_income_stmt, t.quarterly_balance_sheet,
                                   t.quarterly_cashflow, "QUARTERLY")
            return rows

        rows = self._with_retries(_fetch, what=f"statements {vendor_symbol}")
        time.sleep(self._throttle)
        return rows

    # ---------------------------------------------------------------- helpers
    def _with_retries(self, fn, what: str):
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return fn()
            except Exception as exc:  # yfinance raises assorted exception types
                last_exc = exc
                wait = self._backoff * (2 ** (attempt - 1))
                log.warning("Yahoo call failed (%s), attempt %d/%d: %s — retrying in %.1fs",
                            what, attempt, self._max_retries, exc, wait)
                time.sleep(wait)
        raise ProviderError(f"Yahoo call failed after {self._max_retries} attempts: {what}") from last_exc
