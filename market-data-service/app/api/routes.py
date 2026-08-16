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


@router.post("/internal/sync/intraday")
def run_intraday_sync(body: dict | None = None,
                      session: Session = Depends(get_session),
                      provider: MarketDataProvider = Depends(get_provider)) -> dict:
    """Pull the latest ~60 days of intraday bars (default 15m) from Yahoo."""
    from app.services.intraday_service import sync_intraday
    body = body or {}
    try:
        return sync_intraday(session, provider, tickers=body.get("tickers"),
                             interval=body.get("interval") or "15m")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    fetch_errors: list = []
    fetched = (fetch_and_store_news(session, sym, settings.news_max_articles,
                                    errors=fetch_errors) if refresh else 0)
    articles = latest_news(session, sym.id)
    if not articles and not refresh:      # first visit: fetch instead of showing nothing
        fetched = fetch_and_store_news(session, sym, settings.news_max_articles,
                                       errors=fetch_errors)
        articles = latest_news(session, sym.id)

    insight = news_insight(session, settings, sym, articles)

    # Viewing a stock's news here also feeds the Alpha Stack: record today's
    # sentiment so the conviction engine's news layer and trend see the same
    # read the user just saw, instead of the two views disagreeing.
    content = insight.get("insight") if isinstance(insight, dict) else None
    if isinstance(content, dict) and content.get("sentiment"):
        from datetime import date as _date

        from app.services.news_sentiment_service import record_daily_sentiment
        try:
            record_daily_sentiment(session, sym.id, _date.today(),
                                   content.get("sentiment"),
                                   content.get("catalysts") or [], len(articles))
        except Exception:                 # noqa: BLE001 — history is a bonus, not the response
            log.warning("Could not record sentiment history for %s", sym.ticker,
                        exc_info=True)
            session.rollback()

    return {
        "ticker": sym.ticker,
        "fetched_new": fetched,
        "fetch_error": fetch_errors[0] if fetch_errors else None,
        "llm_enabled": llm_enabled(settings),
        "articles": [{"title": a.title, "publisher": a.publisher, "link": a.link,
                      "published_at": a.published_at.isoformat() if a.published_at else None}
                     for a in articles],
        "insight": insight,
    }


@router.get("/internal/news/market")
def market_news(refresh: bool = False,
                session: Session = Depends(get_session),
                settings: Settings = Depends(get_settings)) -> dict:
    """Market-wide headlines (multi-source RSS) + cached AI macro digest."""
    from app.ai.narrator import llm_enabled
    from app.services.market_news_service import (latest_market_news, macro_digest,
                                                  refresh_market_news)
    result = refresh_market_news(session, settings) if refresh else None
    headlines = latest_market_news(session)
    if not headlines and not refresh:      # first visit: fetch instead of showing nothing
        result = refresh_market_news(session, settings)
        headlines = latest_market_news(session)
    return {
        "refresh": result,
        "llm_enabled": llm_enabled(settings),
        "headlines": [{"source": h.source, "title": h.title, "link": h.link,
                       "published_at": h.published_at.isoformat()
                       if h.published_at else None}
                      for h in headlines],
        "digest": macro_digest(session, settings),
    }


