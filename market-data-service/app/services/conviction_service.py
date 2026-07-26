"""The Alpha Stack: fuse technical, fundamental, news and regime into one
conviction score per stock — then size positions by it.

Two modes share the same scoring pipeline:
  - Stack mode: every symbol with a live ENTRY signal, ranked (the daily menu).
  - Analyze mode: any single ticker on demand. Without a fired signal the
    technical layer falls back to a *posture* read from the latest snapshot
    (trend structure, RSI zone, distance from the 52-week high) — clearly
    labeled, and worth at most 30 of the 40 points a real signal earns.

Scoring contract: every layer reports a *strength* in 0..1 (0.5 = neutral or
unknown, so missing data never penalises a stock) and contributes
`weight x strength`. The weights sum to 100, so conviction is a literal
percentage of the best possible setup — not an unbounded points pile.

    technical 25 | quality 25 | news 18 | momentum 14 | ml 7 | macro 6 | regime 5

Timing and business quality are equal and highest: a trigger on a poor business
and a great business with no trigger are each half a thesis. News is next (it
also holds the veto), relative strength next, and the last three are tilts.

Design rules (each guards a known failure mode):
  - Technical decides WHEN; it is the only backtestable timing layer.
  - Fundamental quality carries equal weight, so weak businesses can't be
    carried by a trigger alone.
  - News sentiment is an execution-time gate from the CACHED digest — never a
    fresh LLM call, never a backtest input. Negative news = sizing veto,
    independent of the score.
  - Conviction maps to a 0/0.5x/1x/1.5x risk multiplier at 40/55/75.
"""
import logging
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.quality_score import quality_score
from app.models import (AiPrediction, Fundamentals, ScreenerSnapshot, Symbol)

log = logging.getLogger(__name__)

#: How much each layer can contribute to conviction. They sum to 100, so the
#: score IS a percentage — no rescaling, no hidden ceiling.
#:
#: Timing and business quality are weighted equally and highest: a signal on a
#: bad business and a great business with no trigger are both half a thesis.
#: News sits just below (it's the veto/context layer), relative strength below
#: that, and the remaining three are tilts, not decisions.
LAYER_WEIGHTS = {
    "technical": 25.0,
    "quality": 25.0,
    "news": 18.0,
    "momentum": 14.0,
    "ml": 7.0,
    "macro": 6.0,
    "regime": 5.0,
}
TOTAL_WEIGHT = sum(LAYER_WEIGHTS.values())        # 100.0 — asserted in tests

#: Every layer reports "strength" in 0..1 where 0.5 means neutral/unknown, so a
#: missing input never silently penalises a stock. Contribution = weight × strength.
NEUTRAL = 0.5

SIGNAL_STRENGTH = 0.85        # one fired ENTRY
EXTRA_STRATEGY = 0.075        # each additional agreeing strategy (max 2 counted)
POSTURE_CEILING = 0.70        # snapshot posture can never outrank a real signal
POSTURE_MAX = 30.0            # raw posture points, rescaled to 0..POSTURE_CEILING
REGIME_STRENGTH = {"RISK_ON": 1.0, "PULLBACK": 0.65, "CHOP": 0.35,
                   "BEAR_RALLY": 0.2, "RISK_OFF": 0.0}
MACRO_STRENGTH = {"positive": 1.0, "neutral": 0.5, "mixed": 0.35, "negative": 0.0}
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


def _layer(breakdown: list[dict], layer: str, strength: float, note: str,
           **extra) -> float:
    """Record one layer's contribution and return it.

    `strength` is clamped to 0..1 so no layer can ever exceed its weight — the
    weights are the whole contract of the score."""
    strength = max(0.0, min(1.0, strength))
    weight = LAYER_WEIGHTS[layer]
    points = weight * strength
    breakdown.append({"layer": layer, "points": round(points, 1),
                      "max": weight, "strength": round(strength, 3),
                      "note": note, **extra})
    return points


