"""One-time (idempotent) import of the local nse_dataset/ CSVs into PostgreSQL.

CSV format: Date,Open,High,Low,Close,AdjClose,Volume,Split — one file per ticker.
Only symbols present in the `symbols` table are imported (the symbol master is
seeded by Flyway migration V2).
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Symbol, SyncAudit
from app.services.quality import validate_frame
from app.services.upsert import bulk_insert_ohlcv

log = logging.getLogger(__name__)

_CSV_RENAME = {"Date": "trade_date", "Open": "open", "High": "high", "Low": "low",
               "Close": "close", "AdjClose": "adj_close", "Volume": "volume"}


def ingest_directory(session: Session, directory: str) -> dict:
    """Import every `<TICKER>.csv` matching an active symbol. Returns a summary dict."""
    audit = SyncAudit(run_type="CSV_IMPORT", status="RUNNING")
    session.add(audit)
    session.flush()

    base = Path(directory)
    per_symbol: dict[str, dict] = {}
    inserted_total = rejected_total = 0
    failures: list[str] = []

    symbols = session.scalars(select(Symbol).where(Symbol.active)).all()
    for sym in symbols:
        path = base / f"{sym.ticker}.csv"
        if not path.exists():
            log.info("No CSV for %s at %s — skipping", sym.ticker, path)
            continue
        try:
            raw = pd.read_csv(path).rename(columns=_CSV_RENAME)
            clean, rejected = validate_frame(raw)
            inserted = bulk_insert_ohlcv(session, sym.id, clean)
            per_symbol[sym.ticker] = {"inserted": inserted, "rejected": rejected,
                                      "read": len(raw)}
            inserted_total += inserted
            rejected_total += rejected
        except Exception as exc:
            log.exception("CSV import failed for %s", sym.ticker)
            failures.append(f"{sym.ticker}: {exc}")

    audit.status = "FAILED" if failures and not per_symbol else ("PARTIAL" if failures else "SUCCESS")
    audit.rows_inserted = inserted_total
    audit.rows_rejected = rejected_total
    audit.finished_at = datetime.now(timezone.utc)
    audit.message = "; ".join(failures) if failures else f"{len(per_symbol)} symbols imported"
    session.commit()

    return {"status": audit.status, "symbols": per_symbol,
            "rows_inserted": inserted_total, "rows_rejected": rejected_total,
            "failures": failures}
