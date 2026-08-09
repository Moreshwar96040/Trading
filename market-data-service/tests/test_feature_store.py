"""Point-in-time feature store.

The headline test is `test_no_lookahead_features_are_stable_when_the_future_arrives`:
a feature vector computed for date T must be byte-identical whether it is computed
on day T or replayed a year later. Any drift is a lookahead leak, and a lookahead
leak invalidates every backtest built on top of it — so this is the single most
important assertion in the suite.
"""
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.features import FEATURE_SET_VERSION, get_features, latest_feature_date
from app.models import (Fundamentals, OhlcvDaily, ScreenerSnapshotHistory, Strategy,
                        StrategySignal, Symbol)
from app.services.snapshot_service import backfill_snapshot_history


def _symbol(session: Session, ticker="TCS") -> Symbol:
    sym = Symbol(ticker=ticker, yahoo_symbol=f"{ticker}.NS", name=f"{ticker} Ltd",
                 sector="IT")
    session.add(sym)
    session.commit()
    return sym


def _prices(session: Session, sym: Symbol, n: int, start=date(2026, 1, 1),
            base=100.0, step=0.5):
    """A gently trending series — deterministic, so tests are reproducible."""
    for i in range(n):
        px = base + i * step
        session.add(OhlcvDaily(symbol_id=sym.id, trade_date=start + timedelta(days=i),
                               open=px, high=px * 1.01, low=px * 0.99, close=px,
                               adj_close=px, volume=1000 + i))
    session.commit()


# ---------- backfill ----------

def test_backfill_reconstructs_history_from_prices(session: Session):
    sym = _symbol(session)
    _prices(session, sym, 38)
    out = backfill_snapshot_history(session)
    assert out["written"] > 0
    rows = session.query(ScreenerSnapshotHistory).count()
    assert rows == out["written"]
    assert all(r.source == "BACKFILL"
               for r in session.query(ScreenerSnapshotHistory).all())


def test_backfill_is_idempotent(session: Session):
    sym = _symbol(session)
    _prices(session, sym, 34)
    first = backfill_snapshot_history(session)["written"]
    second = backfill_snapshot_history(session)["written"]
    assert first > 0 and second == 0      # nothing re-written on the second pass


# ---------- the lookahead guarantee ----------

def test_no_lookahead_features_are_stable_when_the_future_arrives(session: Session):
    """Compute features for date T. Then add a year of (wildly different) future
    bars and recompute for the SAME T. The vectors must be identical."""
    sym = _symbol(session)
    _prices(session, sym, 42)
    backfill_snapshot_history(session)

    target = date(2026, 1, 1) + timedelta(days=30)
    before = get_features(session, sym.id, target)
    assert before is not None

    # The future arrives, and it is dramatic — a crash then a spike.
    start = date(2026, 1, 1) + timedelta(days=42)
    for i in range(40):
        px = 500.0 if i % 2 == 0 else 20.0
        session.add(OhlcvDaily(symbol_id=sym.id, trade_date=start + timedelta(days=i),
                               open=px, high=px * 1.05, low=px * 0.95, close=px,
                               adj_close=px, volume=9999))
    session.commit()
    backfill_snapshot_history(session)

    after = get_features(session, sym.id, target)
    assert after is not None
    for f in ("close", "sma_50", "sma_200", "rsi_14", "atr_14", "pct_from_52w_high"):
        assert getattr(before, f) == getattr(after, f), f"{f} changed — lookahead leak"


def test_features_never_read_beyond_the_as_of_date(session: Session):
    """A date before any history exists must return None, not the nearest future row."""
    sym = _symbol(session)
    _prices(session, sym, 32)
    backfill_snapshot_history(session)
    assert get_features(session, sym.id, date(2025, 6, 1)) is None


