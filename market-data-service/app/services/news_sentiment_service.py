"""Per-stock news sentiment scoring for the Alpha Stack.

The conviction engine used to read one cached sentiment string and map it to a
flat ±15. This module deepens that into a bounded composite:

    base sentiment  (-15..+10)  the cached LLM digest's tone
  + catalyst        ( -8..+6 )  typed, signed events (upgrade vs fraud probe)
  + velocity        ( -3..+3 )  today's headline volume vs a 7-day baseline
  + trend           ( -4..+3 )  multi-day sentiment momentum (from history)

Everything except the base sentiment is deterministic and computed from stored
rows — no LLM call at scoring time (the Alpha Stack's core design rule). The
history that powers the trend is written pre-market by `refresh_signal_news`.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AiInsight, NewsArticle, NewsSentimentHistory

log = logging.getLogger(__name__)

SENTIMENT_BASE = {"positive": 10.0, "neutral": 0.0, "mixed": -5.0, "negative": -15.0}

#: Typed catalysts carry their own sign — an upgrade and a fraud probe are not
#: the same "negative". Summed then clamped so they tilt, never dominate.
CATALYST_WEIGHT = {
    "earnings_beat": 5.0, "guidance_raise": 5.0, "upgrade": 4.0, "order_win": 4.0,
    "expansion": 3.0, "buyback": 3.0,
    "earnings_miss": -6.0, "guidance_cut": -6.0, "downgrade": -5.0,
    "management_change": -3.0, "legal": -6.0, "regulatory_action": -8.0, "fraud": -12.0,
}
#: These force a sizing veto regardless of the overall tone.
HARD_RISK = {"fraud", "regulatory_action"}

CATALYST_FLOOR, CATALYST_CAP = -8.0, 6.0
LAYER_FLOOR, LAYER_CAP = -20.0, 15.0
VELOCITY_MIN_ARTICLES = 3
VELOCITY_SPIKE_RATIO = 2.0
TREND_DAYS = 5


def _score(sentiment: str | None) -> float:
    return SENTIMENT_BASE.get(sentiment or "", 0.0)


def _score_out_of_10(points: float) -> float:
    """Map the composite layer points (LAYER_FLOOR..LAYER_CAP) onto a 0-10 scale
    with neutral (0 points) anchored at 5 — the number the UI shows and lets the
    user click through to the underlying headlines."""
    if points >= 0:
        val = 5.0 + (points / LAYER_CAP) * 5.0
    else:
        val = 5.0 + (points / abs(LAYER_FLOOR)) * 5.0
    return round(max(0.0, min(10.0, val)), 1)


def news_velocity(session: Session, symbol_id: int) -> dict:
    """Today's article count vs the trailing 7-day daily average. Falls back to
    `fetched_at` when `published_at` is missing so undated feeds still count."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=8)
    rows = session.execute(
        select(NewsArticle.published_at, NewsArticle.fetched_at)
        .where(NewsArticle.symbol_id == symbol_id)).all()

    # Compare in UTC on both sides. Article timestamps are UTC; `date.today()` is
    # the machine's local date, and in IST (UTC+5:30) those disagree between
    # 00:00 and 05:30 every day — which silently reported zero articles today and
    # killed the velocity signal each morning.
    today = datetime.now(timezone.utc).date()
    prior_counts = 0
    count_today = 0
    for published_at, fetched_at in rows:
        ts = published_at or fetched_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        day = ts.date()
        if day == today:
            count_today += 1
        elif day < today:
            prior_counts += 1

    baseline = prior_counts / 7.0
    spike = count_today / baseline if baseline > 0 else float(count_today)
    return {"count_today": count_today, "baseline": round(baseline, 2), "spike": round(spike, 2)}


