"""Per-symbol news articles from Yahoo Finance (via yfinance).

Fetches the latest headlines for a symbol, dedups them into `news_articles`,
and returns the stored feed newest-first. Handles both the old flat yfinance
news schema ({uuid,title,link,...}) and the new nested one ({id,content:{...}}).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NewsArticle, Symbol

log = logging.getLogger(__name__)


def _normalize(item: dict) -> dict | None:
    """yfinance news item (either schema) -> flat dict, or None if unusable."""
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    if content:                                   # new schema (yfinance >= ~0.2.50)
        title = content.get("title")
        external_id = item.get("id") or content.get("id")
        publisher = (content.get("provider") or {}).get("displayName")
        link = (content.get("canonicalUrl") or {}).get("url") \
            or (content.get("clickThroughUrl") or {}).get("url")
        published_raw = content.get("pubDate")    # ISO string
        published_at = None
        if published_raw:
            try:
                published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
            except ValueError:
                pass
    else:                                         # old flat schema
        title = item.get("title")
        external_id = item.get("uuid")
        publisher = item.get("publisher")
        link = item.get("link")
        ts = item.get("providerPublishTime")
        published_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None

    if not title or not external_id:
        return None
    return {"external_id": str(external_id)[:80], "title": str(title)[:500],
            "publisher": (publisher or None) and str(publisher)[:120],
            "link": (link or None) and str(link)[:1000], "published_at": published_at}


def _yfinance_items(symbol: Symbol, max_articles: int,
                    errors: list | None) -> list[dict]:
    """Yahoo's internal news API via yfinance. Best-effort: returns [] and
    records a reason rather than raising."""
    import yfinance as yf

    try:
        raw = yf.Ticker(symbol.yahoo_symbol).news or []
    except Exception as exc:                      # yfinance raises assorted types
        log.warning("yfinance news failed for %s: %s", symbol.ticker, exc)
        if errors is not None:
            errors.append(f"yfinance: {type(exc).__name__}: {exc}")
        return []

    out = []
    for item in raw[:max_articles]:
        norm = _normalize(item)
        if norm is not None:
            out.append(norm)
    return out


def fetch_and_store_news(session: Session, symbol: Symbol, max_articles: int = 12,
                         errors: list | None = None, settings=None) -> int:
    """Fetch headlines from every configured source and insert the new ones.

    Sources are merged, not raced: yfinance first (richest metadata when it
    works), then the keyless RSS fan-out (Google News / Bing / Yahoo RSS) which
    is what actually covers most NSE tickers. Deduped by normalized title, so
    one story syndicated across outlets is stored once.

    Returns the number of new rows. Provider errors are logged, not raised —
    stale stored news beats a failing page. Pass `errors` (a list) to receive
    per-source failure reasons so callers can explain an empty feed."""
    candidates = _yfinance_items(symbol, max_articles, errors)

    try:
        from app.config import get_settings
        from app.services.stock_news_sources import fetch_stock_feeds, title_key

        cfg = settings or get_settings()
        candidates += fetch_stock_feeds(
            symbol.ticker, symbol.name, symbol.yahoo_symbol,
            cfg.stock_news_feeds, cfg.stock_news_max_age_days, errors=errors)
    except Exception as exc:                      # noqa: BLE001 — RSS tier is optional
        log.warning("Multi-source news fan-out failed for %s: %s", symbol.ticker, exc)
        if errors is not None:
            errors.append(f"rss-fanout: {exc}")
        from app.services.stock_news_sources import title_key

    if not candidates and errors is not None:
        errors.append(f"no source returned headlines for {symbol.ticker}")

    stored = list(session.scalars(
        select(NewsArticle).where(NewsArticle.symbol_id == symbol.id)).all())
    existing_ids = {a.external_id for a in stored}
    existing_titles = {title_key(a.title) for a in stored}

    inserted = 0
    for norm in candidates:
        norm = dict(norm)
        norm.pop("source", None)
        tkey = title_key(norm["title"])
        if norm["external_id"] in existing_ids or tkey in existing_titles:
            continue
        existing_ids.add(norm["external_id"])
        existing_titles.add(tkey)
        session.add(NewsArticle(symbol_id=symbol.id, **norm))
        inserted += 1
    session.commit()
    return inserted


def latest_news(session: Session, symbol_id: int, limit: int = 20) -> list[NewsArticle]:
    return list(session.scalars(
        select(NewsArticle).where(NewsArticle.symbol_id == symbol_id)
        .order_by(NewsArticle.published_at.desc().nulls_last(),
                  NewsArticle.fetched_at.desc())
        .limit(limit)).all())
