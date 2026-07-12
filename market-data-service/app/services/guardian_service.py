"""Position Guardian: proactive health checks over the open paper positions.

Entering well is half the job; this module does the other half. After every
sync (or on demand) it inspects each open position against the latest snapshot
and produces an *action queue* — concrete, prioritized things to decide today:

  - position has no stop                       -> unbounded risk (high)
  - close within striking distance of the stop -> decide before tomorrow (high)
  - strategy fired EXIT but you still hold     -> plan says leave (high)
  - profit + ATR says the stop can ratchet up  -> suggested new stop (medium)
  - close within reach of the target           -> take-profit decision (medium)
  - price below its 200-day average            -> fighting the tide (medium)
  - sector concentration                       -> one bet, not many (medium)
  - total stop-loss exposure                   -> the "if everything hits" number

Reads Spring-owned paper tables via SQL (read-only — Spring stays the writer).
"""
import logging
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

NEAR_STOP_PCT = 3.0        # close within this % of the stop = decision time
NEAR_TARGET_PCT = 2.0
TRAIL_ATR_MULT = 2.5       # suggested stop = close - mult * ATR(14)
CONCENTRATION_PCT = 50.0   # one sector holding more than this = flag


def position_health(session: Session) -> dict:
    rows = session.execute(text("""
        SELECT p.quantity, p.avg_cost, p.stop_price, p.target_price, p.strategy_id,
               s.id AS symbol_id, s.ticker, s.name, s.sector,
               snap.close, snap.atr_14, snap.sma_200, snap.as_of_date
        FROM paper_positions p
        JOIN symbols s ON s.id = p.symbol_id
        LEFT JOIN screener_snapshot snap ON snap.symbol_id = s.id
        WHERE p.quantity > 0
    """)).mappings().all()

    if not rows:
        return {"status": "NO_POSITIONS",
                "note": "No open positions — the Guardian activates when you hold something"}

    exit_fired = {r[0] for r in session.execute(text("""
        SELECT DISTINCT s.ticker FROM strategy_signals sig
        JOIN symbols s ON s.id = sig.symbol_id
        WHERE sig.signal = 'EXIT'
          AND sig.as_of_date = (SELECT MAX(as_of_date) FROM strategy_signals)
    """)).all()}

    positions, actions = [], []
    sector_value: dict[str, float] = defaultdict(float)
    total_value = total_stop_risk = 0.0
    unbounded = []

    for r in rows:
        qty = int(r["quantity"])
        close = float(r["close"]) if r["close"] is not None else None
        avg_cost = float(r["avg_cost"])
        stop = float(r["stop_price"]) if r["stop_price"] is not None else None
        target = float(r["target_price"]) if r["target_price"] is not None else None
        atr = float(r["atr_14"]) if r["atr_14"] is not None else None
        sma200 = float(r["sma_200"]) if r["sma_200"] is not None else None
        value = qty * (close if close is not None else avg_cost)
        pnl_pct = ((close / avg_cost - 1) * 100.0) if close else None

        total_value += value
        sector_value[r["sector"] or "Unknown"] += value

        pos = {"ticker": r["ticker"], "name": r["name"], "sector": r["sector"],
               "quantity": qty, "avg_cost": round(avg_cost, 2), "close": close,
               "stop_price": stop, "target_price": target,
               "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
               "checks": []}

        def flag(severity: str, kind: str, txt: str, **extra) -> None:
            pos["checks"].append(kind)
            actions.append({"severity": severity, "kind": kind,
                            "ticker": r["ticker"], "text": txt, **extra})

        if stop is None:
            unbounded.append(r["ticker"])
            flag("high", "STOP_MISSING",
                 f"{r['ticker']}: no stop-loss on {qty} shares (₹{value:,.0f}) — "
                 "your downside is the whole position.")
        elif close is not None:
            total_stop_risk += max(0.0, (close - stop)) * qty
            dist_pct = (close / stop - 1) * 100.0
            if close <= stop:
                flag("high", "STOP_BREACHED",
                     f"{r['ticker']} closed at ₹{close} — at/below your ₹{stop} stop. "
                     "Honour it or consciously re-underwrite the trade.")
            elif dist_pct <= NEAR_STOP_PCT:
                flag("high", "NEAR_STOP",
                     f"{r['ticker']} is {dist_pct:.1f}% above its ₹{stop} stop — "
                     "decide before the next open, don't let the market decide.")

        if r["ticker"] in exit_fired:
            flag("high", "EXIT_SIGNAL",
                 f"{r['ticker']}: your strategy fired EXIT on the latest bar but the "
                 "position is still open — the plan says leave.")

        if (close is not None and atr is not None and stop is not None
                and close > avg_cost):
            suggested = round(close - TRAIL_ATR_MULT * atr, 2)
            if suggested > stop * 1.01:
                locked = (suggested / avg_cost - 1) * 100.0
                flag("medium", "RAISE_STOP",
                     f"{r['ticker']} is +{pnl_pct:.1f}%. ATR trail says raise the stop "
                     f"₹{stop} → ₹{suggested} (locks in {locked:+.1f}%).",
                     suggested_stop=suggested)

        if close is not None and target is not None and target > 0:
            to_target = (target / close - 1) * 100.0
            if 0 <= to_target <= NEAR_TARGET_PCT:
                flag("medium", "NEAR_TARGET",
                     f"{r['ticker']} is {to_target:.1f}% from its ₹{target} target — "
                     "plan the exit: scale out, trail tighter, or take it.")

        if close is not None and sma200 is not None and close < sma200:
            flag("medium", "TREND_FLIP",
                 f"{r['ticker']} closed below its 200-day average — the long-term "
                 "tide turned against this position.")

        positions.append(pos)

    # ---- account-level reads ----
    if len(positions) >= 2:
        top_sector, top_value = max(sector_value.items(), key=lambda kv: kv[1])
        share = top_value / total_value * 100.0 if total_value else 0.0
        if share > CONCENTRATION_PCT:
            actions.append({"severity": "medium", "kind": "CONCENTRATION", "ticker": None,
                            "text": f"{share:.0f}% of your book is {top_sector} — "
                                    "several tickers, one bet. A sector shock hits all of it."})

    cash = session.execute(text(
        "SELECT cash FROM paper_accounts ORDER BY id LIMIT 1")).scalar() or 0.0
    equity = float(cash) + total_value
    if total_stop_risk > 0 and equity > 0:
        actions.append({
            "severity": "info", "kind": "STOP_EXPOSURE", "ticker": None,
            "text": f"If every stop hits: -₹{total_stop_risk:,.0f} "
                    f"({total_stop_risk / equity * 100.0:.1f}% of equity)"
                    + (f" — plus unbounded risk on {', '.join(unbounded)}." if unbounded else ".")})

    severity_rank = {"high": 0, "medium": 1, "info": 2}
    actions.sort(key=lambda a: severity_rank[a["severity"]])

    return {"status": "OK", "positions": positions, "actions": actions,
            "summary": {"open_positions": len(positions),
                        "portfolio_value": round(total_value, 2),
                        "equity": round(equity, 2),
                        "high_priority": sum(1 for a in actions if a["severity"] == "high")}}
