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


def fetch_and_store_news(session: Session, symbol: Symbol, max_articles: int = 12) -> int:
    """Fetch latest headlines from Yahoo and insert the ones we don't have yet.
    Returns the number of new rows. Provider errors are logged, not raised —
    stale stored news is better than a failing page."""
    import yfinance as yf

    try:
        raw = yf.Ticker(symbol.yahoo_symbol).news or []
    except Exception as exc:                      # yfinance raises assorted types
        log.warning("News fetch failed for %s: %s", symbol.ticker, exc)
        return 0

    existing = set(session.scalars(
        select(NewsArticle.external_id).where(NewsArticle.symbol_id == symbol.id)).all())
    inserted = 0
    for item in raw[:max_articles]:
        norm = _normalize(item)
        if norm is None or norm["external_id"] in existing:
            continue
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
