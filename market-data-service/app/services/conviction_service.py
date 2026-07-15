"""The Alpha Stack: fuse technical, fundamental, news and regime into one
conviction score per stock — then size positions by it.

Two modes share the same scoring pipeline:
  - Stack mode: every symbol with a live ENTRY signal, ranked (the daily menu).
  - Analyze mode: any single ticker on demand. Without a fired signal the
    technical layer falls back to a *posture* read from the latest snapshot
    (trend structure, RSI zone, distance from the 52-week high) — clearly
    labeled, and worth at most 30 of the 40 points a real signal earns.

Design rules (each guards a known failure mode):
  - Technical decides WHEN; it is the only backtestable timing layer.
  - Fundamental quality is a FLOOR: signals on weak businesses are down-weighted.
  - News sentiment is an execution-time gate from the CACHED digest — never a
    fresh LLM call, never a backtest input. Negative news = sizing veto.
  - Regime scales everything; conviction maps to a 0/0.5x/1x/1.5x risk multiplier.
"""
import logging
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.quality_score import quality_score
from app.models import (AiInsight, AiPrediction, Fundamentals, ScreenerSnapshot,
                        Symbol)

log = logging.getLogger(__name__)

BASE_SIGNAL = 40.0            # one fired ENTRY earns this
EXTRA_STRATEGY = 8.0          # each additional agreeing strategy (max 2 counted)
POSTURE_MAX = 30.0            # snapshot posture can never outrank a real signal
REGIME_ADJ = {"RISK_ON": 10.0, "PULLBACK": 3.0, "CHOP": -8.0,
              "BEAR_RALLY": -12.0, "RISK_OFF": -15.0}
SENTIMENT_ADJ = {"positive": 10.0, "neutral": 0.0, "mixed": -5.0, "negative": -15.0}
MIN_ML_ACCURACY = 50.0


def _risk_multiplier(conviction: float) -> float:
    if conviction >= 75:
        return 1.5
    if conviction >= 55:
        return 1.0
    if conviction >= 40:
        return 0.5
    return 0.0


def _technical_posture(snap: ScreenerSnapshot | None) -> tuple[float, str]:
    """Snapshot-based technical read for stocks with no fired signal (0..30)."""
    if snap is None or snap.close is None:
        return 0.0, "No snapshot data — run a sync + snapshot refresh"
    close = float(snap.close)
    points, notes = 0.0, []
    if snap.sma_200 is not None:
        if close > float(snap.sma_200):
            points += 10
            notes.append("above 200-day")
        else:
            notes.append("below 200-day")
    if snap.sma_50 is not None:
        if close > float(snap.sma_50):
            points += 7
            notes.append("above 50-day")
        else:
            notes.append("below 50-day")
    if snap.rsi_14 is not None:
        rsi = float(snap.rsi_14)
        if 50 <= rsi <= 70:
            points += 7
            notes.append(f"RSI {rsi:.0f} (constructive)")
        elif rsi > 70:
            points += 2
            notes.append(f"RSI {rsi:.0f} (stretched)")
        else:
            notes.append(f"RSI {rsi:.0f} (weak)")
    if snap.pct_from_52w_high is not None:
        dist = float(snap.pct_from_52w_high)
        if dist > -5:
            points += 6
            notes.append("near 52-week high")
        elif dist < -25:
            notes.append(f"{abs(dist):.0f}% off its 52-week high")
    return min(points, POSTURE_MAX), "Technical posture (no live signal): " + ", ".join(notes)


