"""Backtest orchestration: load strategy + data from DB, run the pure engine,
persist results. The only module in app.backtest that touches the database."""
import logging
from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestParams, run_backtest
from app.backtest.metrics import compute_metrics
from app.backtest.rules import validate_rules
from app.models import Backtest, BacktestTrade, OhlcvDaily, Strategy, Symbol
from app.services.indicator_service import load_ohlcv

log = logging.getLogger(__name__)

MIN_BARS = 5

#: Supported resampling timeframes -> pandas offset alias. "daily" = no resampling.
#: Weekly/monthly bars let the same swing strategies be tested on higher timeframes
#: without any new data (bars are aggregated from the stored dailies).
TIMEFRAMES = {"daily": None, "weekly": "W-FRI", "monthly": "ME"}


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Aggregate a daily OHLCV frame (DatetimeIndex or date index) to a higher
    timeframe. Open=first, High=max, Low=min, Close=last, Volume=sum."""
    rule = TIMEFRAMES.get(timeframe)
    if rule is None:
        return df
    idx = pd.to_datetime(pd.Index(df.index))
    agg = (df.set_axis(idx)
             .resample(rule)
             .agg({"open": "first", "high": "max", "low": "min",
                   "close": "last", "volume": "sum"})
             .dropna(subset=["open", "close"]))
    agg.index = agg.index.date
    return agg


def validate_definition(definition: dict) -> list[str]:
    """All problems with a strategy definition (empty list = valid)."""
    problems = []
    if not isinstance(definition, dict):
        return ["definition must be an object"]
    entry = definition.get("entry")
    if not entry:
        problems.append("at least one entry rule is required")
    else:
        problems += [f"entry: {p}" for p in validate_rules(entry)]
    if definition.get("exit"):
        problems += [f"exit: {p}" for p in validate_rules(definition["exit"])]

    for key in ("stop_loss_pct", "take_profit_pct", "atr_stop_mult"):
        value = definition.get(key)
        if value is not None and (not isinstance(value, (int, float))
                                  or isinstance(value, bool) or value <= 0):
            problems.append(f"{key} must be a positive number")
    mhd = definition.get("max_holding_days")
    if mhd is not None and (not isinstance(mhd, int) or mhd < 1):
        problems.append("max_holding_days must be a positive integer")
    if definition.get("atr_trail") and definition.get("atr_stop_mult") is None:
        problems.append("atr_trail requires atr_stop_mult to be set")
    exit_keys = ("stop_loss_pct", "take_profit_pct", "max_holding_days", "atr_stop_mult")
    if not definition.get("exit") and all(definition.get(k) is None for k in exit_keys):
        problems.append("strategy needs an exit: exit rules, stop_loss_pct, "
                        "take_profit_pct, atr_stop_mult or max_holding_days")
    return problems


def run_and_persist(session: Session, strategy_id: int, params: dict) -> dict:
    strategy = session.get(Strategy, strategy_id)
    if strategy is None:
        raise ValueError(f"Unknown strategy id: {strategy_id}")

    problems = validate_definition(strategy.definition)
    if problems:
        raise ValueError("Invalid strategy definition: " + "; ".join(problems))

    record = Backtest(strategy_id=strategy_id, params=params, status="RUNNING")
    session.add(record)
    session.flush()

    try:
        result_summary = _execute(session, strategy, record, params)
        session.commit()
        return result_summary
    except Exception as exc:
        record.status = "FAILED"
        record.error = str(exc)
        record.finished_at = datetime.now(timezone.utc)
        session.commit()
        log.exception("Backtest %d failed", record.id)
        raise


def _execute(session: Session, strategy: Strategy, record: Backtest, params: dict) -> dict:
    definition = strategy.definition
    from_date = date.fromisoformat(params["from"]) if params.get("from") else None
    to_date = date.fromisoformat(params["to"]) if params.get("to") else None
    timeframe = (params.get("timeframe") or "daily").lower()
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unknown timeframe '{timeframe}' (use {sorted(TIMEFRAMES)})")

    stmt = select(Symbol).where(Symbol.active)
    if params.get("tickers"):
        stmt = stmt.where(Symbol.ticker.in_([t.upper() for t in params["tickers"]]))
    symbols = session.scalars(stmt).all()
    if not symbols:
        raise ValueError("No matching symbols")

    data = {}
    earliest_stored: date | None = None
    for sym in symbols:
        # Earliest bar on record (ignoring the window) so error/coverage messages
        # can say how far back stored history actually goes.
        sym_earliest = session.scalar(
            select(func.min(OhlcvDaily.trade_date)).where(OhlcvDaily.symbol_id == sym.id))
        if sym_earliest is not None:
            earliest_stored = sym_earliest if earliest_stored is None else min(earliest_stored, sym_earliest)
        raw = load_ohlcv(session, sym.id, until=to_date)
        df = raw[raw["trade_date"] >= from_date] if from_date is not None else raw
        frame = resample_ohlcv(df.set_index("trade_date"), timeframe)
        if len(frame) < MIN_BARS:
            continue
        data[sym.ticker] = frame
    if not data:
        if earliest_stored is not None and from_date is not None:
            hint = (f"stored history only starts {earliest_stored.isoformat()}; run a sync "
                    f"with from_date={from_date.isoformat()} (or click 'Sync latest data' "
                    "with this From date) to backfill it")
        else:
            hint = "run a daily sync first"
        raise ValueError(f"No price data in the requested window — {hint} "
                         "(POST /api/v1/sync/daily)")

    # The DB only ever holds what a prior sync fetched; a "from" earlier than the oldest
    # stored bar isn't a filtering bug, it just has nothing to filter — surface it instead
    # of silently running on a shorter window than the user asked for.
    data_coverage_note = None
    if from_date is not None and earliest_stored is not None and earliest_stored > from_date:
        data_coverage_note = (
            f"Requested data from {from_date.isoformat()}, but stored history only goes back "
            f"to {earliest_stored.isoformat()} — the backtest ran on {earliest_stored.isoformat()}"
            f".. instead. Run a sync with a longer lookback to backfill further."
        )

    engine_params = BacktestParams(
        initial_capital=float(params.get("initial_capital", 1_000_000)),
        max_positions=int(params.get("max_positions", 5)),
        commission_pct=float(params.get("commission_pct", 0.05)),
        stop_loss_pct=definition.get("stop_loss_pct"),
        take_profit_pct=definition.get("take_profit_pct"),
        max_holding_days=definition.get("max_holding_days"),
        atr_stop_mult=definition.get("atr_stop_mult"),
        atr_trail=bool(definition.get("atr_trail", False)),
    )

    result = run_backtest(data, definition["entry"], definition.get("exit") or [],
                          engine_params)
    metrics = compute_metrics(result.equity_curve, result.trades,
                              engine_params.initial_capital)
    if data_coverage_note:
        metrics["data_coverage_note"] = data_coverage_note

    record.status = "SUCCESS"
    record.finished_at = datetime.now(timezone.utc)
    record.metrics = metrics
    record.equity_curve = [{"d": d.isoformat(), "v": round(float(v), 2)}
                           for d, v in result.equity_curve.items()]
    for trade in result.trades:
        session.add(BacktestTrade(
            backtest_id=record.id, ticker=trade.ticker, entry_date=trade.entry_date,
            entry_price=trade.entry_price, exit_date=trade.exit_date,
            exit_price=trade.exit_price, quantity=trade.quantity, pnl=trade.pnl,
            pnl_pct=trade.pnl_pct, exit_reason=trade.exit_reason))

    return {"backtest_id": record.id, "status": "SUCCESS", "metrics": metrics,
            "trades": len(result.trades), "symbols_tested": sorted(data.keys()),
            "timeframe": timeframe}
