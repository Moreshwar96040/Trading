from datetime import date, datetime, timezone

import pandas as pd

from app.models import OhlcvDaily
from app.providers.base import MarketDataProvider, OHLCV_COLUMNS, ProviderError, Quote
from app.services.sync_service import sync_daily

TODAY = date(2026, 7, 3)


class FakeProvider(MarketDataProvider):
    """Records requested windows; returns one candle per requested day."""

    def __init__(self, fail_symbols: set[str] | None = None):
        self.calls: list[tuple[str, date, date]] = []
        self.fail_symbols = fail_symbols or set()

    def fetch_daily(self, vendor_symbol, start, end):
        self.calls.append((vendor_symbol, start, end))
        if vendor_symbol in self.fail_symbols:
            raise ProviderError("boom")
        days = pd.bdate_range(start, end)
        return pd.DataFrame({
            "trade_date": [d.date() for d in days],
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0,
            "adj_close": 104.0, "volume": 1000,
        }, columns=OHLCV_COLUMNS) if len(days) else pd.DataFrame(columns=OHLCV_COLUMNS)

    def get_quote(self, vendor_symbol):
        return Quote(vendor_symbol, 100.0, 99.0, 1.0, 1.01, datetime.now(timezone.utc))


def test_sync_backfills_from_lookback_when_table_empty(session, reliance):
    provider = FakeProvider()
    summary = sync_daily(session, provider, default_lookback_days=10, today=TODAY)

    assert summary["status"] == "SUCCESS"
    (sym, start, end) = provider.calls[0]
    assert sym == "RELIANCE.NS"
    assert start == date(2026, 6, 23)   # today - 10d
    assert end == TODAY
    assert summary["rows_inserted"] > 0


def test_sync_fetches_only_the_gap(session, reliance):
    session.add(OhlcvDaily(symbol_id=reliance.id, trade_date=date(2026, 6, 30),
                           open=1, high=2, low=1, close=1.5, adj_close=1.5, volume=10))
    session.commit()

    provider = FakeProvider()
    sync_daily(session, provider, today=TODAY)

    (_, start, end) = provider.calls[0]
    assert start == date(2026, 7, 1)    # last stored + 1
    assert end == TODAY


def test_sync_skips_when_up_to_date(session, reliance):
    session.add(OhlcvDaily(symbol_id=reliance.id, trade_date=TODAY,
                           open=1, high=2, low=1, close=1.5, adj_close=1.5, volume=10))
    session.commit()

    provider = FakeProvider()
    summary = sync_daily(session, provider, today=TODAY)

    assert provider.calls == []
    assert summary["symbols"]["RELIANCE"]["note"] == "up to date"


def test_sync_partial_on_provider_failure(session, reliance):
    from app.models import Symbol
    session.add(Symbol(ticker="TCS", yahoo_symbol="TCS.NS", name="TCS Ltd", sector="IT"))
    session.commit()

    provider = FakeProvider(fail_symbols={"TCS.NS"})
    summary = sync_daily(session, provider, default_lookback_days=5, today=TODAY)

    assert summary["status"] == "PARTIAL"
    assert any("TCS" in f for f in summary["failures"])
    assert summary["symbols"]["RELIANCE"]["inserted"] > 0


def test_sync_respects_ticker_filter(session, reliance):
    provider = FakeProvider()
    sync_daily(session, provider, tickers=["reliance"], default_lookback_days=5, today=TODAY)
    assert len(provider.calls) == 1