def _score_symbol(session: Session, *, symbol_id: int, ticker: str, name: str,
                  sector: str | None, close: float | None, sig_rows: list,
                  regime: dict, regime_code: str | None,
                  macro_sentiment: str | None = None) -> dict:
    breakdown: list[dict] = []

    # -- technical: fired signal(s) or snapshot posture --
    if sig_rows:
        extra = min(len(sig_rows) - 1, 2)
        tech_strength = SIGNAL_STRENGTH + extra * EXTRA_STRATEGY
        tech_note = ((f"{len(sig_rows)} strategies agree: "
                      if len(sig_rows) > 1 else "ENTRY fired: ")
                     + ", ".join(r["strategy"] for r in sig_rows))
    else:
        snap = session.get(ScreenerSnapshot, symbol_id)
        posture_points, tech_note = _technical_posture(snap)
        tech_strength = (posture_points / POSTURE_MAX) * POSTURE_CEILING
        if close is None and snap is not None and snap.close is not None:
            close = float(snap.close)
    _layer(breakdown, "technical", tech_strength, tech_note)

    # -- fundamental quality: weighted equal to timing --
    fundamentals = session.get(Fundamentals, symbol_id)
    if fundamentals is not None:
        q = quality_score({c.name: (float(getattr(fundamentals, c.name))
                                    if getattr(fundamentals, c.name) is not None else None)
                           for c in Fundamentals.__table__.columns
                           if c.name not in ("symbol_id", "computed_at")})
        _layer(breakdown, "quality", q["score"] / 100.0,
               f"Business quality {q['score']}/100 (grade {q['grade']})")
    else:
        q = None
        _layer(breakdown, "quality", NEUTRAL,
               "No fundamentals stored — neutral (refresh them for a real read)")

    # -- news sentiment gate: composite of tone + catalysts + velocity + trend --
    from app.services.news_sentiment_service import news_layer
    news = news_layer(session, symbol_id)
    sentiment = news["sentiment"]
    news_veto = news["veto"]
    news_score = news.get("score_out_of_10")
    _layer(breakdown, "news",
           NEUTRAL if news_score is None else news_score / 10.0,
           news["note"], score_out_of_10=news_score)

    # -- momentum: relative strength vs the universe (leaders lead) --
    from app.services.momentum_service import rs_rank_for_symbol
    rs = rs_rank_for_symbol(session, symbol_id)
    _layer(breakdown, "momentum", NEUTRAL if rs is None else rs / 100.0,
           (f"Relative strength {rs:.0f}/100 vs the universe"
            + (" — a leader" if rs >= 80 else " — a laggard" if rs <= 20 else "")
            if rs is not None else "Not enough universe data for an RS rank"))

    # -- ML vote --
    pred = session.get(AiPrediction, symbol_id)
    ml_strength, ml_voted = NEUTRAL, False
    if pred is not None and pred.test_direction_accuracy is not None \
            and float(pred.test_direction_accuracy) >= MIN_ML_ACCURACY \
            and pred.direction in ("UP", "DOWN"):
        ml_strength = 1.0 if pred.direction == "UP" else 0.0
        ml_voted = True
    _layer(breakdown, "ml", ml_strength,
           (f"Model says {pred.direction} "
            f"({float(pred.test_direction_accuracy):.0f}% test accuracy)"
            if ml_voted else "Model neutral or below coin-flip — no vote"))

    # -- macro news tone (WSJ/FT/aggregated feeds via the cached digest) --
    _layer(breakdown, "macro", MACRO_STRENGTH.get(macro_sentiment or "", NEUTRAL),
           (f"Market-wide news tone reads {macro_sentiment}" if macro_sentiment
            else "No macro digest yet — refresh market news"))

    # -- regime --
    _layer(breakdown, "regime", REGIME_STRENGTH.get(regime_code or "", NEUTRAL),
           f"Market regime: {regime.get('label', 'unknown')}")

    conviction = max(0.0, min(100.0, sum(b["points"] for b in breakdown)))
    mult = 0.0 if news_veto else _risk_multiplier(conviction)
    return {
        "ticker": ticker, "name": name, "sector": sector, "close": close,
        "strategies": [{"id": r["strategy_id"], "name": r["strategy"]} for r in sig_rows],
        "has_live_signal": bool(sig_rows),
        "conviction": round(conviction),
        "risk_multiplier": mult,
        "news_veto": news_veto,
        "news_score": news_score,
        "quality": q,
        "sentiment": sentiment,
        "verdict": ("VETOED" if news_veto else
                    "HIGH" if conviction >= 75 else
                    "NORMAL" if conviction >= 55 else
                    "SMALL" if conviction >= 40 else "STAND_ASIDE"),
        "breakdown": breakdown,
    }


def alpha_stack(session: Session, ticker: str | None = None,
                settings=None) -> dict:
    """Ranked conviction for every symbol with a live ENTRY signal — or, when
    `ticker` is given, an on-demand analysis of that one stock (signal or not).

    Analyze mode self-warms its news inputs (per-stock digest + macro digest)
    so a stock you explicitly ask about never scores off an empty cache. Stack
    mode stays strictly cached-only — its inputs are warmed pre-market."""
    from app.services.regime_service import compute_regime

    regime = compute_regime(session)
    regime_code = regime.get("regime") if regime.get("status") == "OK" else None

    from app.services.market_news_service import cached_macro_sentiment

    if ticker and settings is not None:
        from app.services.news_sentiment_service import warm_macro
        warm_macro(session, settings)
    macro_sentiment = cached_macro_sentiment(session)

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

    if ticker and settings is not None:
        from app.services.news_sentiment_service import warm_symbol_news
        for symbol_id in by_symbol:                 # analyze mode: at most one
            warm_symbol_news(session, settings, symbol_id)

    setups = [
        _score_symbol(session, symbol_id=symbol_id, ticker=sig_rows[0]["ticker"],
                      name=sig_rows[0]["name"], sector=sig_rows[0]["sector"],
                      close=(float(sig_rows[0]["close"])
                             if sig_rows[0]["close"] is not None else None),
                      sig_rows=sig_rows, regime=regime, regime_code=regime_code,
                      macro_sentiment=macro_sentiment)
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
        if settings is not None:
            from app.services.news_sentiment_service import warm_symbol_news
            warm_symbol_news(session, settings, sym.id)
        setups = [_score_symbol(session, symbol_id=sym.id, ticker=sym.ticker,
                                name=sym.name, sector=sym.sector, close=None,
                                sig_rows=[], regime=regime, regime_code=regime_code,
                                macro_sentiment=macro_sentiment)]

    setups.sort(key=lambda s: s["conviction"], reverse=True)
    return {"status": "OK" if setups else "NO_SIGNALS",
            "regime": {"code": regime_code, "label": regime.get("label")},
            "setups": setups,
            "note": None if setups else
            "No live ENTRY signals — evaluate signals after a sync, or loosen strategy rules"}
