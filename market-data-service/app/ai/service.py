"""Trains per-symbol models and upserts ai_predictions rows (Python-owned table)."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.predictor import InsufficientDataError, train_and_predict
from app.models import AiPrediction, Symbol, SyncAudit
from app.services.indicator_service import load_ohlcv

log = logging.getLogger(__name__)


def train_all(session: Session, tickers: list[str] | None = None) -> dict:
    audit = SyncAudit(run_type="AI_TRAIN", status="RUNNING")
    session.add(audit)
    session.flush()

    stmt = select(Symbol).where(Symbol.active)
    if tickers:
        stmt = stmt.where(Symbol.ticker.in_([t.upper() for t in tickers]))
    symbols = session.scalars(stmt).all()

    trained, skipped, failures = 0, [], []
    for sym in symbols:
        df = load_ohlcv(session, sym.id)
        if df.empty:
            skipped.append(sym.ticker)
            continue
        try:
            result = train_and_predict(df.set_index("trade_date"))
        except InsufficientDataError as exc:
            skipped.append(f"{sym.ticker} ({exc})")
            continue
        except Exception as exc:
            log.exception("AI training failed for %s", sym.ticker)
            failures.append(f"{sym.ticker}: {exc}")
            continue

        row = session.get(AiPrediction, sym.id) or AiPrediction(symbol_id=sym.id)
        row.as_of_date = df["trade_date"].iloc[-1]
        row.predicted_return_pct = result.predicted_return_pct
        row.direction = result.direction
        row.test_direction_accuracy = result.test_direction_accuracy
        row.test_mae_pct = result.test_mae_pct
        row.train_rows = result.train_rows
        row.model_name = result.model_name
        row.trained_at = datetime.now(timezone.utc)
        session.merge(row)
        trained += 1

    audit.status = "FAILED" if failures and not trained else ("PARTIAL" if failures else "SUCCESS")
    audit.rows_inserted = trained
    audit.finished_at = datetime.now(timezone.utc)
    audit.message = f"{trained} trained; skipped: {len(skipped)}; failures: {failures or 'none'}"
    session.commit()

    return {"status": audit.status, "trained": trained, "skipped": skipped,
            "failures": failures}
