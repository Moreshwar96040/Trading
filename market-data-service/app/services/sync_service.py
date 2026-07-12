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
               today: date | None = None,
               start_date: date | None = None) -> dict:
    """Sync EOD candles for the given tickers (default: all active). Returns a summary.

    ``start_date`` requests history at least back to that date: besides the usual
    forward gap-fill (last stored bar .. today), any head gap (start_date .. first
    stored bar) is also fetched, so old windows can be backfilled on demand.
    """
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
        first, last = session.execute(
            select(func.min(OhlcvDaily.trade_date), func.max(OhlcvDaily.trade_date))
            .where(OhlcvDaily.symbol_id == sym.id)).one()

        # Windows to fetch: forward gap-fill (last+1 .. today) as always, plus a
        # head backfill (start_date .. first-1) when older history was requested.
        default_start = start_date or (today - timedelta(days=default_lookback_days))
        windows: list[tuple[date, date]] = []
        if last is None:
            windows.append((default_start, today))
        else:
            if start_date is not None and start_date < first:
                windows.append((start_date, first - timedelta(days=1)))
            if last < today:
                windows.append((last + timedelta(days=1), today))

        if not windows:
            per_symbol[sym.ticker] = {"inserted": 0, "rejected": 0, "note": "up to date"}
            continue
        inserted = rejected = 0
        fetched = []
        try:
            for win_start, win_end in windows:
                raw = provider.fetch_daily(sym.yahoo_symbol, win_start, win_end)
                clean, win_rejected = validate_frame(raw)
                inserted += bulk_insert_ohlcv(session, sym.id, clean)
                rejected += win_rejected
                fetched.append(f"{win_start}..{win_end}")
            per_symbol[sym.ticker] = {"inserted": inserted, "rejected": rejected,
                                      "window": ", ".join(fetched)}
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
