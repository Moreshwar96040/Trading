"""Refreshes fundamentals + financial statements for active symbols (idempotent)."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FinancialStatement, Fundamentals, Symbol, SyncAudit
from app.providers.base import FundamentalDataProvider, ProviderError

log = logging.getLogger(__name__)


def refresh_fundamentals(session: Session, provider: FundamentalDataProvider,
                         tickers: list[str] | None = None) -> dict:
    audit = SyncAudit(run_type="FUNDAMENTALS", status="RUNNING")
    session.add(audit)
    session.flush()

    stmt = select(Symbol).where(Symbol.active)
    if tickers:
        stmt = stmt.where(Symbol.ticker.in_([t.upper() for t in tickers]))
    symbols = session.scalars(stmt).all()

    updated, stmt_rows_total = 0, 0
    failures: list[str] = []

    for sym in symbols:
        try:
            ratios = provider.fetch_fundamentals(sym.yahoo_symbol)
            row = session.get(Fundamentals, sym.id) or Fundamentals(symbol_id=sym.id)
            for key, value in ratios.items():
                setattr(row, key, value)
            row.computed_at = datetime.now(timezone.utc)
            session.merge(row)

            stmt_rows_total += _upsert_statements(session, sym.id,
                                                  provider.fetch_statements(sym.yahoo_symbol))
            updated += 1
        except ProviderError as exc:
            log.error("Fundamentals failed for %s: %s", sym.ticker, exc)
            failures.append(f"{sym.ticker}: {exc}")

    audit.status = "FAILED" if failures and not updated else ("PARTIAL" if failures else "SUCCESS")
    audit.rows_inserted = updated
    audit.finished_at = datetime.now(timezone.utc)
    audit.message = "; ".join(failures) if failures else \
        f"{updated} symbols, {stmt_rows_total} statement rows"
    session.commit()

    return {"status": audit.status, "symbols_updated": updated,
            "statement_rows": stmt_rows_total, "failures": failures}


def _upsert_statements(session: Session, symbol_id: int, rows: list[dict]) -> int:
    count = 0
    for row in rows:
        existing = session.scalar(select(FinancialStatement).where(
            FinancialStatement.symbol_id == symbol_id,
            FinancialStatement.period_end == row["period_end"],
            FinancialStatement.period_type == row["period_type"]))
        target = existing or FinancialStatement(symbol_id=symbol_id,
                                                period_end=row["period_end"],
                                                period_type=row["period_type"])
        for key, value in row.items():
            if key not in ("period_end", "period_type"):
                setattr(target, key, value)
        if existing is None:
            session.add(target)
        count += 1
    return count
