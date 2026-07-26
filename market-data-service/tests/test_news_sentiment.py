from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import AiInsight, NewsArticle, NewsSentimentHistory, Symbol
from app.services.news_sentiment_service import (news_layer, news_velocity,
                                                 record_daily_sentiment,
                                                 sentiment_trend, warm_symbol_news)


class _NoLlmSettings:
    anthropic_api_key = ""


def _sym(session: Session, ticker: str = "TCS") -> Symbol:
    sym = Symbol(ticker=ticker, yahoo_symbol=f"{ticker}.NS", name=f"{ticker} Ltd", sector="IT")
    session.add(sym)
    session.commit()
    return sym


def _article(session: Session, symbol_id: int, when: datetime, ext: str) -> None:
    session.add(NewsArticle(symbol_id=symbol_id, external_id=ext, title=f"headline {ext}",
                            published_at=when, fetched_at=when))
    session.commit()


def _news_insight(session: Session, symbol_id: int, sentiment: str,
                  catalysts: list | None = None) -> None:
    session.add(AiInsight(symbol_id=symbol_id, kind="NEWS", fingerprint="x",
                          content={"sentiment": sentiment, "catalysts": catalysts or []}))
    session.commit()


def _hist(session: Session, symbol_id: int, days_ago: int, sentiment: str) -> None:
    record_daily_sentiment(session, symbol_id, date.today() - timedelta(days=days_ago),
                           sentiment, [], 0)


# ---------- velocity ----------

def test_velocity_spike_when_today_beats_baseline(session: Session):
    sym = _sym(session)
    now = datetime.now(timezone.utc)
    for i in range(3):                                  # 3 articles today, none before
        _article(session, sym.id, now, f"t{i}")
    vel = news_velocity(session, sym.id)
    assert vel["count_today"] == 3
    assert vel["spike"] >= 2.0


def test_velocity_no_spike_when_quiet(session: Session):
    sym = _sym(session)
    old = datetime.now(timezone.utc) - timedelta(days=3)
    _article(session, sym.id, old, "old")
    vel = news_velocity(session, sym.id)
    assert vel["count_today"] == 0


# ---------- trend ----------

def test_trend_deteriorating(session: Session):
    sym = _sym(session)
    _hist(session, sym.id, 3, "positive")
    _hist(session, sym.id, 2, "neutral")
    _hist(session, sym.id, 1, "negative")
    tr = sentiment_trend(session, sym.id)
    assert tr["direction"] == "deteriorating"


def test_trend_consecutive_negatives(session: Session):
    sym = _sym(session)
    _hist(session, sym.id, 2, "negative")
    _hist(session, sym.id, 1, "negative")
    tr = sentiment_trend(session, sym.id)
    assert tr["consecutive_negatives"] == 2


# ---------- composite news_layer ----------

def test_news_layer_no_digest_is_neutral(session: Session):
    sym = _sym(session)
    layer = news_layer(session, sym.id)
    assert layer["points"] == 0.0
    assert layer["veto"] is False


def test_news_layer_positive_with_upgrade_scores_up(session: Session):
    sym = _sym(session)
    _news_insight(session, sym.id, "positive", [{"type": "upgrade", "direction": "positive"}])
    layer = news_layer(session, sym.id)
    assert layer["points"] > 10.0            # base 10 + catalyst 4
    assert layer["veto"] is False


def test_news_layer_exposes_score_out_of_10(session: Session):
    sym = _sym(session)
    # no digest -> unknown score
    assert news_layer(session, sym.id)["score_out_of_10"] is None
    # positive digest -> above the neutral 5.0 anchor, within 0..10
    _news_insight(session, sym.id, "positive", [{"type": "upgrade", "direction": "positive"}])
    score = news_layer(session, sym.id)["score_out_of_10"]
    assert score is not None and 5.0 < score <= 10.0


def test_news_layer_hard_risk_catalyst_vetoes(session: Session):
    sym = _sym(session)
    _news_insight(session, sym.id, "neutral", [{"type": "fraud", "direction": "negative"}])
    layer = news_layer(session, sym.id)
    assert layer["veto"] is True


def test_news_layer_two_negative_days_vetoes(session: Session):
    sym = _sym(session)
    _hist(session, sym.id, 2, "negative")
    _hist(session, sym.id, 1, "negative")
    _news_insight(session, sym.id, "neutral")     # today looks calm, but the streak vetoes
    layer = news_layer(session, sym.id)
    assert layer["veto"] is True


# ---------- analyze-mode warm-up ----------

def test_warm_is_best_effort_never_raises(session: Session):
    """With no articles, no LLM and (in CI) no yfinance, warming must degrade
    to a no-op — scoring proceeds on an empty cache, it never crashes."""
    sym = _sym(session)
    assert warm_symbol_news(session, _NoLlmSettings(), sym.id) is False


def test_warm_without_llm_reports_existing_digest(session: Session):
    sym = _sym(session)
    now = datetime.now(timezone.utc)
    _article(session, sym.id, now, "a1")             # articles stored -> no Yahoo call
    _news_insight(session, sym.id, "positive")       # digest already cached
    assert warm_symbol_news(session, _NoLlmSettings(), sym.id) is True


def test_warm_unknown_symbol_is_false(session: Session):
    assert warm_symbol_news(session, _NoLlmSettings(), 999_999) is False


def test_news_layer_negative_today_vetoes(session: Session):
    sym = _sym(session)
    _news_insight(session, sym.id, "negative")
    layer = news_layer(session, sym.id)
    assert layer["veto"] is True
    assert layer["points"] < 0


def test_velocity_counts_todays_articles_in_utc(session: Session):
    """Regression: article timestamps are UTC but `date.today()` is local. In
    IST that disagrees until 05:30, which used to zero out today's count."""
    from datetime import datetime as _dt, timezone as _tz
    sym = _sym(session)
    just_now = _dt.now(_tz.utc)
    for i in range(3):
        _article(session, sym.id, just_now, f"u{i}")
    assert news_velocity(session, sym.id)["count_today"] == 3
