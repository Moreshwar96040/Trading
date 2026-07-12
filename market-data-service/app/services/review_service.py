"""The Leaks Report: what your own trades say about your habits.

Reads the paper-trading order log (Spring-owned tables, read here via SQL) and
computes the statistics traders never compute about themselves: expectancy,
win rate, hold time, performance by weekday, and discipline leaks — orders
placed without a stop, sells with no journal note, oversized losers.

All numbers are deterministic Python; the optional Claude narrative on top is
generated once per new order (cached via ai_insights, kind=REVIEW).
"""
import logging
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def compute_leaks(session: Session) -> dict:
    orders = session.execute(text("""
        SELECT o.id, s.ticker, o.side, o.quantity, o.price, o.commission,
               o.realized_pnl, o.status, o.placed_at, o.stop_price, o.strategy_id,
               EXISTS (SELECT 1 FROM journal_entries j WHERE j.paper_order_id = o.id)
                   AS journaled
        FROM paper_orders o JOIN symbols s ON s.id = o.symbol_id
        WHERE o.status = 'FILLED'
        ORDER BY o.placed_at
    """)).mappings().all()

    if not orders:
        return {"status": "NO_TRADES",
                "note": "No filled paper orders yet — the report builds itself as you trade"}

    buys = [o for o in orders if o["side"] == "BUY"]
    sells = [o for o in orders if o["side"] == "SELL"]
    closed = [o for o in sells if o["realized_pnl"] is not None]

    # ---- outcome stats ----
    pnls = [float(o["realized_pnl"]) for o in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    expectancy = sum(pnls) / len(pnls) if pnls else None
    win_rate = len(wins) / len(pnls) * 100.0 if pnls else None
    avg_win = sum(wins) / len(wins) if wins else None
    avg_loss = sum(losses) / len(losses) if losses else None
    payoff = (avg_win / abs(avg_loss)) if avg_win and avg_loss else None

    # ---- by weekday (entry day) ----
    by_day: dict[int, list[float]] = defaultdict(list)
    # attribute each SELL's pnl to the weekday of the SELL (exit discipline read)
    for o in closed:
        by_day[o["placed_at"].weekday()].append(float(o["realized_pnl"]))
    weekday_stats = [{"day": WEEKDAYS[d], "trades": len(v), "pnl": round(sum(v), 2)}
                     for d, v in sorted(by_day.items())]

    # ---- discipline leaks ----
    leaks: list[dict] = []
    no_stop = [o for o in buys if o["stop_price"] is None]
    if no_stop:
        leaks.append({
            "kind": "NO_STOP", "count": len(no_stop), "severity": "high",
            "text": f"{len(no_stop)} of {len(buys)} buys had no stop-loss attached — "
                    "every one of them is an unbounded risk."})
    unjournaled = [o for o in buys if not o["journaled"]]
    if unjournaled:
        leaks.append({
            "kind": "NO_JOURNAL", "count": len(unjournaled), "severity": "medium",
            "text": f"{len(unjournaled)} buys have no journal note — in a month you won't "
                    "remember why you took them, so you can't learn from them."})
    freelance = [o for o in buys if o["strategy_id"] is None]
    if freelance:
        leaks.append({
            "kind": "OFF_STRATEGY", "count": len(freelance), "severity": "medium",
            "text": f"{len(freelance)} buys weren't tied to any strategy — impulse trades "
                    "are untestable, so their edge is unknowable."})
    if losses and avg_loss is not None and avg_win is not None and abs(avg_loss) > 1.5 * avg_win:
        leaks.append({
            "kind": "BIG_LOSERS", "count": len(losses), "severity": "high",
            "text": f"Your average loss (₹{abs(avg_loss):,.0f}) is "
                    f"{abs(avg_loss) / avg_win:.1f}× your average win (₹{avg_win:,.0f}) — "
                    "the classic cut-winners-ride-losers pattern."})

    return {
        "status": "OK",
        "orders": len(orders),
        "closed_trades": len(closed),
        "stats": {
            "total_pnl": round(sum(pnls), 2) if pnls else 0.0,
            "expectancy_per_trade": round(expectancy, 2) if expectancy is not None else None,
            "win_rate_pct": round(win_rate, 1) if win_rate is not None else None,
            "avg_win": round(avg_win, 2) if avg_win is not None else None,
            "avg_loss": round(avg_loss, 2) if avg_loss is not None else None,
            "payoff_ratio": round(payoff, 2) if payoff is not None else None,
        },
        "by_weekday": weekday_stats,
        "leaks": leaks,
        "journal_coverage_pct": round(
            sum(1 for o in buys if o["journaled"]) / len(buys) * 100.0, 1) if buys else None,
    }


REVIEW_SYSTEM = (
    "You are a trading coach reviewing a retail trader's paper-trading statistics. "
    "You are given their aggregate stats, weekday breakdown and detected discipline "
    "leaks. Respond with ONLY a JSON object, no markdown fences, with keys: "
    "headline (one blunt sentence), habits_working (array of max 3 short strings), "
    "habits_costing_you (array of max 3 short strings, each tied to a number from the "
    "data), one_change (single most impactful behavioural change for next month, one "
    "sentence). Be direct and specific like a good coach; never mention buying or "
    "selling any particular security.")


def leaks_narrative(session: Session, settings, leaks_data: dict) -> dict | None:
    """Claude coach's read of the stats — cached until a new order lands."""
    import json

    from app.ai import narrator
    from app.models import AiInsight
    from datetime import datetime, timezone

    if not narrator.llm_enabled(settings) or leaks_data.get("status") != "OK":
        return None
    fingerprint = f"orders-{leaks_data['orders']}"
    row = session.get(AiInsight, (0, "REVIEW"))     # symbol_id 0 = account-level
    if row is not None and row.fingerprint == fingerprint:
        return {"insight": row.content, "cached": True}
    try:
        raw = narrator._call_claude(settings, REVIEW_SYSTEM, json.dumps(leaks_data),
                                    session=session, kind="REVIEW")
        content = narrator._parse_json(raw)
    except Exception as exc:                        # noqa: BLE001 — narrative is optional
        log.error("Leaks narrative failed: %s", exc)
        return {"error": str(exc)}
    if row is None:
        row = AiInsight(symbol_id=0, kind="REVIEW")
    row.content = content
    row.fingerprint = fingerprint
    row.model_name = settings.anthropic_model
    row.generated_at = datetime.now(timezone.utc)
    session.merge(row)
    session.commit()
    return {"insight": content, "cached": False}