def _score_symbol(session: Session, *, symbol_id: int, ticker: str, name: str,
                  sector: str | None, close: float | None, sig_rows: list,
                  regime: dict, regime_code: str | None) -> dict:
    breakdown: list[dict] = []

    # -- technical: fired signal(s) or snapshot posture --
    if sig_rows:
        extra = min(len(sig_rows) - 1, 2)
        technical = BASE_SIGNAL + extra * EXTRA_STRATEGY
        breakdown.append({
            "layer": "technical", "points": round(technical, 1),
            "note": (f"{len(sig_rows)} strategies agree: "
                     if len(sig_rows) > 1 else "ENTRY fired: ")
                    + ", ".join(r["strategy"] for r in sig_rows)})
    else:
        snap = session.get(ScreenerSnapshot, symbol_id)
        technical, note = _technical_posture(snap)
        if close is None and snap is not None and snap.close is not None:
            close = float(snap.close)
        breakdown.append({"layer": "technical", "points": round(technical, 1),
                          "note": note})

    # -- fundamental quality floor --
    fundamentals = session.get(Fundamentals, symbol_id)
    if fundamentals is not None:
        q = quality_score({c.name: (float(getattr(fundamentals, c.name))
                                    if getattr(fundamentals, c.name) is not None else None)
                           for c in Fundamentals.__table__.columns
                           if c.name not in ("symbol_id", "computed_at")})
        quality_adj = (q["score"] - 50) * 0.5              # -25 .. +25
        breakdown.append({
            "layer": "quality", "points": round(quality_adj, 1),
            "note": f"Business quality {q['score']}/100 (grade {q['grade']})"})
    else:
        q = None
        quality_adj = 0.0
        breakdown.append({"layer": "quality", "points": 0.0,
                          "note": "No fundamentals stored — neutral (refresh them for a real read)"})

    # -- news sentiment gate (cached digest only) --
    news_row = session.get(AiInsight, (symbol_id, "NEWS"))
    sentiment = (news_row.content or {}).get("sentiment") if news_row else None
    sentiment_adj = SENTIMENT_ADJ.get(sentiment or "", 0.0)
    news_veto = sentiment == "negative"
    breakdown.append({
        "layer": "news", "points": round(sentiment_adj, 1),
        "note": (f"News digest reads {sentiment}" if sentiment
                 else "No news digest yet — neutral")})

    # -- momentum: relative strength vs the universe (leaders lead) --
    from app.services.momentum_service import rs_rank_for_symbol
    rs = rs_rank_for_symbol(session, symbol_id)
    momentum_adj = 0.0 if rs is None else (rs - 50.0) / 50.0 * 12.0   # -12 .. +12
    breakdown.append({
        "layer": "momentum", "points": round(momentum_adj, 1),
        "note": (f"Relative strength {rs:.0f}/100 vs the universe"
                 + (" — a leader" if rs >= 80 else " — a laggard" if rs <= 20 else "")
                 if rs is not None else "Not enough universe data for an RS rank")})

    # -- ML vote --
    pred = session.get(AiPrediction, symbol_id)
    ml_adj = 0.0
    if pred is not None and pred.test_direction_accuracy is not None \
            and float(pred.test_direction_accuracy) >= MIN_ML_ACCURACY:
        ml_adj = 8.0 if pred.direction == "UP" else -10.0 if pred.direction == "DOWN" else 0.0
    breakdown.append({
        "layer": "ml", "points": round(ml_adj, 1),
        "note": (f"Model says {pred.direction} "
                 f"({float(pred.test_direction_accuracy):.0f}% test accuracy)"
                 if pred is not None and ml_adj != 0.0
                 else "Model neutral or below coin-flip — no vote")})

    # -- regime multiplier --
    regime_adj = REGIME_ADJ.get(regime_code or "", 0.0)
    breakdown.append({
        "layer": "regime", "points": round(regime_adj, 1),
        "note": f"Market regime: {regime.get('label', 'unknown')}"})

    conviction = max(0.0, min(100.0, technical + quality_adj + sentiment_adj
                              + momentum_adj + ml_adj + regime_adj))
    mult = 0.0 if news_veto else _risk_multiplier(conviction)
    return {
        "ticker": ticker, "name": name, "sector": sector, "close": close,
        "strategies": [{"id": r["strategy_id"], "name": r["strategy"]} for r in sig_rows],
        "has_live_signal": bool(sig_rows),
        "conviction": round(conviction),
        "risk_multiplier": mult,
        "news_veto": news_veto,
        "quality": q,
        "sentiment": sentiment,
        "verdict": ("VETOED" if news_veto else
                    "HIGH" if conviction >= 75 else
                    "NORMAL" if conviction >= 55 else
                    "SMALL" if conviction >= 40 else "STAND_ASIDE"),
        "breakdown": breakdown,
    }


def alpha_stack(session: Session, ticker: str | None = None) -> dict:
    """Ranked conviction for every symbol with a live ENTRY signal — or, when
    `ticker` is given, an on-demand analysis of that one stock (signal or not)."""
    from app.services.regime_service import compute_regime

    regime = compute_regime(session)
    regime_code = regime.get("regime") if regime.get("status") == "OK" else None

    rows = session.execute(text("""
        SELECT s.id AS symbol_id, s.ticker, s.name, s.sector,
               st.id AS strategy_id, st.name AS strategy, sig.close
        FROM strategy_signals sig
        JOIN symbols s ON s.id = sig.symbol_id
        JOIN strategies st ON st.id = sig.strategy_id
        WHERE sig.signal = 'ENTRY'
          AND sig.as_of_date = (SELECT MAX(as_of_date) FROM strategy_signals)
    """)).mappings().all()
    if ticker:
        rows = [r for r in rows if r["ticker"] == ticker.upper()]

    by_symbol: dict[int, list] = defaultdict(list)
    for r in rows:
        by_symbol[r["symbol_id"]].append(r)

    setups = [
        _score_symbol(session, symbol_id=symbol_id, ticker=sig_rows[0]["ticker"],
                      name=sig_rows[0]["name"], sector=sig_rows[0]["sector"],
                      close=(float(sig_rows[0]["close"])
                             if sig_rows[0]["close"] is not None else None),
                      sig_rows=sig_rows, regime=regime, regime_code=regime_code)
        for symbol_id, sig_rows in by_symbol.items()
    ]

    # Analyze mode: a specific ticker with no fired signal still gets a full read.
    if ticker and not setups:
        sym = session.scalar(select(Symbol).where(Symbol.ticker == ticker.upper(),
                                                  Symbol.active))
        if sym is None:
            return {"status": "UNKNOWN_SYMBOL", "regime": {"code": regime_code,
                    "label": regime.get("label")}, "setups": [],
                    "note": f"Unknown symbol: {ticker.upper()} — add it on the Screener page"}
        setups = [_score_symbol(session, symbol_id=sym.id, ticker=sym.ticker,
                                name=sym.name, sector=sym.sector, close=None,
                                sig_rows=[], regime=regime, regime_code=regime_code)]

    setups.sort(key=lambda s: s["conviction"], reverse=True)
    return {"status": "OK" if setups else "NO_SIGNALS",
            "regime": {"code": regime_code, "label": regime.get("label")},
            "setups": setups,
            "note": None if setups else
            "No live ENTRY signals — evaluate signals after a sync, or loosen strategy rules"}
