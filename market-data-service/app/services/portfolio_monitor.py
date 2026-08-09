"""Portfolio Alpha Monitor: run every stock you HOLD back through the Alpha Stack
and turn its live conviction into an action.

The Alpha Stack decides what to buy; this closes the loop on what you already own.
Entry conviction decays — news turns, a trend breaks, the business deteriorates —
and a position quietly becomes something you'd never open today. This scores each
holding on the same seven-layer conviction engine and maps the result to a verdict:

    SELL   thesis broken   — news veto, or conviction collapsed to STAND_ASIDE
    TRIM   thesis fading    — mediocre conviction, deteriorating news, or below 200-day
    HOLD   thesis intact    — conviction in the normal band
    ADD    thesis strengthening — high conviction, improving news, not vetoed

Decisions are deterministic from the cached conviction inputs (no LLM at decision
time — same rule as the Alpha Stack). Suggestions only: this never places an order.
"""
import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

#: Conviction bands (0-100) that gate the actions. Aligned with the Alpha Stack's
#: own verdict thresholds so a held stock and a fresh idea speak the same language.
SELL_BELOW = 40.0        # STAND_ASIDE — you would not open this today
TRIM_BELOW = 55.0        # below NORMAL — thesis is fading
ADD_AT_OR_ABOVE = 75.0   # HIGH — strong enough that adding is defensible

URGENCY_RANK = {"SELL": 0, "TRIM": 1, "ADD": 2, "HOLD": 3}


def _held_symbol_ids(session: Session, tickers: list[str]) -> dict:
    """Resolve held tickers to our symbol rows in one query (portable in_())."""
    if not tickers:
        return {}
    from app.models import Symbol
    rows = session.execute(
        select(Symbol.id, Symbol.ticker, Symbol.name, Symbol.sector)
        .where(Symbol.active, Symbol.ticker.in_([t.upper() for t in tickers]))).all()
    return {r.ticker: {"symbol_id": r.id, "ticker": r.ticker,
                       "name": r.name, "sector": r.sector} for r in rows}


def _collect_holdings(session: Session, live_positions: list[dict] | None) -> list[dict]:
    """One row per held ticker. Live (real-money) holdings take priority over paper
    for the same ticker, since that's what actually needs monitoring."""
    holdings: dict[str, dict] = {}
    try:
        for r in session.execute(text("""
            SELECT s.ticker, p.quantity, p.avg_cost
            FROM paper_positions p JOIN symbols s ON s.id = p.symbol_id
            WHERE p.quantity > 0
        """)).mappings().all():
            holdings[r["ticker"]] = {"ticker": r["ticker"], "quantity": int(r["quantity"]),
                                     "avg_cost": float(r["avg_cost"] or 0), "source": "PAPER"}
    except Exception:                              # noqa: BLE001 — paper tables optional
        log.debug("paper_positions unavailable for monitor", exc_info=True)

    for lp in live_positions or []:
        ticker = str(lp.get("ticker", "")).upper()
        if not ticker or not lp.get("quantity"):
            continue
        holdings[ticker] = {                       # live overrides paper for the same name
            "ticker": ticker, "quantity": int(lp["quantity"]),
            "avg_cost": float(lp.get("avg_cost") or 0),
            "last_price": lp.get("last_price"),
            "stop_price": lp.get("stop_price"), "source": "LIVE"}
    return list(holdings.values())


def _top_drivers(breakdown: list[dict], positive: bool, n: int = 2) -> list[str]:
    """The layers pulling conviction most up (or down), for a plain rationale."""
    scored = [(b, b["strength"] - 0.5) for b in breakdown]
    scored.sort(key=lambda x: x[1], reverse=positive)
    out = []
    for b, delta in scored[:n]:
        if (positive and delta > 0.05) or (not positive and delta < -0.05):
            out.append(b["layer"])
    return out


def _decide(setup: dict, trend: dict, holding: dict) -> dict:
    """Map a scored holding to an action + a one-line reason a human can act on."""
    conviction = setup["conviction"]
    veto = setup["news_veto"]
    deteriorating = trend.get("direction") == "deteriorating"
    improving = trend.get("direction") == "improving"

    close = setup.get("close")
    avg = holding.get("avg_cost") or 0
    pnl_pct = ((close / avg - 1) * 100.0) if (close and avg) else None

    if veto:
        action, why = "SELL", ("negative/high-risk news has vetoed this name — "
                               "the same gate that blocks new entries")
    elif conviction < SELL_BELOW:
        action, why = "SELL", (f"conviction has fallen to {conviction}/100 (stand-aside) — "
                               "you would not open this position today")
    elif conviction < TRIM_BELOW or deteriorating:
        bits = [f"conviction {conviction}/100"]
        if deteriorating:
            bits.append("news trend deteriorating")
        weak = _top_drivers(setup["breakdown"], positive=False)
        if weak:
            bits.append("weak: " + ", ".join(weak))
        action, why = "TRIM", "; ".join(bits)
    elif conviction >= ADD_AT_OR_ABOVE and not deteriorating:
        strong = _top_drivers(setup["breakdown"], positive=True)
        why = f"conviction {conviction}/100 (high)"
        if improving:
            why += ", news improving"
        if strong:
            why += " — driven by " + ", ".join(strong)
        action = "ADD"
    else:
        action, why = "HOLD", f"conviction {conviction}/100 — thesis intact, no change"

    return {"action": action, "rationale": why,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None}


