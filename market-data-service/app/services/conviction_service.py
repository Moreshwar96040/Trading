"""The Alpha Stack: fuse technical, fundamental, news and regime into one
conviction score per fired setup — then size positions by it.

Design rules (each guards a known failure mode):
  - Technical signals decide WHEN (they are the only backtestable timing layer).
  - Fundamental quality is a FLOOR: signals on weak businesses are down-weighted.
  - News sentiment is an execution-time gate only, read from the CACHED digest
    (kind=NEWS) — never a fresh LLM call, never a backtest input (no archive =
    lookahead bait). Negative news raises a veto flag the UI must show.
  - Regime scales everything: the same setup deserves less capital in chop.
  - Conviction maps to a risk multiplier (0 / 0.5x / 1x / 1.5x of the account's
    per-trade risk). Profit is made in sizing, not in more signals.
"""
import logging
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.ai.quality_score import quality_score
from app.models import AiInsight, AiPrediction, Fundamentals, Symbol

log = logging.getLogger(__name__)

BASE_SIGNAL = 40.0            # one fired ENTRY earns this
EXTRA_STRATEGY = 8.0          # each additional agreeing strategy (max 2 counted)
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


def alpha_stack(session: Session, ticker: str | None = None) -> dict:
    """Ranked conviction for every symbol with a live ENTRY signal
    (or one symbol when `ticker` is given)."""
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

    setups = []
    for symbol_id, sig_rows in by_symbol.items():
        first = sig_rows[0]
        breakdown: list[dict] = []

        # -- technical trigger + strategy confluence --
        extra = min(len(sig_rows) - 1, 2)
        technical = BASE_SIGNAL + extra * EXTRA_STRATEGY
        breakdown.append({
            "layer": "technical", "points": round(technical, 1),
            "note": (f"{len(sig_rows)} strategies agree: "
                     if len(sig_rows) > 1 else "ENTRY fired: ")
                    + ", ".join(r["strategy"] for r in sig_rows)})

        # -- fundamental quality floor --
        fundamentals = session.get(Fundamentals, symbol_id)
        if fundamentals is not None:
            q = quality_score({c.name: (float(getattr(fundamentals, c.name))
                                        if getattr(fundamentals, c.name) is not None else None)
                               for c in Fundamentals.__table__.columns
                               if c.name not in ("symbol_id", "computed_at")})
            quality_adj = (q["score"] - 50) * 0.5          # -25 .. +25
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

        conviction = max(0.0, min(100.0,
                                  technical + quality_adj + sentiment_adj + ml_adj + regime_adj))
        mult = 0.0 if news_veto else _risk_multiplier(conviction)
        setups.append({
            "ticker": first["ticker"], "name": first["name"], "sector": first["sector"],
            "close": float(first["close"]) if first["close"] is not None else None,
            "strategies": [{"id": r["strategy_id"], "name": r["strategy"]} for r in sig_rows],
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
        })

    setups.sort(key=lambda s: s["conviction"], reverse=True)
    return {"status": "OK" if setups else "NO_SIGNALS",
            "regime": {"code": regime_code, "label": regime.get("label")},
            "setups": setups,
            "note": None if setups else
            "No live ENTRY signals — evaluate signals after a sync, or loosen strategy rules"}
