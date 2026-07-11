"""Daily EOD sync with gap backfill.

For each active symbol: find the last stored trade_date, fetch (last+1 .. today)
from the provider, validate, insert. If the platform was offline for a week, this
catches up automatically. Safe to run any number of times.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import OhlcvDaily, Symbol, SyncAudit
from app.providers.base import MarketDataProvider, ProviderError
from app.services.quality import validate_frame
from app.services.upsert import bulk_insert_ohlcv

log = logging.getLogger(__name__)


def sync_daily(session: Session, provider: MarketDataProvider,
               tickers: list[str] | None = None,
               default_lookback_days: int = 730,
               today: date | None = None) -> dict:
    """Sync EOD candles for the given tickers (default: all active). Returns a summary."""
    today = today or date.today()
    audit = SyncAudit(run_type="DAILY_SYNC", status="RUNNING",
                      ticker=tickers[0] if tickers and len(tickers) == 1 else None)
    session.add(audit)
    session.flush()

    stmt = select(Symbol).where(Symbol.active)
    if tickers:
        stmt = stmt.where(Symbol.ticker.in_([t.upper() for t in tickers]))
    symbols = session.scalars(stmt).all()

    per_symbol: dict[str, dict] = {}
    inserted_total = rejected_total = 0
    failures: list[str] = []

    for sym in symbols:
        last: date | None = session.scalar(
            select(func.max(OhlcvDaily.trade_date)).where(OhlcvDaily.symbol_id == sym.id))
        start = (last + timedelta(days=1)) if last else today - timedelta(days=default_lookback_days)
        if start > today:
            per_symbol[sym.ticker] = {"inserted": 0, "rejected": 0, "note": "up to date"}
            continue
        try:
            raw = provider.fetch_daily(sym.yahoo_symbol, start, today)
            clean, rejected = validate_frame(raw)
            inserted = bulk_insert_ohlcv(session, sym.id, clean)
            per_symbol[sym.ticker] = {"inserted": inserted, "rejected": rejected,
                                      "window": f"{start}..{today}"}
            inserted_total += inserted
            rejected_total += rejected
        except ProviderError as exc:
            log.error("Sync failed for %s: %s", sym.ticker, exc)
            failures.append(f"{sym.ticker}: {exc}")

    audit.status = "FAILED" if failures and not per_symbol else ("PARTIAL" if failures else "SUCCESS")
    audit.rows_inserted = inserted_total
    audit.rows_rejected = rejected_total
    audit.finished_at = datetime.now(timezone.utc)
    audit.message = "; ".join(failures) if failures else f"{len(per_symbol)} symbols synced"
    session.commit()

    return {"status": audit.status, "symbols": per_symbol,
            "rows_inserted": inserted_total, "rows_rejected": rejected_total,
            "failures": failures}