# --- proactive management: not just "what", but "act now" --------------------
PROFIT_BOOK_PCT = 15.0      # a gain worth protecting once momentum stalls
STRETCHED_RSI = 70.0        # overbought — mean reversion risk
DRAWDOWN_ALERT_PCT = -8.0   # a loss deep enough to demand a stop decision
NEAR_STOP_PCT = 3.0         # within this % of a set stop = decide before the open
ATR_STOP_MULT = 2.5         # suggested risk line = close - mult x ATR


def _profit_alert(pnl_pct, conviction, trend, rsi) -> str | None:
    """Book/trim when you're up AND the edge that got you there is fading."""
    if pnl_pct is None or pnl_pct < PROFIT_BOOK_PCT:
        return None
    reasons = []
    if conviction is not None and conviction < TRIM_BELOW:
        reasons.append("conviction fading")
    if trend == "deteriorating":
        reasons.append("news softening")
    if rsi is not None and rsi >= STRETCHED_RSI:
        reasons.append(f"RSI {rsi:.0f} stretched")
    if not reasons:
        return None
    return (f"Up {pnl_pct:.0f}% and {', '.join(reasons)} — "
            "consider booking or trimming into strength.")


def _stop_alert(pnl_pct, close, atr, sma200, stop_price) -> dict | None:
    """Near a set stop, or bleeding with no stop — surface the risk line."""
    if close is None:
        return None
    suggested = round(close - ATR_STOP_MULT * atr, 2) if atr else None

    if stop_price is not None and stop_price > 0:
        if close <= stop_price:
            return {"text": f"At/below your ₹{stop_price:g} stop — honour it or "
                            "consciously re-underwrite the trade.", "urgent": True}
        dist = (close / stop_price - 1) * 100.0
        if dist <= NEAR_STOP_PCT:
            return {"text": f"{dist:.1f}% above your ₹{stop_price:g} stop — "
                            "decide before the next open.", "urgent": True}
        return None

    below_200 = sma200 is not None and close < sma200
    deep_loss = pnl_pct is not None and pnl_pct <= DRAWDOWN_ALERT_PCT
    if not (below_200 or deep_loss):
        return None
    bits = []
    if deep_loss:
        bits.append(f"down {pnl_pct:.0f}%")
    if below_200:
        bits.append("below its 200-day")
    text = "No stop set and " + " and ".join(bits) + "."
    if suggested:
        text += f" Suggested stop ₹{suggested:g} ({(suggested / close - 1) * 100:.0f}%)."
    return {"text": text, "urgent": deep_loss}


def _replacement(sector: str | None, candidates: list[dict], held: set[str]):
    """The best live Alpha Stack setup to rotate INTO — same sector first (keeps
    the book's shape), then the strongest available name. Never a held ticker,
    never a vetoed one."""
    def ok(c: dict) -> bool:
        return (c["ticker"] not in held and not c.get("news_veto")
                and c["conviction"] >= TRIM_BELOW)
    same = [c for c in candidates if ok(c) and c.get("sector") == sector]
    pool = same or [c for c in candidates if ok(c)]
    if not pool:
        return None
    best = max(pool, key=lambda c: c["conviction"])
    return {"ticker": best["ticker"], "name": best["name"],
            "sector": best.get("sector"), "conviction": best["conviction"],
            "same_sector": bool(same)}


