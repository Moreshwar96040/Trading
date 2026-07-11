"""Computes the screener_snapshot row for every active symbol (idempotent upsert).

Runs after each daily sync (scheduler) and on demand via the API.
"""
import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators import core
from app.models import Fundamentals, ScreenerSnapshot, Symbol, SyncAudit
from app.services.indicator_service import load_ohlcv

#: Ratio columns copied from fundamentals onto the snapshot (keeps screener single-table).
FUNDAMENTAL_COLUMNS = ["market_cap", "pe_trailing", "pb", "dividend_yield_pct",
                       "roe_pct", "debt_to_equity", "profit_margin_pct",
                       "revenue_growth_pct"]

log = logging.getLogger(__name__)

TRADING_DAYS = {"1m": 21, "3m": 63, "1y": 252, "52w": 252}
MIN_ROWS = 21   # below this we skip the symbol (indicators meaningless)


def _pct(new: float, old: float) -> float | None:
    return round((new - old) / old * 100.0, 4) if old else None


def compute_snapshot_row(df: pd.DataFrame) -> dict | None:
    """Latest indicator values from an OHLCV frame (ascending by date)."""
    if len(df) < MIN_ROWS:
        return None
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    last = -1
    win52 = df.tail(TRADING_DAYS["52w"])
    avg_vol_20 = float(vol.rolling(20).mean().iloc[last])
    m = core.macd(close)
    bb = core.bollinger(close)

    def _sf(series: pd.Series) -> float | None:   # safe float
        v = series.iloc[last]
        return None if pd.isna(v) else round(float(v), 6)

    high_52w = float(win52["high"].max())
    low_52w = float(win52["low"].min())
    c = float(close.iloc[last])
    prev_c = float(close.iloc[-2])

    def _ret(days: int) -> float | None:
        return _pct(c, float(close.iloc[-days - 1])) if len(close) > days else None

    return {
        "as_of_date": df["trade_date"].iloc[last],
        "close": round(c, 4),
        "change_1d_pct": _pct(c, prev_c),
        "volume": int(vol.iloc[last]),
        "avg_volume_20": round(avg_vol_20, 2) if not pd.isna(avg_vol_20) else None,
        "volume_ratio": round(float(vol.iloc[last]) / avg_vol_20, 4) if avg_vol_20 else None,
        "sma_20": _sf(core.sma(close, 20)),
        "sma_50": _sf(core.sma(close, 50)),
        "sma_200": _sf(core.sma(close, 200)),
        "ema_20": _sf(core.ema(close, 20)),
        "rsi_14": _sf(core.rsi(close, 14)),
        "macd": _sf(m["macd"]),
        "macd_signal": _sf(m["signal"]),
        "macd_hist": _sf(m["hist"]),
        "bb_upper": _sf(bb["upper"]),
        "bb_lower": _sf(bb["lower"]),
        "atr_14": _sf(core.atr(high, low, close, 14)),
        "high_52w": round(high_52w, 4),
        "low_52w": round(low_52w, 4),
        "pct_from_52w_high": _pct(c, high_52w),
        "pct_from_52w_low": _pct(c, low_52w),
        "return_1m_pct": _ret(TRADING_DAYS["1m"]),
        "return_3m_pct": _ret(TRADING_DAYS["3m"]),
        "return_1y_pct": _ret(TRADING_DAYS["1y"]),
    }


def refresh_snapshots(session: Session) -> dict:
    audit = SyncAudit(run_type="SNAPSHOT", status="RUNNING")
    session.add(audit)
    session.flush()

    computed, skipped = 0, []
    for sym in session.scalars(select(Symbol).where(Symbol.active)).all():
        row = compute_snapshot_row(load_ohlcv(session, sym.id))
        if row is None:
            skipped.append(sym.ticker)
            continue
        snapshot = session.get(ScreenerSnapshot, sym.id) or ScreenerSnapshot(symbol_id=sym.id)
        for key, value in row.items():
            setattr(snapshot, key, value)
        fundamentals = session.get(Fundamentals, sym.id)
        for col in FUNDAMENTAL_COLUMNS:
            setattr(snapshot, col, getattr(fundamentals, col) if fundamentals else None)
        snapshot.computed_at = datetime.now(timezone.utc)
        session.merge(snapshot)
        computed += 1

    audit.status = "SUCCESS"
    audit.rows_inserted = computed
    audit.finished_at = datetime.now(timezone.utc)
    audit.message = f"{computed} snapshots; skipped: {skipped or 'none'}"
    session.commit()
    log.info("Snapshot refresh: %d computed, %d skipped", computed, len(skipped))
    return {"status": "SUCCESS", "computed": computed, "skipped": skipped}
