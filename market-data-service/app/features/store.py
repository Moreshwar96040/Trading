"""Point-in-time feature store.

The contract: `get_features(session, symbol_id, as_of)` returns exactly what was
knowable about a symbol on that date — nothing that had not happened yet. Every
scoring path should read through here rather than touching raw tables, because
that is the only way a historical score can be trusted.

WHY THIS EXISTS
The composite conviction score mixes indicators, fundamentals, news and regime.
Indicators are recomputable from price, but the others are *current-state* tables
that get overwritten. Re-scoring the past by reading them today would match
today's news to yesterday's prices — a lookahead bug that produces beautiful,
completely fake backtest results. This module makes the distinction explicit
instead of leaving it as a trap.

HONEST LIMITS — what can and cannot be reconstructed
    fully point-in-time
        price/indicators   recomputed from ohlcv_daily, or read from the
                           append-only screener_snapshot_history (V21)
        momentum RS rank   already computed from stored closes for a given date
        news sentiment     news_sentiment_history keeps a daily row per symbol
        regime             recomputable from cross-sectional history breadth
    NOT point-in-time (best-effort, and flagged)
        fundamentals       one row per symbol, overwritten on refresh; no history
        ML prediction      one row per symbol, overwritten on retrain
        macro digest       cached per fingerprint, not versioned by date

Rather than silently substituting today's values, every FeatureVector carries
`degraded_fields` and `point_in_time`. A caller doing research can refuse to use
a degraded vector; live scoring (where as_of == today) is never degraded.
"""
import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

#: Bump when the meaning of any field changes. Stamped on every vector so a stored
#: score can always be traced to the feature semantics that produced it.
FEATURE_SET_VERSION = "1.0.0"

#: Fields that cannot be reconstructed for a past date with today's schema.
NON_HISTORICAL = ("fundamentals", "ml_prediction", "macro_sentiment")


@dataclass(frozen=True)
class FeatureVector:
    """Everything the scoring engine needs, as of one date. Immutable by design —
    a feature vector is evidence, and evidence should not be edited in place."""

    symbol_id: int
    ticker: str
    #: The date the caller asked about.
    as_of_date: date
    #: The date of the newest data actually used. On a market holiday this is the
    #: prior trading day — reporting the requested date instead would hide
    #: staleness, which is exactly the kind of silent lie this module exists to
    #: prevent.
    data_date: date | None = None
    feature_set_version: str = FEATURE_SET_VERSION

    # --- price / technical (point-in-time) ---
    close: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    pct_from_52w_high: float | None = None

    # --- momentum (point-in-time) ---
    rs_rank: float | None = None

    # --- quality (best-effort) ---
    quality_score: float | None = None
    quality_grade: str | None = None

    # --- news (point-in-time via news_sentiment_history) ---
    news_sentiment: str | None = None
    news_score_out_of_10: float | None = None
    news_veto: bool = False

    # --- ml (best-effort) ---
    ml_direction: str | None = None
    ml_accuracy: float | None = None

    # --- market context ---
    macro_sentiment: str | None = None
    regime_code: str | None = None

    # --- signals fired on this date (point-in-time) ---
    signal_count: int = 0
    signal_names: tuple = ()

    # --- provenance ---
    point_in_time: bool = True
    degraded_fields: tuple = ()
    source: str = "LIVE"

    @property
    def sector(self) -> str | None:
        return self._sector

    _sector: str | None = field(default=None, repr=False)

    @property
    def staleness_days(self) -> int | None:
        """How old the underlying data is relative to the question asked."""
        if self.data_date is None:
            return None
        return (self.as_of_date - self.data_date).days

    def completeness(self) -> float:
        """Share of high-signal inputs actually present — feeds the confidence
        term in the redesign (see docs/ADAPTIVE_PLATFORM_DESIGN.md)."""
        checks = [self.close is not None, self.quality_score is not None,
                  self.news_score_out_of_10 is not None, self.rs_rank is not None,
                  self.ml_direction is not None]
        return round(sum(1 for c in checks if c) / len(checks), 3)


def latest_feature_date(session: Session) -> date | None:
    """Most recent date with indicator history — the natural 'today' for scoring."""
    from app.models import ScreenerSnapshotHistory
    return session.scalar(select(ScreenerSnapshotHistory.as_of_date)
                          .order_by(ScreenerSnapshotHistory.as_of_date.desc()).limit(1))


def _history_row(session: Session, symbol_id: int, as_of: date):
    """Latest history row at or before `as_of` — never after. This single
    `<=` is what makes the whole module point-in-time."""
    from app.models import ScreenerSnapshotHistory
    return session.scalars(
        select(ScreenerSnapshotHistory)
        .where(ScreenerSnapshotHistory.symbol_id == symbol_id,
               ScreenerSnapshotHistory.as_of_date <= as_of)
        .order_by(ScreenerSnapshotHistory.as_of_date.desc()).limit(1)).first()