def portfolio_alpha_review(session: Session, settings,
                           live_positions: list[dict] | None = None) -> dict:
    """Score every held stock through the Alpha Stack and recommend an action."""
    from app.services.conviction_service import _score_symbol
    from app.services.market_news_service import cached_macro_sentiment
    from app.services.news_sentiment_service import (sentiment_trend, warm_macro,
                                                     warm_symbol_news)
    from app.services.regime_service import compute_regime

    holdings = _collect_holdings(session, live_positions)
    if not holdings:
        return {"status": "NO_POSITIONS",
                "note": "No holdings to monitor — connect Upstox or open a paper position."}

    warm_macro(session, settings)
    regime = compute_regime(session)
    regime_code = regime.get("regime") if regime.get("status") == "OK" else None
    macro_sentiment = cached_macro_sentiment(session)

    meta = _held_symbol_ids(session, [h["ticker"] for h in holdings])

    # Latest ENTRY signals for held names, so a still-signalling hold scores its
    # real technical layer instead of only a posture read.
    sig_rows = session.execute(text("""
        SELECT s.id AS symbol_id, s.ticker, s.name, s.sector,
               st.id AS strategy_id, st.name AS strategy, sig.close
        FROM strategy_signals sig
        JOIN symbols s ON s.id = sig.symbol_id
        JOIN strategies st ON st.id = sig.strategy_id
        WHERE sig.signal = 'ENTRY'
          AND sig.as_of_date = (SELECT MAX(as_of_date) FROM strategy_signals)
    """)).mappings().all()
    sig_by_symbol: dict[int, list] = {}
    for r in sig_rows:
        sig_by_symbol.setdefault(r["symbol_id"], []).append(dict(r))

    # Snapshot metrics (RSI, ATR, 200-day) for the stop / profit reads.
    from app.models import ScreenerSnapshot
    snap_by_id = {row.symbol_id: row for row in session.execute(
        select(ScreenerSnapshot.symbol_id, ScreenerSnapshot.close,
               ScreenerSnapshot.atr_14, ScreenerSnapshot.rsi_14,
               ScreenerSnapshot.sma_200)
        .where(ScreenerSnapshot.symbol_id.in_([m["symbol_id"] for m in meta.values()]))
    ).all()} if meta else {}

    # Candidate pool for replacement suggestions: the ranked live Alpha Stack.
    held_tickers = {h["ticker"] for h in holdings}
    try:
        from app.services.conviction_service import alpha_stack
        candidates = alpha_stack(session).get("setups", [])
    except Exception:                              # noqa: BLE001 — replacement is a bonus
        log.warning("Replacement candidates unavailable", exc_info=True)
        candidates = []

    reviews, counts = [], {"SELL": 0, "TRIM": 0, "HOLD": 0, "ADD": 0}
    for h in holdings:
        m = meta.get(h["ticker"])
        if m is None:
            reviews.append({**h, "action": "UNKNOWN", "conviction": None,
                            "rationale": f"{h['ticker']} isn't tracked yet — "
                                         "add it on the Screener to monitor it."})
            continue
        warm_symbol_news(session, settings, m["symbol_id"])
        rows = sig_by_symbol.get(m["symbol_id"], [])
        setup = _score_symbol(
            session, symbol_id=m["symbol_id"], ticker=m["ticker"], name=m["name"],
            sector=m["sector"], close=h.get("last_price"), sig_rows=rows,
            regime=regime, regime_code=regime_code, macro_sentiment=macro_sentiment)
        trend = sentiment_trend(session, m["symbol_id"])
        decision = _decide(setup, trend, h)
        counts[decision["action"]] += 1

        # -- proactive management signals --
        snap = snap_by_id.get(m["symbol_id"])
        close = setup.get("close")
        atr = float(snap.atr_14) if snap is not None and snap.atr_14 is not None else None
        rsi = float(snap.rsi_14) if snap is not None and snap.rsi_14 is not None else None
        sma200 = float(snap.sma_200) if snap is not None and snap.sma_200 is not None else None
        pnl_pct = decision["pnl_pct"]

        alerts = []
        stop = _stop_alert(pnl_pct, close, atr, sma200, h.get("stop_price"))
        if stop:
            alerts.append({"kind": "STOP", **stop})
        profit = _profit_alert(pnl_pct, setup["conviction"], trend.get("direction"), rsi)
        if profit:
            alerts.append({"kind": "PROFIT", "text": profit, "urgent": False})

        replacement = (_replacement(m["sector"], candidates, held_tickers)
                       if decision["action"] in ("SELL", "TRIM") else None)

        reviews.append({
            "ticker": m["ticker"], "name": m["name"], "sector": m["sector"],
            "quantity": h["quantity"], "avg_cost": h["avg_cost"], "source": h["source"],
            "close": close, "rsi": round(rsi, 1) if rsi is not None else None,
            "conviction": setup["conviction"], "verdict": setup["verdict"],
            "news_veto": setup["news_veto"], "news_score": setup.get("news_score"),
            "trend": trend.get("direction"),
            "alerts": alerts, "replacement": replacement,
            **decision})

    reviews.sort(key=lambda r: URGENCY_RANK.get(r["action"], 4))
    alerts_total = sum(len(r.get("alerts", [])) for r in reviews)
    return {"status": "OK", "reviews": reviews,
            "summary": {"holdings": len(reviews), **{k.lower(): v for k, v in counts.items()},
                        "alerts": alerts_total,
                        "action_needed": counts["SELL"] + counts["TRIM"] + counts["ADD"]}}
