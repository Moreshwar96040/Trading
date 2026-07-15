"""Intraday bar sync + loading (15-minute default, Yahoo free tier).

Yahoo only serves ~60 days of 15m history, so the table is a rolling window:
each sync inserts whatever is new (idempotent via the unique constraint).
Honesty note propagated to the UI: 60 days is enough to TRADE an intraday
setup, not enough to statistically TRUST its backtest.
"""
import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OhlcvIntraday, Symbol, SyncAudit

log = logging.getLogger(__name__)

SUPPORTED_INTERVALS = {"15m", "30m", "60m"}


def _utc_naive(ts: datetime) -> datetime:
    """Normalize for dedup: some backends (SQLite) return naive datetimes,
    providers return tz-aware UTC — compare apples to apples."""
    if ts.tzinfo is not None:
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


def sync_intraday(session: Session, provider, tickers: list[str] | None = None,
                  interval: str = "15m") -> dict:
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"interval must be one of {sorted(SUPPORTED_INTERVALS)}")

    audit = SyncAudit(run_type="INTRADAY", status="RUNNING",
                      ticker=tickers[0] if tickers and len(tickers) == 1 else None)
    session.add(audit)
    session.flush()

    stmt = select(Symbol).where(Symbol.active)
    if tickers:
        stmt = stmt.where(Symbol.ticker.in_([t.upper() for t in tickers]))
    symbols = session.scalars(stmt).all()

    inserted_total = 0
    failures: list[str] = []
    per_symbol: dict[str, int] = {}

    for sym in symbols:
        try:
            df = provider.fetch_intraday(sym.yahoo_symbol, interval=interval)
        except Exception as exc:                    # noqa: BLE001 — provider variety
            log.error("Intraday fetch failed for %s: %s", sym.ticker, exc)
            failures.append(f"{sym.ticker}: {exc}")
            continue
        if df.empty:
            per_symbol[sym.ticker] = 0
            continue
        existing = {_utc_naive(ts) for ts in session.scalars(
            select(OhlcvIntraday.ts).where(OhlcvIntraday.symbol_id == sym.id,
                                           OhlcvIntraday.interval == interval)).all()}
        inserted = 0
        for row in df.itertuples(index=False):
            ts = row.ts.to_pydatetime()
            if _utc_naive(ts) in existing:
                continue
            session.add(OhlcvIntraday(symbol_id=sym.id, interval=interval, ts=ts,
                                      open=float(row.open), high=float(row.high),
                                      low=float(row.low), close=float(row.close),
                                      volume=int(row.volume)))
            inserted += 1
        session.commit()
        per_symbol[sym.ticker] = inserted
        inserted_total += inserted

    audit.status = "FAILED" if failures and not per_symbol else \
        ("PARTIAL" if failures else "SUCCESS")
    audit.rows_inserted = inserted_total
    audit.finished_at = datetime.now(timezone.utc)
    audit.message = "; ".join(failures) if failures else \
        f"{len(per_symbol)} symbols, {inserted_total} bars ({interval})"
    session.commit()
    return {"status": audit.status, "rows_inserted": inserted_total,
            "symbols": per_symbol, "failures": failures, "interval": interval}


def load_intraday(session: Session, symbol_id: int, interval: str = "15m") -> pd.DataFrame:
    """All stored bars for a symbol, ascending, indexed for the backtest engine."""
    rows = session.execute(
        select(OhlcvIntraday.ts, OhlcvIntraday.open, OhlcvIntraday.high,
               OhlcvIntraday.low, OhlcvIntraday.close, OhlcvIntraday.volume)
        .where(OhlcvIntraday.symbol_id == symbol_id, OhlcvIntraday.interval == interval)
        .order_by(OhlcvIntraday.ts)).all()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    return df
