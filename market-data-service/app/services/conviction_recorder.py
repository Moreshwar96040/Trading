"""Phase 0+1 of adaptive conviction: record what we scored, then label what happened.

Nothing in the Alpha Stack was ever persisted — conviction was computed in memory
and thrown away, which is why the weights have never been checked against
outcomes. This module fixes that, and it is the only part of the loop that is
time-critical: history cannot be backfilled (conviction depends on the cached
news digest and regime *as they were that day*), so every day this doesn't run
is a day of training data that no longer exists.

Two jobs:
  record_conviction()  - snapshot every active symbol's score + layer strengths
  label_outcomes()     - once enough bars have passed, attach forward returns

Design note on scope: we record EVERY active symbol, including those with no
live signal (which score via the posture read). Recording only signalled names
would leave the technical layer pinned near 0.85-1.0 with almost no variance,
and a feature that never varies cannot have its weight estimated. The
non-signal rows are what make the regression identifiable.
"""
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

#: Bars that must pass before a row can carry a given label.
HORIZONS = {"fwd_return_5d": 5, "fwd_return_10d": 10, "fwd_return_20d": 20}
#: Excursion window (best/worst move) — matches the primary 10-day horizon.
EXCURSION_BARS = 10
#: The label the weight learner optimises for.
PRIMARY_LABEL = "fwd_return_10d"


def _strengths(breakdown: list[dict]) -> dict:
    """Layer -> strength, flattened into the column names we store."""
    by_layer = {b["layer"]: b.get("strength") for b in breakdown or []}
    return {f"{layer}_strength": by_layer.get(layer)
            for layer in ("technical", "quality", "news", "momentum",
                          "ml", "macro", "regime")}


def record_conviction(session: Session, settings=None,
                      as_of: date | None = None) -> dict:
    """Score every active symbol and persist the result. Idempotent per day:
    re-running overwrites that day's rows rather than duplicating."""
    from app.models import ConvictionHistory, ScreenerSnapshot, Symbol
    from app.services.conviction_service import _score_symbol
    from app.services.market_news_service import cached_macro_sentiment
    from app.services.regime_service import compute_regime

    regime = compute_regime(session)
    regime_code = regime.get("regime") if regime.get("status") == "OK" else None
    macro_sentiment = cached_macro_sentiment(session)

    # Live ENTRY signals, so signalled names score their real technical layer.
    sig_by_symbol: dict[int, list] = {}
    for r in session.execute(text("""
        SELECT s.id AS symbol_id, s.ticker, s.name, s.sector,
               st.id AS strategy_id, st.name AS strategy, sig.close
        FROM strategy_signals sig
        JOIN symbols s ON s.id = sig.symbol_id
        JOIN strategies st ON st.id = sig.strategy_id
        WHERE sig.signal = 'ENTRY'
          AND sig.as_of_date = (SELECT MAX(as_of_date) FROM strategy_signals)
    """)).mappings().all():
        sig_by_symbol.setdefault(r["symbol_id"], []).append(dict(r))

    symbols = session.scalars(select(Symbol).where(Symbol.active)).all()
    recorded, skipped = 0, 0

    for sym in symbols:
        snap = session.get(ScreenerSnapshot, sym.id)
        if snap is None or snap.close is None:
            skipped += 1                       # nothing to score or to label against
            continue
        row_date = as_of or snap.as_of_date or date.today()
        try:
            setup = _score_symbol(
                session, symbol_id=sym.id, ticker=sym.ticker, name=sym.name,
                sector=sym.sector, close=float(snap.close),
                sig_rows=sig_by_symbol.get(sym.id, []),
                regime=regime, regime_code=regime_code,
                macro_sentiment=macro_sentiment)
        except Exception:                      # noqa: BLE001 — one bad symbol ≠ no snapshot
            log.warning("Conviction recording failed for %s", sym.ticker, exc_info=True)
            skipped += 1
            continue

        row = session.get(ConvictionHistory, (sym.id, row_date)) or ConvictionHistory(
            symbol_id=sym.id, as_of_date=row_date)
        row.conviction = setup["conviction"]
        row.verdict = setup["verdict"]
        row.risk_multiplier = setup.get("risk_multiplier")
        row.news_veto = bool(setup.get("news_veto"))
        row.has_live_signal = bool(setup.get("has_live_signal"))
        for key, value in _strengths(setup.get("breakdown")).items():
            setattr(row, key, value)
        row.regime_code = regime_code
        row.sector = sym.sector
        row.atr_pct = setup.get("atr_pct")
        row.data_quality = setup.get("data_quality")
        row.close = float(snap.close)
        # Stamp the model that produced this score — the whole point of the
        # registry is that a stored score is never ambiguous about its origin.
        row.model_version_id = setup.get("weights_version_id")
        row.recorded_at = datetime.now(timezone.utc)
        session.merge(row)
        recorded += 1

    session.commit()
    log.info("Conviction recorded: %d rows, %d skipped", recorded, skipped)
    return {"recorded": recorded, "skipped": skipped,
            "as_of": str(as_of) if as_of else None}


def label_outcomes(session: Session) -> dict:
    """Attach forward returns to rows old enough to have them.

    Pure price arithmetic from ohlcv_daily — recomputable, no lookahead risk.
    A row is only labelled once ALL bars for a horizon exist, so a partially
    matured row stays NULL rather than carrying a truncated return.
    """
    from app.models import ConvictionHistory, OhlcvDaily

    pending = session.scalars(
        select(ConvictionHistory)
        .where(ConvictionHistory.fwd_return_10d.is_(None))
        .order_by(ConvictionHistory.as_of_date)).all()
    if not pending:
        return {"labelled": 0, "pending": 0}

    labelled = 0
    for row in pending:
        if row.close is None or float(row.close) <= 0:
            continue
        entry = float(row.close)
        bars = session.execute(
            select(OhlcvDaily.trade_date, OhlcvDaily.close,
                   OhlcvDaily.high, OhlcvDaily.low)
            .where(OhlcvDaily.symbol_id == row.symbol_id,
                   OhlcvDaily.trade_date > row.as_of_date)
            .order_by(OhlcvDaily.trade_date)
            .limit(max(HORIZONS.values()))).all()

        for column, horizon in HORIZONS.items():
            if len(bars) >= horizon:
                close_then = float(bars[horizon - 1].close)
                setattr(row, column, round((close_then / entry - 1) * 100.0, 4))

        window = bars[:EXCURSION_BARS]
        if len(window) >= EXCURSION_BARS:
            highs = [float(b.high) for b in window if b.high is not None]
            lows = [float(b.low) for b in window if b.low is not None]
            if highs:
                row.mfe_pct = round((max(highs) / entry - 1) * 100.0, 4)
            if lows:
                row.mae_pct = round((min(lows) / entry - 1) * 100.0, 4)

        if getattr(row, PRIMARY_LABEL) is not None:
            row.labelled_at = datetime.now(timezone.utc)
            labelled += 1
        session.merge(row)

    session.commit()
    log.info("Conviction labelling: %d newly labelled", labelled)
    return {"labelled": labelled, "pending": len(pending) - labelled}
