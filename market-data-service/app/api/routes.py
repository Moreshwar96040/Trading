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
from app.schemas import IngestCsvRequest, QuoteResponse, RunSummary, SyncRequest
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
                                   default_lookback_days=settings.sync_default_lookback_days))


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
