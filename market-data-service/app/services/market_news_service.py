"""Market-wide news engine: multi-source RSS -> stored headlines -> AI macro read.

Sources (configurable via MARKET_NEWS_FEEDS): WSJ's official Dow Jones feed,
FT markets, Google News India business (which carries syndicated Reuters and
Bloomberg reporting), Economic Times and Mint. Honest scope note: direct
Bloomberg/Reuters/Dow Jones APIs are enterprise-licensed products — headline
feeds + syndication are what's legitimately available to individuals, and for
sentiment purposes headlines carry most of the signal.

The Claude digest (kind=MACRO, cached by headline fingerprint) classifies the
overall tape: sentiment, key market-moving events, and a one-line stance. The
Alpha Stack consumes ONLY the cached digest — conviction scoring never waits
on an LLM call.
"""
import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings

log = logging.getLogger(__name__)

MAX_PER_FEED = 15
DIGEST_HEADLINES = 30

MACRO_SYSTEM = (
    "You are a markets desk editor. You get recent market-wide headlines from "
    "multiple financial news sources (India-focused plus WSJ/FT). Respond with ONLY a "
    "JSON object, no markdown fences, keys: sentiment (one of "
    "positive/negative/neutral/mixed — the overall tone for Indian equities "
    "specifically), stance (one sentence: what this news backdrop means for an NSE "
    "swing trader today), key_events (array of max 4 short strings — the genuinely "
    "market-moving items, ignore noise), risk_flags (array of max 2 short strings for "
    "brewing macro risks, or []). Judge from headlines only; do not invent details.")


def parse_feed(xml_text: str, source: str) -> list[dict]:
    """RSS 2.0 / Atom -> [{source, title, link, published_at}]. Never raises."""
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("Feed %s: XML parse failed: %s", source, exc)
        return items

    ns_atom = "{http://www.w3.org/2005/Atom}"
    nodes = root.findall(".//item") or root.findall(f".//{ns_atom}entry")
    for node in nodes[:MAX_PER_FEED]:
        title = (node.findtext("title") or node.findtext(f"{ns_atom}title") or "").strip()
        if not title:
            continue
        link = (node.findtext("link") or "").strip()
        if not link:                                   # Atom: <link href=.../>
            link_el = node.find(f"{ns_atom}link")
            link = (link_el.get("href") or "").strip() if link_el is not None else ""
        published = None
        raw_date = (node.findtext("pubDate") or node.findtext(f"{ns_atom}updated")
                    or node.findtext(f"{ns_atom}published"))
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date.strip())
            except (TypeError, ValueError):
                try:
                    published = datetime.fromisoformat(raw_date.strip().replace("Z", "+00:00"))
                except ValueError:
                    pass
        items.append({"source": source, "title": title[:500],
                      "link": link[:1000] or None, "published_at": published})
    return items


def refresh_market_news(session: Session, settings: Settings) -> dict:
    """Fetch every configured feed, store new headlines (deduped). Best-effort."""
    import httpx

    from app.models import MarketNews

    fetched = inserted = 0
    failures: list[str] = []
    for entry in settings.market_news_feeds.split(","):
        if "|" not in entry:
            continue
        source, url = entry.split("|", 1)
        source, url = source.strip(), url.strip()
        try:
            resp = httpx.get(url, timeout=10.0, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                failures.append(f"{source}: HTTP {resp.status_code}")
                continue
            items = parse_feed(resp.text, source)
        except Exception as exc:                       # noqa: BLE001 — one bad feed ≠ no news
            failures.append(f"{source}: {exc}")
            continue
        fetched += len(items)
        for item in items:
            key = hashlib.sha256(item["title"].lower().encode()).hexdigest()[:64]
            exists = session.scalar(select(MarketNews.id)
                                    .where(MarketNews.dedup_key == key))
            if exists:
                continue
            session.add(MarketNews(dedup_key=key, **item))
            inserted += 1
        session.commit()
    return {"fetched": fetched, "inserted": inserted, "failures": failures}


def latest_market_news(session: Session, limit: int = DIGEST_HEADLINES) -> list:
    from app.models import MarketNews
    rows = list(session.scalars(
        select(MarketNews)
        .order_by(MarketNews.published_at.desc().nulls_last(),
                  MarketNews.fetched_at.desc())
        .limit(limit * 2)).all())

    # Recency filter in Python: backends disagree on tz-aware comparisons
    # (SQLite returns naive datetimes), so normalize here instead of in SQL.
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)

    def fresh(row) -> bool:
        ts = row.published_at
        if ts is None:
            return True                       # keep undated items (fetched recently)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts >= cutoff

    return [r for r in rows if fresh(r)][:limit]


def macro_digest(session: Session, settings: Settings) -> dict | None:
    """Claude's read of the market-wide tape — cached until headlines change."""
    from app.ai import narrator
    from app.models import AiInsight

    if not narrator.llm_enabled(settings):
        return None
    headlines = latest_market_news(session)
    if not headlines:
        return None

    fingerprint = hashlib.sha1(
        "|".join(h.dedup_key for h in headlines).encode()).hexdigest()[:40]
    row = session.get(AiInsight, (0, "MACRO"))
    if row is not None and row.fingerprint == fingerprint:
        return {"insight": row.content, "cached": True}

    lines = [f"- [{h.source}] {h.title}" for h in headlines]
    try:
        raw = narrator._call_claude(settings, MACRO_SYSTEM, "\n".join(lines),
                                    session=session, kind="MACRO")
        content = narrator._parse_json(raw)
    except Exception as exc:                           # noqa: BLE001 — digest is optional
        log.error("Macro digest failed: %s", exc)
        if row is not None:
            # Yesterday's read of the tape beats no read: serve the stale cache
            # and say so, instead of leaving the macro layer blind.
            return {"insight": row.content, "cached": True, "stale": True,
                    "error": str(exc)}
        return {"error": str(exc)}

    if row is None:
        row = AiInsight(symbol_id=0, kind="MACRO")
    row.content = content
    row.fingerprint = fingerprint
    row.model_name = settings.anthropic_model
    row.generated_at = datetime.now(timezone.utc)
    session.merge(row)
    session.commit()
    return {"insight": content, "cached": False}


def cached_macro_sentiment(session: Session) -> str | None:
    """Read-only peek for the Alpha Stack layer — never triggers an LLM call."""
    from app.models import AiInsight
    row = session.get(AiInsight, (0, "MACRO"))
    return (row.content or {}).get("sentiment") if row is not None else None
