"""Market regime from breadth: what kind of tape are we trading in?

Computed from the screener snapshot (already refreshed after every sync), so it
costs nothing extra. Breadth — the % of stocks above their long-term averages —
is the classic regime read: trend strategies earn in broad uptrends and bleed in
chop, mean-reversion does the opposite. Surfacing this stops the most common
mistake: running the right strategy in the wrong market.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScreenerSnapshot


def compute_regime(session: Session) -> dict:
    rows = session.execute(
        select(ScreenerSnapshot.close, ScreenerSnapshot.sma_50, ScreenerSnapshot.sma_200,
               ScreenerSnapshot.rsi_14, ScreenerSnapshot.atr_14,
               ScreenerSnapshot.return_1m_pct, ScreenerSnapshot.as_of_date)).all()
    rows = [r for r in rows if r.close is not None]
    if not rows:
        return {"status": "NO_DATA",
                "note": "Run a sync + snapshot refresh to compute the market regime"}

    def share(pred) -> float:
        applicable = [r for r in rows if pred(r) is not None]
        if not applicable:
            return 0.0
        return sum(1 for r in applicable if pred(r)) / len(applicable) * 100.0

    above_200 = share(lambda r: None if r.sma_200 is None else float(r.close) > float(r.sma_200))
    above_50 = share(lambda r: None if r.sma_50 is None else float(r.close) > float(r.sma_50))
    rsi_vals = [float(r.rsi_14) for r in rows if r.rsi_14 is not None]
    avg_rsi = sum(rsi_vals) / len(rsi_vals) if rsi_vals else None
    atr_pcts = [float(r.atr_14) / float(r.close) * 100.0
                for r in rows if r.atr_14 is not None and float(r.close) > 0]
    avg_atr_pct = sum(atr_pcts) / len(atr_pcts) if atr_pcts else None
    ret_1m = [float(r.return_1m_pct) for r in rows if r.return_1m_pct is not None]
    avg_ret_1m = sum(ret_1m) / len(ret_1m) if ret_1m else None

    # ---- classification: long-term breadth leads, short-term breadth refines ----
    if above_200 >= 65 and above_50 >= 55:
        regime, label = "RISK_ON", "Broad uptrend"
        guidance = "Trend and breakout strategies have the wind behind them; dips are for buying, not panicking."
    elif above_200 >= 65:
        regime, label = "PULLBACK", "Uptrend, short-term pressure"
        guidance = "Long-term trend intact but short-term weak — favour pullback entries over chasing breakouts."
    elif above_200 <= 35 and above_50 <= 45:
        regime, label = "RISK_OFF", "Broad downtrend"
        guidance = "Most stocks are below their long-term averages. Long trend signals are fighting the tape — smaller size, wider skepticism."
    elif above_200 <= 35:
        regime, label = "BEAR_RALLY", "Downtrend, short-term bounce"
        guidance = "Bounce inside a downtrend — historically where breakout longs get trapped. Take profits fast."
    else:
        regime, label = "CHOP", "Mixed / range-bound"
        guidance = "No dominant trend. Trend-following signals whipsaw here; mean-reversion and patience do better."

    volatility = (None if avg_atr_pct is None else
                  "HIGH" if avg_atr_pct > 3.5 else "LOW" if avg_atr_pct < 1.5 else "NORMAL")

    return {
        "status": "OK",
        "regime": regime,
        "label": label,
        "guidance": guidance,
        "volatility": volatility,
        "breadth": {
            "pct_above_sma200": round(above_200, 1),
            "pct_above_sma50": round(above_50, 1),
            "avg_rsi": round(avg_rsi, 1) if avg_rsi is not None else None,
            "avg_atr_pct": round(avg_atr_pct, 2) if avg_atr_pct is not None else None,
            "avg_return_1m_pct": round(avg_ret_1m, 2) if avg_ret_1m is not None else None,
            "symbols": len(rows),
        },
        "as_of": max(r.as_of_date for r in rows).isoformat(),
    }
