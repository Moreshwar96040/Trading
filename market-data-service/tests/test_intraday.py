from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.models import OhlcvIntraday, Strategy, Symbol
from app.services.intraday_service import load_intraday, sync_intraday


class FakeIntradayProvider:
    """Returns `bars` 15m candles ending now; records calls."""

    def __init__(self, bars: int = 50, fail: bool = False):
        self.bars = bars
        self.fail = fail
        self.calls: list[str] = []

    def fetch_intraday(self, vendor_symbol, interval="15m", period="60d"):
        self.calls.append(vendor_symbol)
        if self.fail:
            raise RuntimeError("boom")
        start = datetime(2026, 7, 14, 9, 15, tzinfo=timezone.utc)
        ts = [start + timedelta(minutes=15 * i) for i in range(self.bars)]
        return pd.DataFrame({
            "ts": pd.to_datetime(ts, utc=True),
            "open": [100.0 + i * 0.1 for i in range(self.bars)],
            "high": [100.5 + i * 0.1 for i in range(self.bars)],
            "low": [99.5 + i * 0.1 for i in range(self.bars)],
            "close": [100.2 + i * 0.1 for i in range(self.bars)],
            "volume": [1000] * self.bars,
        })


def test_sync_intraday_inserts_and_dedups(session: Session, reliance: Symbol):
    provider = FakeIntradayProvider(bars=40)
    first = sync_intraday(session, provider, interval="15m")
    assert first["status"] == "SUCCESS"
    assert first["rows_inserted"] == 40

    second = sync_intraday(session, provider, interval="15m")   # same bars again
    assert second["rows_inserted"] == 0                          # idempotent


def test_sync_intraday_rejects_bad_interval(session: Session, reliance: Symbol):
    try:
        sync_intraday(session, FakeIntradayProvider(), interval="3m")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_sync_intraday_partial_on_failure(session: Session, reliance: Symbol):
    from app.models import Symbol as Sym
    session.add(Sym(ticker="TCS", yahoo_symbol="TCS.NS", name="TCS", sector="IT"))
    session.commit()

    class Mixed(FakeIntradayProvider):
        def fetch_intraday(self, vendor_symbol, interval="15m", period="60d"):
            if vendor_symbol == "TCS.NS":
                raise RuntimeError("boom")
            return super().fetch_intraday(vendor_symbol, interval, period)

    result = sync_intraday(session, Mixed(bars=10))
    assert result["status"] == "PARTIAL"
    assert any("TCS" in f for f in result["failures"])


def test_load_intraday_roundtrip(session: Session, reliance: Symbol):
    sync_intraday(session, FakeIntradayProvider(bars=20))
    df = load_intraday(session, reliance.id, interval="15m")
    assert len(df) == 20
    assert list(df["close"])[0] == 100.2
    assert df["ts"].is_monotonic_increasing


def test_intraday_backtest_runs(session: Session, reliance: Symbol):
    """End-to-end: 15m bars -> timeframe='15m' backtest persists trades cleanly."""
    from app.backtest.service import run_and_persist

    sync_intraday(session, FakeIntradayProvider(bars=120))
    strategy = Strategy(name="intraday-test", definition={
        "entry": [{"left": "close", "op": "crosses_above", "right": "sma_5"}],
        "exit": [{"left": "close", "op": "crosses_below", "right": "sma_5"}],
        "stop_loss_pct": 2,
    })
    session.add(strategy)
    session.commit()

    summary = run_and_persist(session, strategy.id, {"timeframe": "15m",
                                                     "initial_capital": 100000})
    assert summary["status"] == "SUCCESS"
    assert "60-day" in summary["metrics"]["data_coverage_note"]


def test_intraday_backtest_without_bars_fails_clearly(session: Session, reliance: Symbol):
    from app.backtest.service import run_and_persist

    strategy = Strategy(name="no-bars", definition={
        "entry": [{"left": "close", "op": "gt", "right": "sma_5"}],
        "stop_loss_pct": 2,
    })
    session.add(strategy)
    session.commit()
    try:
        run_and_persist(session, strategy.id, {"timeframe": "15m"})
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "intraday sync" in str(exc)
