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
from app.scoring import ScoringInputs, WeightSet
from app.scoring import score as score_setup

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


#: Volatility-scaled sizing. Two names at the same conviction shouldn't carry the
#: same rupee risk if one is twice as volatile — a desk sizes inversely to vol.
#: A "normal" NSE daily ATR is ~2.5% of price; calmer names size up, wilder names
#: size down, clamped so the adjustment tilts sizing without dominating it.
VOL_BASELINE_PCT = 2.5
VOL_FACTOR_FLOOR, VOL_FACTOR_CAP = 0.6, 1.4
#: Sizing haircut per missing high-signal input (fundamentals, news digest): a
#: setup scored partly on unknowns should risk less, not the same as a fully-read one.
DQ_PENALTY = 0.85
#: Final sizing never exceeds the top conviction bucket's intent.
RISK_MULT_CAP = 1.5


#: --- Confidence: how SURE we are, as distinct from how GOOD the setup looks ---
#: Conviction and confidence answer different questions and must not be one number.
#: An 80/0.4 setup (great-looking, poorly evidenced) and a 60/0.9 setup (modest,
#: well evidenced) demand different sizing, and the old single score could not
#: express the difference.
#: Weighted dispersion at or above this counts as total disagreement.
DISPERSION_MAX = 0.35
#: A high-weight layer this far from the weighted mean, on the opposite side, is a conflict.
CONFLICT_THRESHOLD = 0.30
CONFLICT_MIN_WEIGHT = 14.0
#: Regime support: labelled history for the CURRENT regime, shrunk n/(n+k).
#: Makes the system automatically cautious in regimes it has barely seen.
REGIME_SUPPORT_K = 200
#: Confidence never reaches zero — zeroing is the veto's job, not uncertainty's.
CONFIDENCE_FLOOR = 0.15


def _consensus(breakdown: list[dict]) -> tuple[float, float]:
    """(consensus, dispersion) from the weighted spread of layer strengths.

    Conviction is a weighted mean, and a mean hides whether it came from
    agreement or from a fight. Two setups can both score 60: one where every
    layer says 0.6, another where half say 0.95 and half say 0.25. The second is
    far less trustworthy, and only dispersion reveals that.
    """
    pairs = [(b["strength"], LAYER_WEIGHTS[b["layer"]]) for b in breakdown
             if b.get("strength") is not None]
    total_w = sum(w for _, w in pairs)
    if not pairs or total_w <= 0:
        return 1.0, 0.0
    mean = sum(s * w for s, w in pairs) / total_w
    variance = sum(w * (s - mean) ** 2 for s, w in pairs) / total_w
    dispersion = variance ** 0.5
    consensus = max(0.0, 1.0 - min(1.0, dispersion / DISPERSION_MAX))
    return round(consensus, 3), round(dispersion, 4)


def _conflicts(breakdown: list[dict]) -> list[dict]:
    """High-weight layers pulling hard against the consensus.

    Surfaced as a first-class output, not a footnote: "fundamentals strong but
    news deteriorating" is a quality-trap warning a trader can act on, and it is
    invisible in a single blended score.
    """
    pairs = [(b, LAYER_WEIGHTS[b["layer"]]) for b in breakdown
             if b.get("strength") is not None]
    total_w = sum(w for _, w in pairs)
    if not pairs or total_w <= 0:
        return []
    mean = sum(b["strength"] * w for b, w in pairs) / total_w

    bulls = [b for b, w in pairs
             if w >= CONFLICT_MIN_WEIGHT and b["strength"] - mean >= CONFLICT_THRESHOLD]
    bears = [b for b, w in pairs
             if w >= CONFLICT_MIN_WEIGHT and mean - b["strength"] >= CONFLICT_THRESHOLD]
    if not bulls or not bears:
        return []                          # a one-sided outlier is not a conflict
    bull = max(bulls, key=lambda b: b["strength"])
    bear = min(bears, key=lambda b: b["strength"])
    return [{"bullish_layer": bull["layer"], "bullish_strength": bull["strength"],
             "bearish_layer": bear["layer"], "bearish_strength": bear["strength"],
             "note": (f"{bull['layer']} is strong ({bull['strength']:.2f}) while "
                      f"{bear['layer']} is weak ({bear['strength']:.2f}) — "
                      "the layers disagree")}]


def _regime_support(session: Session, regime_code: str | None) -> float:
    """How much labelled history backs scoring in the CURRENT regime.

    Shrinkage n/(n+k): with little history the term is small, confidence drops,
    and positions shrink automatically. The system is cautious exactly where it
    is ignorant — which is the whole point of separating confidence out.
    """
    if not regime_code:
        return 0.5
    try:
        from sqlalchemy import func as sqlfunc

        from app.models import ConvictionHistory
        n = session.scalar(
            select(sqlfunc.count()).select_from(ConvictionHistory)
            .where(ConvictionHistory.regime_code == regime_code,
                   ConvictionHistory.fwd_return_10d.isnot(None))) or 0
    except Exception:                      # noqa: BLE001 — table may not exist yet
        return 0.5
    return round(n / (n + REGIME_SUPPORT_K), 3)


