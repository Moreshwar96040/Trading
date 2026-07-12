"""Internal API — consumed by the Spring Boot backend only (never by the UI)."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Symbol
from app.providers.base import MarketDataProvider, ProviderError
from app.providers.yahoo import YahooProvider
from app.schemas import IngestCsvRequest, QuoteResponse, RunSummary, SeedSymbolRequest, SeedSymbolResponse, SyncRequest
from app.services.csv_ingestion import ingest_directory
from app.services.sync_service import sync_daily

log = logging.getLogger(__name__)
router = APIRouter()


def get_provider(settings: Settings = Depends(get_settings)) -> MarketDataProvider:
    return YahooProvider(throttle_seconds=settings.yahoo_throttle_seconds,
                         max_retries=settings.yahoo_max_retries,
                         backoff_seconds=settings.yahoo_backoff_seconds)


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.post("/internal/ingest/csv", response_model=RunSummary)
def ingest_csv(body: IngestCsvRequest,
               session: Session = Depends(get_session),
               settings: Settings = Depends(get_settings)) -> RunSummary:
    directory = body.directory or settings.csv_dataset_dir
    return RunSummary(**ingest_directory(session, directory))


@router.post("/internal/sync/daily", response_model=RunSummary)
def run_sync(body: SyncRequest,
             session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings),
             provider: MarketDataProvider = Depends(get_provider)) -> RunSummary:
    return RunSummary(**sync_daily(session, provider, tickers=body.tickers,
                                   default_lookback_days=settings.sync_default_lookback_days,
                                   start_date=body.from_date))


@router.post("/internal/symbols/seed", response_model=SeedSymbolResponse)
def seed_symbol(body: SeedSymbolRequest,
                session: Session = Depends(get_session),
                settings: Settings = Depends(get_settings),
                provider: MarketDataProvider = Depends(get_provider)) -> SeedSymbolResponse:
    """Validate a ticker on Yahoo Finance, insert it into symbols, and fetch historical OHLCV."""
    import yfinance as yf

    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker is required")

    existing = session.scalar(select(Symbol).where(Symbol.ticker == ticker, Symbol.active))
    if existing:
        return SeedSymbolResponse(
            id=existing.id, ticker=existing.ticker, name=existing.name,
            sector=existing.sector, exchange=existing.exchange,
            currency=existing.currency, yahoo_symbol=existing.yahoo_symbol, seeded=False,
        )

    yahoo_symbol = f"{ticker}.NS"
    try:
        info = yf.Ticker(yahoo_symbol).info
        name = info.get("longName") or info.get("shortName") if info else None
        if not name:
            raise HTTPException(status_code=404, detail=f"Symbol '{ticker}' not found on Yahoo Finance")
        sector = info.get("sector")
        currency = info.get("currency") or "INR"
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Yahoo Finance lookup failed: {exc}") from exc

    sym = Symbol(ticker=ticker, yahoo_symbol=yahoo_symbol, name=name,
                 sector=sector, exchange="NSE", currency=currency, active=True)
    session.add(sym)
    session.commit()
    session.refresh(sym)

    try:
        sync_daily(session, provider, tickers=[ticker],
                   default_lookback_days=settings.sync_default_lookback_days)
    except Exception as exc:
        log.warning("Historical data fetch failed for newly seeded %s: %s", ticker, exc)

    return SeedSymbolResponse(
        id=sym.id, ticker=sym.ticker, name=sym.name, sector=sym.sector,
        exchange=sym.exchange, currency=sym.currency, yahoo_symbol=sym.yahoo_symbol, seeded=True,
    )


@router.get("/internal/indicators/{ticker}")
def indicators(ticker: str,
               from_date: str | None = None,
               to_date: str | None = None,
               session: Session = Depends(get_session)) -> dict:
    from datetime import date as _date

    from app.services.indicator_service import indicator_series
    sym = session.scalar(select(Symbol).where(Symbol.ticker == ticker.upper(), Symbol.active))
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {ticker}")
    try:
        f = _date.fromisoformat(from_date) if from_date else None
        t = _date.fromisoformat(to_date) if to_date else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Bad date: {exc}") from exc
    return indicator_series(session, sym, f, t)


@router.post("/internal/snapshot/refresh")
def snapshot_refresh(session: Session = Depends(get_session)) -> dict:
    from app.services.snapshot_service import refresh_snapshots
    return refresh_snapshots(session)


@router.post("/internal/fundamentals/refresh")
def fundamentals_refresh(body: SyncRequest,
                         session: Session = Depends(get_session),
                         provider: MarketDataProvider = Depends(get_provider)) -> dict:
    from app.services.fundamentals_service import refresh_fundamentals
    from app.services.snapshot_service import refresh_snapshots
    result = refresh_fundamentals(session, provider, tickers=body.tickers)
    refresh_snapshots(session)   # propagate new ratios onto the screener snapshot
    return result


def _get_symbol(session: Session, ticker: str) -> Symbol:
    sym = session.scalar(select(Symbol).where(Symbol.ticker == ticker.upper(), Symbol.active))
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {ticker}")
    return sym


@router.get("/internal/news/{ticker}")
def news(ticker: str, refresh: bool = False,
         session: Session = Depends(get_session),
         settings: Settings = Depends(get_settings)) -> dict:
    """Stored headlines for a symbol plus a cached LLM digest.
    `refresh=true` pulls the latest articles from Yahoo first."""
    from app.ai.narrator import llm_enabled, news_insight
    from app.services.news_service import fetch_and_store_news, latest_news

    sym = _get_symbol(session, ticker)
    fetched = fetch_and_store_news(session, sym, settings.news_max_articles) if refresh else 0
    articles = latest_news(session, sym.id)
    if not articles and not refresh:      # first visit: fetch instead of showing nothing
        fetched = fetch_and_store_news(session, sym, settings.news_max_articles)
        articles = latest_news(session, sym.id)

    return {
        "ticker": sym.ticker,
        "fetched_new": fetched,
        "llm_enabled": llm_enabled(settings),
        "articles": [{"title": a.title, "publisher": a.publisher, "link": a.link,
                      "published_at": a.published_at.isoformat() if a.published_at else None}
                     for a in articles],
        "insight": news_insight(session, settings, sym, articles),
    }


@router.get("/internal/insights/fundamentals/{ticker}")
def fundamentals_insights(ticker: str,
                          session: Session = Depends(get_session),
                          settings: Settings = Depends(get_settings)) -> dict:
    """Plain-language LLM read of the stored fundamentals (cached until refresh)."""
    from app.ai.narrator import fundamentals_insight, llm_enabled
    from app.models import FinancialStatement, Fundamentals

    sym = _get_symbol(session, ticker)
    fundamentals = session.get(Fundamentals, sym.id)
    if fundamentals is None:
        raise HTTPException(status_code=404,
                            detail=f"No fundamentals stored for {ticker} — refresh them first")
    stmts = session.scalars(
        select(FinancialStatement).where(FinancialStatement.symbol_id == sym.id)
        .order_by(FinancialStatement.period_end.desc()).limit(4)).all()
    statement_rows = [{"period_end": s.period_end.isoformat(), "period_type": s.period_type,
                       "revenue": s.revenue, "net_income": s.net_income, "eps": s.eps}
                      for s in stmts]

    return {"ticker": sym.ticker,
            "llm_enabled": llm_enabled(settings),
            "insight": fundamentals_insight(session, settings, sym, fundamentals,
                                            statement_rows)}


@router.get("/internal/regime")
def market_regime(session: Session = Depends(get_session)) -> dict:
    """Breadth-based market regime (computed from the screener snapshot)."""
    from app.services.regime_service import compute_regime
    return compute_regime(session)


@router.get("/internal/review/leaks")
def review_leaks(session: Session = Depends(get_session),
                 settings: Settings = Depends(get_settings)) -> dict:
    """Trading-habit analytics over the paper order log + optional AI coach read."""
    from app.services.review_service import compute_leaks, leaks_narrative
    data = compute_leaks(session)
    data["narrative"] = leaks_narrative(session, settings, data)
    return data


@router.get("/internal/alpha/stack")
def alpha_stack_endpoint(ticker: str | None = None,
                         session: Session = Depends(get_session)) -> dict:
    """Alpha Stack: conviction-ranked live setups (technical+quality+news+regime+ML)."""
    from app.services.conviction_service import alpha_stack
    return alpha_stack(session, ticker=ticker)


@router.get("/internal/portfolio/health")
def portfolio_health(session: Session = Depends(get_session)) -> dict:
    """Position Guardian: proactive health checks + action queue for open positions."""
    from app.services.guardian_service import position_health
    return position_health(session)


@router.get("/internal/briefing")
def briefing(force: bool = False,
             session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings)) -> dict:
    """Morning briefing: guardian + regime + signals + held-stock news, AI-narrated."""
    from app.services.briefing_service import build_briefing
    return build_briefing(session, settings, force=force)


@router.get("/internal/ai/usage")
def ai_usage(session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings)) -> dict:
    """What the LLM insights have cost: this calendar month + all time + by kind."""
    from datetime import datetime, timezone

    from sqlalchemy import func as sqlfunc

    from app.models import AiUsage

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0,
                                                     second=0, microsecond=0)

    def summarize(rows) -> dict:
        calls, inp, out, usd = rows or (0, 0, 0, 0.0)
        usd = float(usd or 0.0)
        return {"calls": int(calls or 0), "input_tokens": int(inp or 0),
                "output_tokens": int(out or 0), "cost_usd": round(usd, 4),
                "cost_inr": round(usd * settings.usd_to_inr, 2)}

    agg = (sqlfunc.count(AiUsage.id), sqlfunc.sum(AiUsage.input_tokens),
           sqlfunc.sum(AiUsage.output_tokens), sqlfunc.sum(AiUsage.cost_usd))
    month = session.execute(select(*agg).where(AiUsage.created_at >= month_start)).one()
    total = session.execute(select(*agg)).one()
    by_kind = session.execute(
        select(AiUsage.kind, *agg).where(AiUsage.created_at >= month_start)
        .group_by(AiUsage.kind)).all()

    return {"month": summarize(month), "total": summarize(total),
            "by_kind": [{"kind": r[0], **summarize(r[1:])} for r in by_kind],
            "usd_to_inr": settings.usd_to_inr}


@router.post("/internal/ai/train")
def ai_train(body: SyncRequest, session: Session = Depends(get_session)) -> dict:
    try:
        from app.ai.service import train_all
    except ImportError as exc:
        raise HTTPException(status_code=501,
                            detail=f"scikit-learn not installed: {exc}") from exc
    return train_all(session, tickers=body.tickers)


@router.post("/internal/signals/evaluate")
def signals_evaluate(body: dict | None = None,
                     session: Session = Depends(get_session)) -> dict:
    from app.services.signal_service import evaluate_signals
    body = body or {}
    return evaluate_signals(session, strategy_ids=body.get("strategy_ids"),
                            tickers=body.get("tickers"))


@router.get("/internal/ai/risk/{ticker}")
def ai_risk(ticker: str,
            entry_price: float | None = None,
            session: Session = Depends(get_session)) -> dict:
    from app.ai.risk import InsufficientDataError, recommend_risk
    from app.services.indicator_service import load_ohlcv
    sym = session.scalar(select(Symbol).where(Symbol.ticker == ticker.upper(), Symbol.active))
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {ticker}")
    df = load_ohlcv(session, sym.id)
    try:
        rec = recommend_risk(df.set_index("trade_date"), entry_price=entry_price)
    except InsufficientDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ticker": sym.ticker, **rec.to_dict()}


@router.get("/internal/ai/ideas")
def ai_ideas(limit: int = 10, session: Session = Depends(get_session)) -> dict:
    from app.ai.ideas import build_ideas
    return build_ideas(session, limit=max(1, min(limit, 50)))


@router.post("/internal/alerts/evaluate")
def alerts_evaluate(session: Session = Depends(get_session)) -> dict:
    from app.services.alert_service import evaluate_alerts
    return evaluate_alerts(session)


@router.post("/internal/strategies/validate")
def validate_strategy(body: dict) -> dict:
    from app.backtest.service import validate_definition
    problems = validate_definition(body.get("definition", {}))
    return {"valid": not problems, "problems": problems}


@router.post("/internal/backtests/run")
def run_backtest_endpoint(body: dict, session: Session = Depends(get_session)) -> dict:
    from app.backtest.service import run_and_persist
    strategy_id = body.get("strategy_id")
    if not isinstance(strategy_id, int):
        raise HTTPException(status_code=400, detail="strategy_id (int) is required")
    try:
        return run_and_persist(session, strategy_id, body.get("params") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/internal/quotes/{ticker}", response_model=QuoteResponse)
def quote(ticker: str,
          session: Session = Depends(get_session),
          provider: MarketDataProvider = Depends(get_provider)) -> QuoteResponse:
    sym = session.scalar(select(Symbol).where(Symbol.ticker == ticker.upper(), Symbol.active))
    if sym is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {ticker}")
    try:
        q = provider.get_quote(sym.yahoo_symbol)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return QuoteResponse(ticker=sym.ticker, yahoo_symbol=sym.yahoo_symbol, price=q.price,
                         prev_close=q.prev_close, change=q.change,
                         change_pct=q.change_pct, as_of=q.as_of)