@router.post("/internal/news/refresh-all")
def refresh_all_news(session: Session = Depends(get_session),
                     settings: Settings = Depends(get_settings)) -> dict:
    """One-click news refresh — the same work the pre-market scheduler does:
    re-pull every market feed, regenerate the macro digest, then refresh
    per-stock news for signaled/held symbols. Drives the Alpha Stack's
    "Refresh news" button so a stale macro layer is fixable from where it shows."""
    from app.services.market_news_service import macro_digest, refresh_market_news
    from app.services.news_sentiment_service import refresh_signal_news

    market = refresh_market_news(session, settings)
    digest = macro_digest(session, settings) or {}
    insight = digest.get("insight") if isinstance(digest, dict) else None
    signal_news = refresh_signal_news(session, settings)
    return {
        "market": market,
        "macro_sentiment": (insight.get("sentiment")
                            if isinstance(insight, dict) else None),
        "macro_error": digest.get("error") if isinstance(digest, dict) else None,
        "signal_news": signal_news,
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


@router.get("/internal/symbols/lookup")
def symbols_lookup(q: str, session: Session = Depends(get_session)) -> dict:
    """Search ALL NSE stocks: local DB matches first, then Yahoo Finance's symbol
    search for anything not yet tracked (marked in_db=false so the UI can offer
    to add-and-analyze)."""
    import httpx

    term = q.strip()
    if not term:
        return {"results": []}

    local = session.scalars(
        select(Symbol).where(Symbol.active)
        .where((Symbol.ticker.ilike(f"%{term}%")) | (Symbol.name.ilike(f"%{term}%")))
        .limit(8)).all()
    results = [{"ticker": s.ticker, "name": s.name, "sector": s.sector, "in_db": True}
               for s in local]
    seen = {s.ticker for s in local}

    try:
        resp = httpx.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": term, "quotesCount": 10, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=6.0)
        quotes = resp.json().get("quotes", []) if resp.status_code == 200 else []
    except Exception as exc:                       # noqa: BLE001 — lookup is best-effort
        log.warning("Yahoo symbol search failed: %s", exc)
        quotes = []

    for quote_item in quotes:
        symbol = quote_item.get("symbol", "")
        if not symbol.endswith(".NS") or quote_item.get("quoteType") != "EQUITY":
            continue                                # NSE equities only
        ticker = symbol[:-3].upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        results.append({"ticker": ticker,
                        "name": quote_item.get("longname")
                        or quote_item.get("shortname") or ticker,
                        "sector": quote_item.get("sector"),
                        "in_db": False})
    return {"results": results[:12]}


@router.get("/internal/data/health")
def data_health(session: Session = Depends(get_session)) -> dict:
    """One glance: how fresh is every data source the scores depend on?"""
    from sqlalchemy import text as sqltext

    def scalar(q: str):
        try:
            return session.execute(sqltext(q)).scalar()
        except Exception:                          # noqa: BLE001 — table may not exist yet
            session.rollback()
            return None

    return {
        "symbols_active": scalar("SELECT COUNT(*) FROM symbols WHERE active") or 0,
        "daily": {
            "last_bar": str(scalar("SELECT MAX(trade_date) FROM ohlcv_daily") or ""),
            "first_bar": str(scalar("SELECT MIN(trade_date) FROM ohlcv_daily") or ""),
            "rows": scalar("SELECT COUNT(*) FROM ohlcv_daily") or 0,
        },
        "snapshot": {"as_of": str(scalar("SELECT MAX(as_of_date) FROM screener_snapshot") or "")},
        "fundamentals": {
            "symbols": scalar("SELECT COUNT(*) FROM fundamentals") or 0,
            "oldest": str(scalar("SELECT MIN(computed_at) FROM fundamentals") or ""),
        },
        "intraday": {
            "last_bar": str(scalar("SELECT MAX(ts) FROM ohlcv_intraday") or ""),
            "rows": scalar("SELECT COUNT(*) FROM ohlcv_intraday") or 0,
        },
        "signals": {"as_of": str(scalar("SELECT MAX(as_of_date) FROM strategy_signals") or "")},
        "last_sync": {
            "status": scalar("SELECT status FROM sync_audit ORDER BY id DESC LIMIT 1"),
            "finished_at": str(scalar(
                "SELECT finished_at FROM sync_audit ORDER BY id DESC LIMIT 1") or ""),
        },
    }


@router.get("/internal/edge/gates")
def edge_gates_endpoint(session: Session = Depends(get_session)) -> dict:
    """Per-strategy validation pipeline: sample -> robustness -> paper -> live edge."""
    from app.services.edge_gates import edge_gates
    return edge_gates(session)


@router.get("/internal/momentum/board")
def momentum_board_endpoint(session: Session = Depends(get_session)) -> dict:
    """Momentum Engine: sector rotation heat + relative-strength leaders."""
    from app.services.momentum_service import momentum_board
    return momentum_board(session)


@router.get("/internal/alpha/stack")
def alpha_stack_endpoint(ticker: str | None = None,
                         session: Session = Depends(get_session),
                         settings: Settings = Depends(get_settings)) -> dict:
    """Alpha Stack: conviction-ranked live setups (technical+quality+news+regime+ML).
    Single-ticker analyses self-warm their news inputs before scoring."""
    from app.services.conviction_service import alpha_stack
    return alpha_stack(session, ticker=ticker, settings=settings)


@router.get("/internal/portfolio/health")
def portfolio_health(session: Session = Depends(get_session)) -> dict:
    """Position Guardian: proactive health checks + action queue for open positions."""
    from app.services.guardian_service import position_health
    return position_health(session)


@router.post("/internal/portfolio/health")
def portfolio_health_with_live(body: dict | None = None,
                               session: Session = Depends(get_session)) -> dict:
    """Guardian over paper positions PLUS live broker holdings passed in the body:
    {"live_positions": [{"ticker","quantity","avg_cost","last_price"?,"stop_price"?}]}"""
    from app.services.guardian_service import position_health
    body = body or {}
    return position_health(session, live_positions=body.get("live_positions"))


@router.get("/internal/exness/account")
def exness_account_endpoint(settings: Settings = Depends(get_settings)) -> dict:
    """Exness/MT5 account + open FX-crypto positions with a risk action queue.
    Read-only. Returns a status (UNAVAILABLE / NOT_CONNECTED / ERROR) with a
    plain explanation rather than failing, so the UI can always render."""
    from app.services.fx_monitor import exness_account
    return exness_account(settings)


@router.get("/internal/exness/trades")
def exness_trades_endpoint(days: int = 90,
                           settings: Settings = Depends(get_settings)) -> dict:
    """Closed FX/crypto trade analysis: win rate, expectancy, per-symbol P&L and
    behavioural leaks, computed from the MT5 deal history. Read-only."""
    from app.services.fx_review import exness_trade_review
    return exness_trade_review(settings, days=days)


@router.post("/internal/portfolio/alpha-review")
def portfolio_alpha_review_endpoint(body: dict | None = None,
                                    session: Session = Depends(get_session),
                                    settings: Settings = Depends(get_settings)) -> dict:
    """Alpha Monitor: score each held stock through the Alpha Stack and recommend
    ADD / HOLD / TRIM / SELL. Body carries live broker holdings (same shape as the
    Guardian): {"live_positions": [{"ticker","quantity","avg_cost","last_price"?}]}"""
    from app.services.portfolio_monitor import portfolio_alpha_review
    body = body or {}
    return portfolio_alpha_review(session, settings, live_positions=body.get("live_positions"))


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


@router.post("/internal/conviction/propose")
def conviction_propose(horizon: str = "fwd_return_10d",
                       session: Session = Depends(get_session)) -> dict:
    """Fit candidate weights, run every validation gate, and register a SHADOW
    version if all pass. Never promotes — that stays a human decision."""
    from app.ai.calibration import propose_weights
    return propose_weights(session, horizon=horizon)


@router.get("/internal/conviction/regime-weights")
def conviction_regime_weights(horizon: str = "fwd_return_10d",
                              session: Session = Depends(get_session)) -> dict:
    """Partially-pooled weights per regime bucket, with the shrinkage applied."""
    from app.ai.calibration import learn_regime_weights
    return learn_regime_weights(session, horizon=horizon)


@router.post("/internal/adapt/run")
def adapt_run(dry_run: bool = False, session: Session = Depends(get_session),
              settings: Settings = Depends(get_settings)) -> dict:
    """Let the Alpha Stack adjust its own weights, within the approved bounds.

    `dry_run=true` reports what it *would* do and changes nothing — the right way
    to inspect the loop before enabling it.
    """
    from app.services.auto_adapt import run_auto_adaptation
    return run_auto_adaptation(session, settings, dry_run=dry_run)


@router.get("/internal/adapt/history")
def adapt_history(limit: int = 50, session: Session = Depends(get_session)) -> dict:
    """What the system changed about itself, why, and what is live per regime."""
    from app.services.auto_adapt import adaptation_history
    return adaptation_history(session, limit=min(max(limit, 1), 200))


@router.post("/internal/adapt/revert")
def adapt_revert(body: dict | None = None,
                 session: Session = Depends(get_session)) -> dict:
    """Discard automatic changes and return a scope to your approved baseline."""
    from app.services.model_registry import SCOPES, revert_to_anchor
    body = body or {}
    actor = (body.get("actor") or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required.")
    scope = body.get("scope") or "global"
    if scope not in SCOPES:
        raise HTTPException(status_code=400,
                            detail=f"scope must be one of {sorted(SCOPES)}")
    return revert_to_anchor(session, actor, scope=scope, reason=body.get("reason"))


@router.post("/internal/adapt/auto-rollback")
def adapt_auto_rollback(session: Session = Depends(get_session)) -> dict:
    """Revert any learner-promoted model that is failing on probation."""
    from app.services.circuit_breakers import auto_rollback_if_failing
    return auto_rollback_if_failing(session)


@router.get("/internal/shadow/board")
def shadow_board_endpoint(horizon: str = "fwd_return_10d",
                          session: Session = Depends(get_session)) -> dict:
    """Every shadow challenger replayed against the champion on the same history
    — the promotion decision screen."""
    from app.ai.shadow import shadow_board
    return shadow_board(session, horizon=horizon)


@router.get("/internal/shadow/{version_id}")
def shadow_evaluate(version_id: int, horizon: str = "fwd_return_10d",
                    session: Session = Depends(get_session)) -> dict:
    """Replay one registered version against the live champion."""
    from app.ai.shadow import evaluate_candidate
    return evaluate_candidate(session, version_id, horizon=horizon)


@router.get("/internal/circuit-breakers")
def circuit_breakers_endpoint(session: Session = Depends(get_session)) -> dict:
    """Conditions under which the autopilot must stop opening new positions."""
    from app.services.circuit_breakers import evaluate
    return evaluate(session)


@router.get("/internal/portfolio/plan")
def portfolio_plan(equity: float = 1_000_000.0,
                   session: Session = Depends(get_session)) -> dict:
    """Today's Alpha Stack setups turned into a book under sector, correlation
    and risk-budget caps — with a reason recorded for every rejection."""
    from app.services.conviction_service import alpha_stack
    from app.services.portfolio_constructor import build_from_setups
    if equity <= 0:
        raise HTTPException(status_code=400, detail="equity must be positive")
    stack = alpha_stack(session)
    return build_from_setups(session, stack.get("setups") or [], equity)


@router.get("/internal/models")
def models_list(kind: str = "WEIGHTS", session: Session = Depends(get_session)) -> dict:
    """Every registered model version — the governance view."""
    from app.services.model_registry import list_versions
    return list_versions(session, kind=kind)


@router.post("/internal/models/{version_id}/promote")
def models_promote(version_id: int, body: dict | None = None,
                   session: Session = Depends(get_session)) -> dict:
    """Make a SHADOW version the live CHAMPION. Requires `approved_by` — an
    unattributed promotion is exactly the silent self-modification we forbid."""
    from app.services.model_registry import promote
    body = body or {}
    approved_by = (body.get("approved_by") or "").strip()
    if not approved_by:
        raise HTTPException(status_code=400,
                            detail="approved_by is required — promotions are audited.")
    return promote(session, version_id, approved_by, body.get("reason"))


@router.post("/internal/models/rollback")
def models_rollback(body: dict | None = None,
                    session: Session = Depends(get_session)) -> dict:
    """Restore the previously retired champion — one-step, audited."""
    from app.services.model_registry import rollback
    body = body or {}
    actor = (body.get("actor") or "").strip()
    if not actor:
        raise HTTPException(status_code=400, detail="actor is required.")
    return rollback(session, actor, body.get("reason"))


@router.post("/internal/features/backfill")
def features_backfill(days: int = 400, body: dict | None = None,
                      session: Session = Depends(get_session)) -> dict:
    """Reconstruct indicator history from stored prices so past dates become
    scoreable. Safe to re-run — existing (symbol, date) rows are skipped."""
    from app.services.snapshot_service import backfill_snapshot_history
    body = body or {}
    return backfill_snapshot_history(session, days=days, tickers=body.get("tickers"))


@router.get("/internal/features/{ticker}")
def features_for(ticker: str, as_of: str | None = None,
                 session: Session = Depends(get_session)) -> dict:
    """The point-in-time feature vector behind a score — the audit view.
    Shows exactly what was knowable on a date, and which fields are degraded."""
    from dataclasses import asdict
    from datetime import date as _date

    from app.features import get_features

    sym = _get_symbol(session, ticker)
    when = None
    if as_of:
        try:
            when = _date.fromisoformat(as_of)
        except ValueError as exc:
            raise HTTPException(status_code=400,
                                detail="as_of must be YYYY-MM-DD") from exc
    vector = get_features(session, sym.id, when)
    if vector is None:
        raise HTTPException(status_code=404,
                            detail=f"No point-in-time features for {sym.ticker} "
                                   f"on or before {as_of or 'the latest date'}. "
                                   "Run POST /internal/features/backfill.")
    payload = asdict(vector)
    payload["sector"] = payload.pop("_sector", None)
    payload["completeness"] = vector.completeness()
    return payload


@router.post("/internal/conviction/record")
def conviction_record(session: Session = Depends(get_session),
                      settings: Settings = Depends(get_settings)) -> dict:
    """Snapshot today's conviction + layer strengths for every active symbol.
    This is the training data for adaptive weighting — it cannot be backfilled,
    so it must run daily."""
    from app.services.conviction_recorder import record_conviction
    return record_conviction(session, settings)


@router.post("/internal/conviction/label")
def conviction_label(session: Session = Depends(get_session)) -> dict:
    """Attach forward returns to conviction rows old enough to have them."""
    from app.services.conviction_recorder import label_outcomes
    return label_outcomes(session)


@router.get("/internal/conviction/calibration")
def conviction_calibration(horizon: str = "fwd_return_10d",
                           session: Session = Depends(get_session)) -> dict:
    """Is the Alpha Stack predictive, and what weights would the data suggest?
    Safe from day one — reports COLLECTING until enough labelled rows exist."""
    from app.ai.calibration import calibration_report
    allowed = {"fwd_return_5d", "fwd_return_10d", "fwd_return_20d"}
    if horizon not in allowed:
        raise HTTPException(status_code=400,
                            detail=f"horizon must be one of {sorted(allowed)}")
    return calibration_report(session, horizon=horizon)


@router.get("/internal/autopilot/status")
def autopilot_status_endpoint(session: Session = Depends(get_session),
                              settings: Settings = Depends(get_settings)) -> dict:
    """Open autopilot paper trades + realised P&L attributed by conviction band."""
    from app.services.autopilot import autopilot_status
    return autopilot_status(session, settings)


@router.post("/internal/autopilot/run")
def autopilot_run(session: Session = Depends(get_session),
                  settings: Settings = Depends(get_settings)) -> dict:
    """Open paper trades for today's best setups. Paper only; no-op unless
    AUTOPILOT_ENABLED=true."""
    from app.services.autopilot import reconcile_closed, run_autopilot
    result = run_autopilot(session, settings)
    result["reconciled"] = reconcile_closed(session)
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