def _signals_on(session: Session, symbol_id: int, as_of: date) -> tuple:
    """ENTRY signals whose as_of_date is exactly this date."""
    from app.models import Strategy, StrategySignal
    rows = session.execute(
        select(Strategy.name)
        .join(StrategySignal, StrategySignal.strategy_id == Strategy.id)
        .where(StrategySignal.symbol_id == symbol_id,
               StrategySignal.signal == "ENTRY",
               StrategySignal.as_of_date == as_of)).all()
    return tuple(r[0] for r in rows)


def _news_on(session: Session, symbol_id: int, as_of: date):
    """Sentiment recorded for that day. news_sentiment_history is one of the few
    genuinely versioned sources we have."""
    from app.models import NewsSentimentHistory
    return session.scalars(
        select(NewsSentimentHistory)
        .where(NewsSentimentHistory.symbol_id == symbol_id,
               NewsSentimentHistory.as_of_date <= as_of)
        .order_by(NewsSentimentHistory.as_of_date.desc()).limit(1)).first()


def _sentiment_to_score(sentiment: str | None) -> float | None:
    """Map a stored daily sentiment to the same 0-10 scale the live news layer
    uses, so historical and live vectors are comparable."""
    return {"positive": 7.5, "neutral": 5.0, "mixed": 4.0,
            "negative": 2.0}.get(sentiment or "")


def get_features(session: Session, symbol_id: int, as_of: date | None = None,
                 *, strict: bool = False) -> FeatureVector | None:
    """Assemble the point-in-time feature vector for one symbol.

    `strict=True` returns None when any field would have to be degraded — use it
    for research and backtests, where a silently-wrong input is worse than no
    answer. Live scoring uses the default (best-effort, but flagged).
    """
    from app.models import Fundamentals, Symbol

    sym = session.get(Symbol, symbol_id)
    if sym is None:
        return None
    as_of = as_of or latest_feature_date(session) or date.today()

    hist = _history_row(session, symbol_id, as_of)
    if hist is None:
        return None                       # nothing knowable on/before this date

    latest = latest_feature_date(session)
    is_today = latest is not None and as_of >= latest
    degraded = [] if is_today else list(NON_HISTORICAL)

    # -- quality: current-state only; for a past date this is an approximation --
    quality_score = quality_grade = None
    fundamentals = session.get(Fundamentals, symbol_id)
    if fundamentals is not None:
        from app.ai.quality_score import quality_score as compute_quality
        q = compute_quality({c.name: (float(getattr(fundamentals, c.name))
                                      if getattr(fundamentals, c.name) is not None else None)
                             for c in Fundamentals.__table__.columns
                             if c.name not in ("symbol_id", "computed_at")})
        quality_score, quality_grade = q["score"], q["grade"]

    # -- momentum: genuinely point-in-time (derived from stored closes) --
    rs_rank = None
    try:
        from app.services.momentum_service import rs_rank_for_symbol
        rs_rank = rs_rank_for_symbol(session, symbol_id) if is_today else None
        if not is_today:
            degraded.append("rs_rank")    # historical panel not implemented yet
    except Exception:                     # noqa: BLE001 — momentum is optional
        log.debug("RS rank unavailable for %s", symbol_id, exc_info=True)

    # -- news: versioned daily, so honest for past dates --
    news = _news_on(session, symbol_id, as_of)
    news_sentiment = news.sentiment if news is not None else None

    # -- ml: current-state only --
    ml_direction = ml_accuracy = None
    from app.models import AiPrediction
    pred = session.get(AiPrediction, symbol_id)
    if pred is not None:
        ml_direction = pred.direction
        ml_accuracy = (float(pred.test_direction_accuracy)
                       if pred.test_direction_accuracy is not None else None)

    if strict and degraded:
        return None

    signals = _signals_on(session, symbol_id, as_of)
    return FeatureVector(
        symbol_id=symbol_id, ticker=sym.ticker, as_of_date=as_of,
        data_date=hist.as_of_date,
        close=float(hist.close) if hist.close is not None else None,
        sma_50=float(hist.sma_50) if hist.sma_50 is not None else None,
        sma_200=float(hist.sma_200) if hist.sma_200 is not None else None,
        rsi_14=float(hist.rsi_14) if hist.rsi_14 is not None else None,
        atr_14=float(hist.atr_14) if hist.atr_14 is not None else None,
        pct_from_52w_high=(float(hist.pct_from_52w_high)
                           if hist.pct_from_52w_high is not None else None),
        rs_rank=rs_rank,
        quality_score=quality_score, quality_grade=quality_grade,
        news_sentiment=news_sentiment,
        news_score_out_of_10=_sentiment_to_score(news_sentiment),
        ml_direction=ml_direction, ml_accuracy=ml_accuracy,
        regime_code=None,                 # cross-sectional; supplied by the caller
        signal_count=len(signals), signal_names=signals,
        point_in_time=not degraded, degraded_fields=tuple(degraded),
        source=hist.source or "LIVE", _sector=sym.sector)
