from datetime import date, timedelta

from sqlalchemy import select

from app.models import OhlcvDaily, ScreenerSnapshot
from app.services.snapshot_service import MIN_ROWS, compute_snapshot_row, refresh_snapshots
from app.services.indicator_service import load_ohlcv


def _seed_candles(session, symbol_id: int, days: int, start_price: float = 100.0):
    """Rising series: +1 per day, volume 1000 (last day 3000 for volume_ratio)."""
    start = date(2026, 1, 1)
    for i in range(days):
        price = start_price + i
        session.add(OhlcvDaily(symbol_id=symbol_id, trade_date=start + timedelta(days=i),
                               open=price - 0.5, high=price + 1, low=price - 1,
                               close=price, adj_close=price,
                               volume=3000 if i == days - 1 else 1000))
    session.commit()


def test_snapshot_row_computed_correctly(session, reliance):
    _seed_candles(session, reliance.id, 60)
    row = compute_snapshot_row(load_ohlcv(session, reliance.id))

    assert row["close"] == 159.0                       # 100 + 59
    assert row["change_1d_pct"] > 0
    assert row["sma_20"] is not None
    assert row["sma_200"] is None                      # not enough history
    assert row["rsi_14"] == 100.0                      # strictly rising
    assert row["high_52w"] == 160.0                    # 159 + 1
    assert row["volume_ratio"] > 1.5                   # 3000 vs ~1100 avg
    assert row["return_1m_pct"] is not None


def test_snapshot_skips_short_history(session, reliance):
    _seed_candles(session, reliance.id, MIN_ROWS - 1)
    assert compute_snapshot_row(load_ohlcv(session, reliance.id)) is None


def test_refresh_upserts_one_row_per_symbol(session, reliance):
    _seed_candles(session, reliance.id, 40)

    first = refresh_snapshots(session)
    assert first["computed"] == 1
    second = refresh_snapshots(session)               # idempotent re-run
    assert second["computed"] == 1

    rows = session.scalars(select(ScreenerSnapshot)).all()
    assert len(rows) == 1
    assert rows[0].symbol_id == reliance.id
    assert float(rows[0].close) == 139.0
