"""Live strategy signals: run each strategy's entry/exit rules against the most
recent bar of every active symbol and persist what fired (Python-owned table).

This is the connective tissue of the trading loop — the same rules engine the
backtester uses (`combined_signal`), evaluated on today instead of history, so a
signal here is exactly what the backtest would have acted on tomorrow.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.backtest.rules import combined_signal
from app.backtest.service import validate_definition
from app.models import StrategySignal, Strategy, Symbol, SyncAudit
from app.services.indicator_service import load_ohlcv

log = logging.getLogger(__name__)

MIN_BARS = 30   # below this, indicator warm-up makes signals meaningless


def evaluate_signals(session: Session, strategy_ids: list[int] | None = None,
                     tickers: list[str] | None = None) -> dict:
    audit = SyncAudit(run_type="SIGNALS", status="RUNNING")
    session.add(audit)
    session.flush()

    strategies_stmt = select(Strategy)
    if strategy_ids:
        strategies_stmt = strategies_stmt.where(Strategy.id.in_(strategy_ids))
    strategies = session.scalars(strategies_stmt).all()

    symbols_stmt = select(Symbol).where(Symbol.active)
    if tickers:
        symbols_stmt = symbols_stmt.where(Symbol.ticker.in_([t.upper() for t in tickers]))
    symbols = session.scalars(symbols_stmt).all()

    # Load each symbol's history once, shared across all strategies.
    frames = {}
    for sym in symbols:
        df = load_ohlcv(session, sym.id)
        if len(df) >= MIN_BARS:
            frames[sym] = df.set_index("trade_date")

    signals, skipped = [], []
    for strategy in strategies:
        if validate_definition(strategy.definition):
            skipped.append(strategy.name)
            continue
        entry_rules = strategy.definition.get("entry") or []
        exit_rules = strategy.definition.get("exit") or []
        for sym, df in frames.items():
            as_of = df.index[-1]
            close = round(float(df["close"].iloc[-1]), 4)
            if bool(combined_signal(df, entry_rules).iloc[-1]):
                signals.append(dict(strategy_id=strategy.id, symbol_id=sym.id,
                                    signal="ENTRY", as_of_date=as_of, close=close))
            if exit_rules and bool(combined_signal(df, exit_rules).iloc[-1]):
                signals.append(dict(strategy_id=strategy.id, symbol_id=sym.id,
                                    signal="EXIT", as_of_date=as_of, close=close))

    # Replace, don't append: each evaluated strategy's signal set reflects the
    # latest bar only — stale rows from prior runs on the same date would linger
    # after a definition edit.
    evaluated_ids = [s.id for s in strategies]
    if evaluated_ids:
        session.execute(delete(StrategySignal)
                        .where(StrategySignal.strategy_id.in_(evaluated_ids)))
    for row in signals:
        session.add(StrategySignal(**row))

    audit.status = "SUCCESS"
    audit.rows_inserted = len(signals)
    audit.finished_at = datetime.now(timezone.utc)
    audit.message = (f"{len(signals)} signals from {len(strategies)} strategies × "
                     f"{len(frames)} symbols; skipped invalid: {skipped or 'none'}")
    session.commit()
    log.info("Signal evaluation: %d signals, %d strategies, %d symbols",
             len(signals), len(strategies), len(frames))
    return {"status": "SUCCESS", "signals": len(signals),
            "strategies": len(strategies), "symbols": len(frames),
            "skipped_invalid": skipped}
