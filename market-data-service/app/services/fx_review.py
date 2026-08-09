"""Exness / MT5 closed-trade analysis: what your FX & crypto trading actually did.

The Alpha Stack can't score a currency pair, but your own trade history is pure
arithmetic — and it's where the honest edge lives. This answers the questions a
discretionary FX trader most often can't answer about themselves:

  - Do I actually make money, after swap and commission?
  - Which symbols pay me, and which ones I keep trading out of habit?
  - Is my average loss bigger than my average win? (the classic killer)
  - Do I cut winners early and let losers run? (hold-time asymmetry)
  - How much is overnight financing quietly costing me?

Every number is computed from closed round-trips, so it reflects money that
really settled, not floating hope. Read-only and deterministic: no LLM, no
predictions, no advice — just your record, stated plainly.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone

log = logging.getLogger(__name__)

#: A loss/win ratio worse than this means winners must be unusually frequent to survive.
PAYOFF_WARN = 1.0
#: Holding losers materially longer than winners is the "hope" pattern.
HOLD_ASYMMETRY = 1.5
#: Swap this negative, relative to gross profit, is a real drag worth naming.
SWAP_DRAG_PCT = 20.0
MIN_TRADES_FOR_SYMBOL_VERDICT = 3


def _safe_div(a: float, b: float):
    return (a / b) if b else None


def analyze_fx_trades(state: dict) -> dict:
    """Closed MT5 trades -> performance stats, per-symbol table and leaks."""
    if state.get("status") != "OK":
        return {"status": state.get("status", "UNAVAILABLE"),
                "note": state.get("note"), "trades": [], "leaks": []}

    trades = state.get("trades") or []
    if not trades:
        return {"status": "NO_TRADES", "trades": [], "leaks": [],
                "note": "No closed trades in this window — nothing to analyse yet."}

    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] < 0]
    gross_profit = sum(t["net"] for t in wins)
    gross_loss = abs(sum(t["net"] for t in losses))
    net = sum(t["net"] for t in trades)
    total_swap = sum(t.get("swap", 0) for t in trades)
    total_commission = sum(t.get("commission", 0) for t in trades)

    avg_win = _safe_div(gross_profit, len(wins))
    avg_loss = _safe_div(gross_loss, len(losses))
    payoff = _safe_div(avg_win or 0, avg_loss) if avg_loss else None
    win_rate = len(wins) / len(trades) * 100.0

    hold_win = _safe_div(sum(t["hold_hours"] or 0 for t in wins), len(wins))
    hold_loss = _safe_div(sum(t["hold_hours"] or 0 for t in losses), len(losses))

    stats = {
        "trades": len(trades),
        "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "net": round(net, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(_safe_div(gross_profit, gross_loss), 2)
        if gross_loss else None,
        "expectancy": round(net / len(trades), 2),
        "avg_win": round(avg_win, 2) if avg_win is not None else None,
        "avg_loss": round(avg_loss, 2) if avg_loss is not None else None,
        "payoff_ratio": round(payoff, 2) if payoff else None,
        "swap_total": round(total_swap, 2),
        "commission_total": round(total_commission, 2),
        "avg_hold_hours_win": round(hold_win, 1) if hold_win is not None else None,
        "avg_hold_hours_loss": round(hold_loss, 1) if hold_loss is not None else None,
        "best": max(trades, key=lambda t: t["net"])["net"],
        "worst": min(trades, key=lambda t: t["net"])["net"],
    }

    # ---- per symbol: what pays, what bleeds ----
    per: dict[str, dict] = defaultdict(
        lambda: {"trades": 0, "net": 0.0, "wins": 0, "volume": 0.0})
    for t in trades:
        row = per[t["symbol"]]
        row["trades"] += 1
        row["net"] += t["net"]
        row["volume"] += t.get("volume", 0)
        if t["net"] > 0:
            row["wins"] += 1
    symbols = sorted(
        ({"symbol": s, "trades": r["trades"], "net": round(r["net"], 2),
          "win_rate_pct": round(r["wins"] / r["trades"] * 100.0, 1),
          "volume": round(r["volume"], 2)} for s, r in per.items()),
        key=lambda r: r["net"])

    # ---- leaks: the patterns worth changing ----
    leaks = []
    if stats["payoff_ratio"] is not None and stats["payoff_ratio"] < PAYOFF_WARN:
        leaks.append({
            "severity": "high", "kind": "PAYOFF",
            "text": f"Your average loss ({stats['avg_loss']}) is bigger than your average "
                    f"win ({stats['avg_win']}). At a {stats['win_rate_pct']}% win rate that "
                    "maths only works if you win far more often than you lose."})

    if hold_win and hold_loss and hold_loss > hold_win * HOLD_ASYMMETRY:
        leaks.append({
            "severity": "high", "kind": "HOLD_ASYMMETRY",
            "text": f"You hold losers {hold_loss:.1f}h on average but winners only "
                    f"{hold_win:.1f}h — cutting winners early and hoping on losers."})

    if gross_profit > 0 and total_swap < 0 \
            and abs(total_swap) / gross_profit * 100.0 >= SWAP_DRAG_PCT:
        leaks.append({
            "severity": "medium", "kind": "SWAP_DRAG",
            "text": f"Swap has cost {abs(total_swap):.2f}, which is "
                    f"{abs(total_swap) / gross_profit * 100:.0f}% of your gross profit — "
                    "overnight financing is eating the edge."})

    bleeders = [s for s in symbols
                if s["net"] < 0 and s["trades"] >= MIN_TRADES_FOR_SYMBOL_VERDICT]
    if bleeders:
        worst = bleeders[0]
        leaks.append({
            "severity": "medium", "kind": "LOSING_SYMBOL",
            "text": f"{worst['symbol']} has lost {abs(worst['net']):.2f} across "
                    f"{worst['trades']} trades ({worst['win_rate_pct']}% win rate) — "
                    "consider dropping it from your rotation."})

    if stats["profit_factor"] is not None and stats["profit_factor"] < 1:
        leaks.append({
            "severity": "high", "kind": "UNPROFITABLE",
            "text": f"Profit factor {stats['profit_factor']} — this book loses money "
                    "over the window. Reduce size until the process is fixed."})

    rank = {"high": 0, "medium": 1, "info": 2}
    leaks.sort(key=lambda x: rank[x["severity"]])
    return {"status": "OK", "days": state.get("days"), "stats": stats,
            "symbols": symbols, "leaks": leaks,
            "trades": [_public(t) for t in trades[:50]]}


def _public(t: dict) -> dict:
    """Trade row with human-readable timestamps for the UI."""
    def iso(ts):
        if not ts:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return {**t, "opened_at": iso(t.get("opened_at")), "closed_at": iso(t.get("closed_at"))}


def exness_trade_review(settings, days: int = 90) -> dict:
    """Fetch + analyse in one call, driven by config."""
    from app.providers.mt5 import fetch_deal_history
    state = fetch_deal_history(
        days=days,
        login=getattr(settings, "mt5_login", None) or None,
        password=getattr(settings, "mt5_password", "") or None,
        server=getattr(settings, "mt5_server", "") or None,
        terminal_path=getattr(settings, "mt5_terminal_path", "") or None)
    return analyze_fx_trades(state)
