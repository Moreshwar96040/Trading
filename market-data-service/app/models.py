"""SQLAlchemy models mirroring the Flyway schema (backend/src/main/resources/db/migration).

Flyway owns DDL in production. `Base.metadata.create_all` is used only in unit tests.
"""
from datetime import date, datetime

from sqlalchemy import (JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer,
                        Numeric, String, Text, UniqueConstraint, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("ticker", "exchange", name="uq_symbols_ticker_exchange"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    yahoo_symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(60))
    exchange: Mapped[str] = mapped_column(String(10), nullable=False, default="NSE")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OhlcvDaily(Base):
    __tablename__ = "ohlcv_daily"
    __table_args__ = (UniqueConstraint("symbol_id", "trade_date", name="uq_ohlcv_symbol_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    adj_close: Mapped[float | None] = mapped_column(Numeric(14, 4))
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ScreenerSnapshot(Base):
    __tablename__ = "screener_snapshot"

    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           primary_key=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    change_1d_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    avg_volume_20: Mapped[float | None] = mapped_column(Numeric(18, 2))
    volume_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4))
    sma_20: Mapped[float | None] = mapped_column(Numeric(14, 4))
    sma_50: Mapped[float | None] = mapped_column(Numeric(14, 4))
    sma_200: Mapped[float | None] = mapped_column(Numeric(14, 4))
    ema_20: Mapped[float | None] = mapped_column(Numeric(14, 4))
    rsi_14: Mapped[float | None] = mapped_column(Numeric(7, 4))
    macd: Mapped[float | None] = mapped_column(Numeric(14, 6))
    macd_signal: Mapped[float | None] = mapped_column(Numeric(14, 6))
    macd_hist: Mapped[float | None] = mapped_column(Numeric(14, 6))
    bb_upper: Mapped[float | None] = mapped_column(Numeric(14, 4))
    bb_lower: Mapped[float | None] = mapped_column(Numeric(14, 4))
    atr_14: Mapped[float | None] = mapped_column(Numeric(14, 4))
    high_52w: Mapped[float | None] = mapped_column(Numeric(14, 4))
    low_52w: Mapped[float | None] = mapped_column(Numeric(14, 4))
    pct_from_52w_high: Mapped[float | None] = mapped_column(Numeric(10, 4))
    pct_from_52w_low: Mapped[float | None] = mapped_column(Numeric(10, 4))
    return_1m_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    return_3m_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    return_1y_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    # denormalized fundamentals (V4) — kept in sync by the snapshot refresher
    market_cap: Mapped[float | None] = mapped_column(Numeric(22, 2))
    pe_trailing: Mapped[float | None] = mapped_column(Numeric(12, 4))
    pb: Mapped[float | None] = mapped_column(Numeric(12, 4))
    dividend_yield_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    roe_pct: Mapped[float | None] = mapped_column(Numeric(9, 2))
    debt_to_equity: Mapped[float | None] = mapped_column(Numeric(10, 4))
    profit_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 2))
    revenue_growth_pct: Mapped[float | None] = mapped_column(Numeric(9, 2))
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         server_default=func.now())


class Fundamentals(Base):
    __tablename__ = "fundamentals"

    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           primary_key=True)
    market_cap: Mapped[float | None] = mapped_column(Numeric(22, 2))
    pe_trailing: Mapped[float | None] = mapped_column(Numeric(12, 4))
    pe_forward: Mapped[float | None] = mapped_column(Numeric(12, 4))
    pb: Mapped[float | None] = mapped_column(Numeric(12, 4))
    ps: Mapped[float | None] = mapped_column(Numeric(12, 4))
    dividend_yield_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    roe_pct: Mapped[float | None] = mapped_column(Numeric(9, 2))
    debt_to_equity: Mapped[float | None] = mapped_column(Numeric(10, 4))
    profit_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 2))
    operating_margin_pct: Mapped[float | None] = mapped_column(Numeric(8, 2))
    revenue_growth_pct: Mapped[float | None] = mapped_column(Numeric(9, 2))
    earnings_growth_pct: Mapped[float | None] = mapped_column(Numeric(9, 2))
    eps_trailing: Mapped[float | None] = mapped_column(Numeric(12, 4))
    book_value: Mapped[float | None] = mapped_column(Numeric(14, 4))
    beta: Mapped[float | None] = mapped_column(Numeric(8, 4))
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         server_default=func.now())


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (UniqueConstraint("symbol_id", "period_end", "period_type",
                                       name="uq_fin_stmt"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)
    revenue: Mapped[float | None] = mapped_column(Numeric(22, 2))
    operating_income: Mapped[float | None] = mapped_column(Numeric(22, 2))
    net_income: Mapped[float | None] = mapped_column(Numeric(22, 2))
    eps: Mapped[float | None] = mapped_column(Numeric(12, 4))
    total_assets: Mapped[float | None] = mapped_column(Numeric(22, 2))
    total_liabilities: Mapped[float | None] = mapped_column(Numeric(22, 2))
    shareholders_equity: Mapped[float | None] = mapped_column(Numeric(22, 2))
    operating_cash_flow: Mapped[float | None] = mapped_column(Numeric(22, 2))
    free_cash_flow: Mapped[float | None] = mapped_column(Numeric(22, 2))


class Strategy(Base):
    """Written by Spring (CRUD); Python only reads definitions to run backtests."""
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        server_default=func.now())


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(BigInteger,
                                             ForeignKey("strategies.id", ondelete="CASCADE"),
                                             nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict | None] = mapped_column(JSON)
    equity_curve: Mapped[list | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    backtest_id: Mapped[int] = mapped_column(BigInteger,
                                             ForeignKey("backtests.id", ondelete="CASCADE"),
                                             nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    pnl: Mapped[float | None] = mapped_column(Numeric(16, 2))
    pnl_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    exit_reason: Mapped[str | None] = mapped_column(String(20))


class Alert(Base):
    """Definition columns written by Spring; lifecycle columns (status/triggered_*)
    written here after each snapshot refresh. Disjoint writers by design."""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           nullable=False)
    field: Mapped[str] = mapped_column(String(30), nullable=False)
    op: Mapped[str] = mapped_column(String(5), nullable=False)
    value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        server_default=func.now())
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_value: Mapped[float | None] = mapped_column(Numeric(18, 4))


class AiPrediction(Base):
    __tablename__ = "ai_predictions"

    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           primary_key=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_return_pct: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False)
    test_direction_accuracy: Mapped[float | None] = mapped_column(Numeric(6, 2))
    test_mae_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    train_rows: Mapped[int | None] = mapped_column(Integer)
    model_name: Mapped[str | None] = mapped_column(String(60))
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        server_default=func.now())


class SyncAudit(Base):
    __tablename__ = "sync_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(15), nullable=False)
    rows_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(Text)
