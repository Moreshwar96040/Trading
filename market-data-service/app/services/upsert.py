"""Idempotent OHLCV bulk insert. Dialect-aware ON CONFLICT DO NOTHING
(PostgreSQL in production, SQLite in unit tests)."""
import pandas as pd
from sqlalchemy.orm import Session

from app.models import OhlcvDaily


def bulk_insert_ohlcv(session: Session, symbol_id: int, clean: pd.DataFrame) -> int:
    """Insert validated rows; silently skip (symbol_id, trade_date) duplicates.
    Returns the number of rows actually inserted."""
    if clean.empty:
        return 0

    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover
        raise NotImplementedError(f"Unsupported dialect: {dialect}")

    records = [
        {
            "symbol_id": symbol_id,
            "trade_date": r.trade_date,
            "open": r.open, "high": r.high, "low": r.low, "close": r.close,
            "adj_close": None if pd.isna(r.adj_close) else r.adj_close,
            "volume": int(r.volume),
        }
        for r in clean.itertuples(index=False)
    ]
    stmt = insert(OhlcvDaily).values(records).on_conflict_do_nothing(
        index_elements=["symbol_id", "trade_date"]
    )
    result = session.execute(stmt)
    return result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