def sentiment_trend(session: Session, symbol_id: int, days: int = TREND_DAYS) -> dict:
    """Direction of sentiment over the prior `days` (today excluded) plus the
    length of any current negative streak — the multi-day warning signal."""
    today = date.today()
    rows = list(session.scalars(
        select(NewsSentimentHistory)
        .where(NewsSentimentHistory.symbol_id == symbol_id,
               NewsSentimentHistory.as_of_date < today)
        .order_by(NewsSentimentHistory.as_of_date.desc())
        .limit(days)).all())

    if not rows:
        return {"direction": "stable", "consecutive_negatives": 0}

    consecutive_negatives = 0
    for r in rows:                                   # newest first
        if r.sentiment == "negative":
            consecutive_negatives += 1
        else:
            break

    recent = [float(r.score) if r.score is not None else _score(r.sentiment) for r in rows]
    avg_recent = sum(recent) / len(recent)
    newest = recent[0]
    if newest - avg_recent >= 5.0:
        direction = "improving"
    elif newest - avg_recent <= -5.0:
        direction = "deteriorating"
    else:
        direction = "stable"
    return {"direction": direction, "consecutive_negatives": consecutive_negatives}


def _catalyst_modifier(catalysts: list) -> tuple[float, bool, list[str]]:
    total, hard, types = 0.0, False, []
    for c in catalysts or []:
        ctype = (c.get("type") if isinstance(c, dict) else None) or ""
        total += CATALYST_WEIGHT.get(ctype, 0.0)
        if ctype in HARD_RISK:
            hard = True
        if ctype:
            types.append(ctype)
    return max(CATALYST_FLOOR, min(CATALYST_CAP, total)), hard, types


def news_layer(session: Session, symbol_id: int) -> dict:
    """Composite per-stock news score for the conviction engine. Read-only:
    reads the cached NEWS digest, article velocity and sentiment history."""
    row = session.get(AiInsight, (symbol_id, "NEWS"))
    content = (row.content or {}) if row is not None else {}
    sentiment = content.get("sentiment")
    catalysts = content.get("catalysts") or []

    if sentiment is None:
        return {"points": 0.0, "veto": False, "sentiment": None,
                "score_out_of_10": None,
                "note": "No news digest yet — neutral"}

    base = _score(sentiment)
    catalyst_mod, hard_risk, catalyst_types = _catalyst_modifier(catalysts)

    vel = news_velocity(session, symbol_id)
    velocity_pts = 0.0
    if vel["count_today"] >= VELOCITY_MIN_ARTICLES and vel["spike"] >= VELOCITY_SPIKE_RATIO:
        velocity_pts = 3.0 if sentiment == "positive" else -3.0 if sentiment == "negative" else 1.0

    trend = sentiment_trend(session, symbol_id)
    trend_pts = {"improving": 3.0, "deteriorating": -4.0, "stable": 0.0}[trend["direction"]]

    points = max(LAYER_FLOOR, min(LAYER_CAP,
                                  base + catalyst_mod + velocity_pts + trend_pts))
    veto = (sentiment == "negative"
            or trend["consecutive_negatives"] >= 2
            or hard_risk)

    parts = [f"digest {sentiment}"]
    if catalyst_types:
        parts.append("catalysts: " + ", ".join(catalyst_types[:3]))
    if velocity_pts:
        parts.append(f"volume spike x{vel['spike']:.1f}")
    if trend["direction"] != "stable":
        parts.append(f"trend {trend['direction']}")
    if hard_risk:
        parts.append("hard-risk catalyst")
    elif trend["consecutive_negatives"] >= 2:
        parts.append(f"{trend['consecutive_negatives']} straight negative days")
    return {"points": round(points, 1), "veto": veto, "sentiment": sentiment,
            "score_out_of_10": _score_out_of_10(points),
            "note": "News: " + "; ".join(parts)}


def record_daily_sentiment(session: Session, symbol_id: int, as_of_date: date,
                           sentiment: str | None, catalysts: list,
                           article_count: int) -> None:
    """Upsert one history row per symbol/day — the memory the trend reads."""
    row = session.get(NewsSentimentHistory, (symbol_id, as_of_date)) \
        or NewsSentimentHistory(symbol_id=symbol_id, as_of_date=as_of_date)
    row.sentiment = sentiment
    row.catalysts = catalysts or []
    row.article_count = article_count
    row.score = _score(sentiment)
    row.generated_at = datetime.now(timezone.utc)
    session.merge(row)
    session.commit()


