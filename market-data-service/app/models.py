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


class OhlcvIntraday(Base):
    __tablename__ = "ohlcv_intraday"
    __table_args__ = (UniqueConstraint("symbol_id", "interval", "ts",
                                       name="uq_intraday_bar"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           nullable=False)
    interval: Mapped[str] = mapped_column(String(5), nullable=False, default="15m")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
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
    # Ichimoku (V17): tenkan = blue line, kijun = red line, cloud = senkou A/B band.
    # tk_cross_age_days is NULL unless tenkan is currently above kijun.
    tenkan_9: Mapped[float | None] = mapped_column(Numeric(14, 4))
    kijun_26: Mapped[float | None] = mapped_column(Numeric(14, 4))
    cloud_top: Mapped[float | None] = mapped_column(Numeric(14, 4))
    cloud_bottom: Mapped[float | None] = mapped_column(Numeric(14, 4))
    tk_cross_age_days: Mapped[int | None] = mapped_column(Integer)
    pct_above_cloud: Mapped[float | None] = mapped_column(Numeric(10, 4))
    ichimoku_bullish: Mapped[int | None] = mapped_column(Integer)
    # Major swing support (V18): support level + price's % distance above it.
    support: Mapped[float | None] = mapped_column(Numeric(14, 4))
    pct_from_support: Mapped[float | None] = mapped_column(Numeric(10, 4))
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


class StrategySignal(Base):
    """Live entry/exit signals per strategy, refreshed after each daily sync.
    Python-owned (it runs the rules engine); Spring reads them."""
    __tablename__ = "strategy_signals"
    __table_args__ = (UniqueConstraint("strategy_id", "symbol_id", "signal", "as_of_date",
                                       name="uq_strategy_signal"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(BigInteger,
                                             ForeignKey("strategies.id", ondelete="CASCADE"),
                                             nullable=False)
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id"), nullable=False)
    signal: Mapped[str] = mapped_column(String(8), nullable=False)      # ENTRY | EXIT
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[float | None] = mapped_column(Numeric(14, 4))
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          server_default=func.now())


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


class ConvictionHistory(Base):
    """One scored setup on one day + its eventual forward return (V19).

    The training set for adaptive weighting: features are the seven layer
    strengths recorded at scoring time, labels are forward returns filled in
    later by the labeller. Recorded for every active symbol (not just signalled
    ones) so the technical layer has enough variance to be identifiable.
    """
    __tablename__ = "conviction_history"

    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           primary_key=True)
    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)

    conviction: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_multiplier: Mapped[float | None] = mapped_column(Numeric(6, 3))
    news_veto: Mapped[bool] = mapped_column(Boolean, default=False)
    has_live_signal: Mapped[bool] = mapped_column(Boolean, default=False)

    technical_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    quality_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    news_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    momentum_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    ml_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    macro_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    regime_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))

    regime_code: Mapped[str | None] = mapped_column(String(16))
    sector: Mapped[str | None] = mapped_column(String(60))
    atr_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    data_quality: Mapped[float | None] = mapped_column(Numeric(6, 3))
    close: Mapped[float | None] = mapped_column(Numeric(14, 4))

    fwd_return_5d: Mapped[float | None] = mapped_column(Numeric(10, 4))
    fwd_return_10d: Mapped[float | None] = mapped_column(Numeric(10, 4))
    fwd_return_20d: Mapped[float | None] = mapped_column(Numeric(10, 4))
    mfe_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    mae_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    labelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                         server_default=func.now())


class AutopilotTrade(Base):
    """A paper trade the autopilot opened, plus the conviction that justified it (V20).

    Carries a COPY of the layer strengths at entry so realised P&L can be attributed
    to the score as it was, independent of conviction_history retention.
    """
    __tablename__ = "autopilot_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)

    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    target_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    paper_order_id: Mapped[int | None] = mapped_column(BigInteger)

    conviction: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(16))
    risk_multiplier: Mapped[float | None] = mapped_column(Numeric(6, 3))
    technical_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    quality_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    news_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    momentum_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    ml_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    macro_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    regime_strength: Mapped[float | None] = mapped_column(Numeric(6, 4))
    regime_code: Mapped[str | None] = mapped_column(String(16))
    sector: Mapped[str | None] = mapped_column(String(60))

    status: Mapped[str] = mapped_column(String(10), default="OPEN")
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(16, 2))
    return_pct: Mapped[float | None] = mapped_column(Numeric(10, 4))
    hold_days: Mapped[int | None] = mapped_column(Integer)
    exit_reason: Mapped[str | None] = mapped_column(String(40))

    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                        server_default=func.now())


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


class NewsArticle(Base):
    __tablename__ = "news_articles"
    __table_args__ = (UniqueConstraint("symbol_id", "external_id",
                                       name="uq_news_symbol_external"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           nullable=False)
    external_id: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(120))
    link: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarketNews(Base):
    """Market-wide headlines from configured RSS feeds (WSJ/FT/aggregators)."""
    __tablename__ = "market_news"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_market_news"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    link: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)


class AiInsight(Base):
    """Cached LLM-generated insight per (symbol, kind). Regenerated when the
    fingerprint of its inputs changes (new articles / refreshed fundamentals).
    symbol_id 0 is the account-level sentinel (e.g. kind=REVIEW), so no FK."""
    __tablename__ = "ai_insights"

    symbol_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)   # NEWS | FUNDAMENTALS
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(120), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(60))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          server_default=func.now())


class NewsSentimentHistory(Base):
    """One row per (symbol, day): the day's news sentiment, catalysts and
    article count. Written pre-market by the briefing job so the Alpha Stack
    news layer can read multi-day momentum, not just today's tone."""
    __tablename__ = "news_sentiment_history"

    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"),
                                           primary_key=True)
    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)
    sentiment: Mapped[str | None] = mapped_column(String(10))
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    catalysts: Mapped[list | None] = mapped_column(JSON)
    score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                          server_default=func.now())


class AiUsage(Base):
    """One row per Anthropic API call: tokens + cost, so the UI can show spend."""
    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
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