def test_uses_the_latest_row_at_or_before_the_date(session: Session):
    """On a market holiday there is no row for that exact date — we must fall back
    to the most recent PRIOR row, never the next one."""
    sym = _symbol(session)
    _prices(session, sym, 32)
    backfill_snapshot_history(session)
    rows = sorted(r.as_of_date for r in session.query(ScreenerSnapshotHistory).all())
    assert len(rows) >= 3
    # Delete a mid-series row to simulate a market holiday, then ask for that date.
    holiday = rows[len(rows) // 2]
    session.query(ScreenerSnapshotHistory).filter_by(
        symbol_id=sym.id, as_of_date=holiday).delete(synchronize_session=False)
    session.commit()
    session.expire_all()                   # drop the identity-map copy

    v = get_features(session, sym.id, holiday)
    assert v is not None
    assert v.as_of_date == holiday         # the question we asked
    assert v.data_date < holiday           # the data we used — PRIOR, never later
    assert v.staleness_days >= 1           # and the gap is visible, not hidden


# ---------- provenance and degradation ----------

def test_historical_vectors_flag_non_reconstructable_fields(session: Session):
    """Fundamentals/ML/macro are overwritten current-state. For a past date the
    vector must SAY it is degraded rather than pretend today's values applied."""
    sym = _symbol(session)
    _prices(session, sym, 42)
    backfill_snapshot_history(session)
    past = date(2026, 1, 1) + timedelta(days=26)
    v = get_features(session, sym.id, past)
    assert v.point_in_time is False
    assert "fundamentals" in v.degraded_fields
    assert "ml_prediction" in v.degraded_fields


def test_todays_vector_is_not_degraded(session: Session):
    sym = _symbol(session)
    _prices(session, sym, 42)
    backfill_snapshot_history(session)
    v = get_features(session, sym.id, latest_feature_date(session))
    assert v.point_in_time is True and v.degraded_fields == ()


def test_strict_mode_refuses_a_degraded_vector(session: Session):
    """Research/backtest callers should get nothing rather than something wrong."""
    sym = _symbol(session)
    _prices(session, sym, 42)
    backfill_snapshot_history(session)
    past = date(2026, 1, 1) + timedelta(days=26)
    assert get_features(session, sym.id, past, strict=True) is None
    assert get_features(session, sym.id, past, strict=False) is not None


def test_vector_is_stamped_and_immutable(session: Session):
    sym = _symbol(session)
    _prices(session, sym, 32)
    backfill_snapshot_history(session)
    v = get_features(session, sym.id)
    assert v.feature_set_version == FEATURE_SET_VERSION
    import dataclasses
    try:
        v.close = 1.0                      # frozen dataclass
        raise AssertionError("FeatureVector should be immutable")
    except dataclasses.FrozenInstanceError:
        pass


# ---------- content ----------

def test_signals_are_point_in_time(session: Session):
    """A signal fired on a later date must not appear in an earlier vector."""
    sym = _symbol(session)
    _prices(session, sym, 38)
    backfill_snapshot_history(session)
    strat = Strategy(name="GC", definition={"entry": []})
    session.add(strat)
    session.flush()
    late = date(2026, 1, 1) + timedelta(days=36)
    early = date(2026, 1, 1) + timedelta(days=26)
    session.add(StrategySignal(strategy_id=strat.id, symbol_id=sym.id, signal="ENTRY",
                               as_of_date=late, close=120))
    session.commit()
    assert get_features(session, sym.id, early).signal_count == 0
    assert get_features(session, sym.id, late).signal_count == 1


def test_completeness_reflects_available_inputs(session: Session):
    sym = _symbol(session)
    _prices(session, sym, 38)
    backfill_snapshot_history(session)
    bare = get_features(session, sym.id).completeness()
    session.add(Fundamentals(symbol_id=sym.id, roe_pct=22, profit_margin_pct=15,
                             earnings_growth_pct=12, revenue_growth_pct=10,
                             debt_to_equity=0.3, pe_trailing=20))
    session.commit()
    assert get_features(session, sym.id).completeness() > bare


def test_unknown_symbol_returns_none(session: Session):
    assert get_features(session, 999_999) is None