def _volatility_factor(atr_pct: float | None) -> float:
    """Inverse-vol sizing tilt: baseline / ATR%, clamped. 1.0 when vol unknown."""
    if atr_pct is None or atr_pct <= 0:
        return 1.0
    return round(max(VOL_FACTOR_FLOOR, min(VOL_FACTOR_CAP, VOL_BASELINE_PCT / atr_pct)), 3)


def _data_quality(has_fundamentals: bool, has_news: bool) -> tuple[float, list[str]]:
    """Multiplicative sizing haircut for each absent high-signal input."""
    factor, missing = 1.0, []
    if not has_fundamentals:
        factor *= DQ_PENALTY
        missing.append("fundamentals")
    if not has_news:
        factor *= DQ_PENALTY
        missing.append("news")
    return round(factor, 3), missing


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
                  macro_sentiment: str | None = None,
                  weights: WeightSet | None = None) -> dict:
    """Resolve this symbol's inputs from the DB, then delegate to the pure engine.

    All the I/O lives here; none of it lives in the scoring maths. That split is
    what lets the same inputs be re-scored under a challenger weight set, or
    replayed from history, without a live database.
    """
    snap = session.get(ScreenerSnapshot, symbol_id)

    # -- technical: posture is only needed when no signal fired --
    posture_points, posture_note = (0.0, "")
    if not sig_rows:
        posture_points, posture_note = _technical_posture(snap)
        if close is None and snap is not None and snap.close is not None:
            close = float(snap.close)

    # -- quality --
    quality = None
    fundamentals = session.get(Fundamentals, symbol_id)
    if fundamentals is not None:
        quality = quality_score({c.name: (float(getattr(fundamentals, c.name))
                                          if getattr(fundamentals, c.name) is not None
                                          else None)
                                 for c in Fundamentals.__table__.columns
                                 if c.name not in ("symbol_id", "computed_at")})

    # -- news (composite: tone + catalysts + velocity + trend, plus the veto) --
    from app.services.news_sentiment_service import news_layer
    news = news_layer(session, symbol_id)

    # -- momentum --
    from app.services.momentum_service import rs_rank_for_symbol
    rs = rs_rank_for_symbol(session, symbol_id)

    # -- ml --
    pred = session.get(AiPrediction, symbol_id)
    ml_accuracy = (float(pred.test_direction_accuracy)
                   if pred is not None and pred.test_direction_accuracy is not None
                   else None)

    atr_pct = None
    if snap is not None and snap.atr_14 is not None \
            and snap.close is not None and float(snap.close) > 0:
        atr_pct = round(float(snap.atr_14) / float(snap.close) * 100.0, 2)

    inputs = ScoringInputs(
        ticker=ticker, name=name, sector=sector, close=close,
        signal_names=tuple(r["strategy"] for r in sig_rows),
        posture_points=posture_points, posture_note=posture_note,
        quality_score=(quality or {}).get("score"),
        quality_grade=(quality or {}).get("grade"),
        news_score_out_of_10=news.get("score_out_of_10"),
        news_note=news.get("note", ""), news_veto=bool(news.get("veto")),
        news_sentiment=news.get("sentiment"),
        rs_rank=rs,
        ml_direction=(pred.direction if pred is not None else None),
        ml_accuracy=ml_accuracy,
        macro_sentiment=macro_sentiment,
        regime_code=regime_code, regime_label=regime.get("label", "unknown"),
        atr_pct=atr_pct, regime_support=_regime_support(session, regime_code))

    result = score_setup(inputs, weights)
    return {
        "ticker": ticker, "name": name, "sector": sector, "close": close,
        "strategies": [{"id": r["strategy_id"], "name": r["strategy"]}
                       for r in sig_rows],
        "has_live_signal": bool(sig_rows),
        "conviction": result.conviction,
        "confidence": result.confidence,
        "consensus": result.consensus,
        "dispersion": result.dispersion,
        "conflicts": list(result.conflicts),
        "regime_support": result.regime_support,
        "risk_multiplier": result.risk_multiplier,
        "atr_pct": atr_pct,
        "vol_factor": result.vol_factor,
        "data_quality": result.data_quality,
        "size_note": result.size_note,
        "news_veto": result.news_veto,
        "news_score": news.get("score_out_of_10"),
        "quality": quality,
        "sentiment": news.get("sentiment"),
        "verdict": result.verdict,
        "weights_version_id": result.weights_version_id,
        "breakdown": result.layer_dicts(),
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
    from app.services.model_registry import champion_weights

    # Weights come from the registry, not from an import — that indirection is
    # what makes champion/challenger and reproducible attribution possible.
    weights = champion_weights(session)

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
                      macro_sentiment=macro_sentiment, weights=weights)
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
                                macro_sentiment=macro_sentiment, weights=weights)]

    # Attach the deterministic rationale. Pure and cheap — every setup gets an
    # explanation derived from its own arithmetic, with no LLM on this path.
    from app.ai.reasoning import build_rationale
    for setup in setups:
        setup["rationale"] = build_rationale(setup).to_dict()

    setups.sort(key=lambda s: s["conviction"], reverse=True)
    return {"status": "OK" if setups else "NO_SIGNALS",
            "regime": {"code": regime_code, "label": regime.get("label")},
            "setups": setups,
            "note": None if setups else
            "No live ENTRY signals — evaluate signals after a sync, or loosen strategy rules"}