def warm_symbol_news(session: Session, settings, symbol_id: int) -> bool:
    """Analyze-mode warm-up: make sure ONE stock has articles + a cached NEWS
    digest before it's scored, so on-demand analyses don't read an empty cache
    forever. Bounded (one symbol, one LLM call, fingerprint-cached) and entirely
    best-effort — scoring proceeds on whatever exists if any step fails.

    This is the deliberate exception to "scoring never calls an LLM": that rule
    protects the ranked stack (N symbols, latency-critical). A user asking about
    one specific stock is explicitly requesting a fresh read of it.
    Returns True if a digest exists afterwards."""
    from app.models import Symbol
    from app.services.news_service import latest_news

    sym = session.get(Symbol, symbol_id)
    if sym is None:
        return False
    has_digest = session.get(AiInsight, (symbol_id, "NEWS")) is not None
    try:
        from app.ai.narrator import llm_enabled, news_insight
        from app.services.news_service import fetch_and_store_news

        articles = latest_news(session, symbol_id)
        if not articles:
            fetch_and_store_news(session, sym)
            articles = latest_news(session, symbol_id)
        if not articles or not llm_enabled(settings):
            return has_digest

        insight = news_insight(session, settings, sym, articles) or {}
        content = insight.get("insight") if isinstance(insight, dict) else None
        content = content if isinstance(content, dict) else {}
        if content.get("sentiment"):
            # also feed the trend history so tomorrow's read has memory
            record_daily_sentiment(session, symbol_id, date.today(),
                                   content.get("sentiment"),
                                   content.get("catalysts") or [], len(articles))
            return True
        return session.get(AiInsight, (symbol_id, "NEWS")) is not None
    except Exception:                                # noqa: BLE001 — warm-up is optional
        log.warning("News warm-up failed for symbol %s", symbol_id, exc_info=True)
        session.rollback()
        return has_digest


def warm_macro(session: Session, settings) -> None:
    """Analyze-mode warm-up for the market-wide layer: if no macro digest is
    cached, build one from stored headlines (pulling the feeds first if the
    store is empty). Best-effort; one LLM call at most, fingerprint-cached."""
    from app.services.market_news_service import (cached_macro_sentiment,
                                                  latest_market_news, macro_digest,
                                                  refresh_market_news)
    try:
        if cached_macro_sentiment(session) is not None:
            return
        if not latest_market_news(session):
            refresh_market_news(session, settings)
        macro_digest(session, settings)
    except Exception:                                # noqa: BLE001
        log.warning("Macro warm-up failed", exc_info=True)
        session.rollback()


def _signal_universe(session: Session) -> set[int]:
    """Symbol ids that need a fresh pre-market news read: those with a live
    ENTRY signal, plus any currently held paper position."""
    ids: set[int] = set()
    rows = session.execute(text(
        "SELECT DISTINCT symbol_id FROM strategy_signals WHERE signal = 'ENTRY' "
        "AND as_of_date = (SELECT MAX(as_of_date) FROM strategy_signals)")).all()
    ids.update(r[0] for r in rows)
    try:
        held = session.execute(text(
            "SELECT DISTINCT symbol_id FROM paper_positions WHERE quantity <> 0")).all()
        ids.update(r[0] for r in held)
    except Exception:                                # noqa: BLE001 — paper tables optional
        log.debug("paper_positions not available for news universe", exc_info=True)
    return ids


def refresh_signal_news(session: Session, settings) -> dict:
    """Pre-market: for every signaled/held stock, refresh its news, (re)generate
    the cached digest and record today's sentiment in history. Best-effort per
    symbol so one failure never sinks the batch."""
    from app.ai.narrator import news_insight
    from app.models import Symbol
    from app.services.news_service import fetch_and_store_news, latest_news

    today = date.today()
    processed = failures = 0
    for symbol_id in _signal_universe(session):
        sym = session.get(Symbol, symbol_id)
        if sym is None:
            continue
        try:
            fetch_and_store_news(session, sym)
            articles = latest_news(session, symbol_id)
            insight = news_insight(session, settings, sym, articles) or {}
            content = insight.get("insight") if isinstance(insight, dict) else None
            content = content if isinstance(content, dict) else {}
            record_daily_sentiment(session, symbol_id, today,
                                   content.get("sentiment"),
                                   content.get("catalysts") or [], len(articles))
            processed += 1
        except Exception:                            # noqa: BLE001
            failures += 1
            log.warning("Signal news refresh failed for %s", sym.ticker, exc_info=True)
            session.rollback()
    return {"processed": processed, "failures": failures}
