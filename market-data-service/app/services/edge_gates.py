"""Edge Gates: the falsifiable path from strategy idea to proven edge.

No feature can hand anyone a profitable strategy. What CAN be built is the
process professionals actually use — and enforcement that you followed it.
Each strategy is tracked through four gates, computed from data the platform
already records (backtests, robustness reports, paper orders):

  Gate 1 — SAMPLE     backtest produced >= 30 closed trades (else: noise)
  Gate 2 — ROBUST     robustness score >= 60 AND out-of-sample return > 0
  Gate 3 — PAPER      >= 15 closed paper trades taken via this strategy
  Gate 4 — LIVE EDGE  live expectancy per trade > 0 (the backtest survived reality)

A strategy that passes all four has earned real risk. Anything else is a
hypothesis — the UI says so in those words.
"""
import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

MIN_BACKTEST_TRADES = 30
MIN_ROBUSTNESS = 60
MIN_PAPER_TRADES = 15


def _gate(status: str, detail: str) -> dict:
    return {"status": status, "detail": detail}   # PASS | FAIL | PENDING


def edge_gates(session: Session) -> dict:
    strategies = session.execute(text(
        "SELECT id, name, description FROM strategies ORDER BY id")).mappings().all()
    if not strategies:
        return {"status": "NO_STRATEGIES",
                "note": "Create a strategy in the Strategy Lab — presets are one click"}

    results = []
    for s in strategies:
        # ---- latest successful backtest + its robustness report ----
        bt = session.execute(text("""
            SELECT metrics FROM backtests
            WHERE strategy_id = :sid AND status = 'SUCCESS'
            ORDER BY finished_at DESC LIMIT 1
        """), {"sid": s["id"]}).scalar()
        if isinstance(bt, str):          # SQLite hands JSON back as text via raw SQL
            bt = json.loads(bt)

        if bt is None:
            g1 = _gate("PENDING", "No backtest yet — run one in the Strategy Lab")
            g2 = _gate("PENDING", "Needs a backtest first")
        else:
            trades = bt.get("trades", 0) or 0
            rob = bt.get("robustness") or {}
            score = rob.get("score")
            holdout = rob.get("holdout") or {}
            oos = holdout.get("out_sample_return_pct")

            g1 = (_gate("PASS", f"{trades} closed trades in the backtest")
                  if trades >= MIN_BACKTEST_TRADES else
                  _gate("FAIL", f"Only {trades} closed trades — widen the window or "
                                f"universe (need {MIN_BACKTEST_TRADES}+)"))
            if score is None:
                g2 = _gate("PENDING", "Re-run the backtest to get a robustness report")
            elif score >= MIN_ROBUSTNESS and oos is not None and oos > 0:
                g2 = _gate("PASS", f"Robustness {score}/100, out-of-sample {oos:+.1f}%")
            else:
                why = []
                if score < MIN_ROBUSTNESS:
                    why.append(f"robustness {score} < {MIN_ROBUSTNESS}")
                if oos is None:
                    why.append("no out-of-sample split (window too short)")
                elif oos <= 0:
                    why.append(f"out-of-sample {oos:+.1f}% — the edge didn't survive "
                               "unseen data")
                g2 = _gate("FAIL", "; ".join(why))

        # ---- paper record for this strategy ----
        paper = session.execute(text("""
            SELECT COUNT(*) FILTER (WHERE side = 'SELL' AND realized_pnl IS NOT NULL)
                       AS closed,
                   COALESCE(SUM(realized_pnl) FILTER (WHERE side = 'SELL'), 0) AS pnl
            FROM paper_orders
            WHERE strategy_id = :sid AND status = 'FILLED'
        """), {"sid": s["id"]}).mappings().one()
        closed = int(paper["closed"] or 0)
        pnl = float(paper["pnl"] or 0)

        g3 = (_gate("PASS", f"{closed} closed paper trades")
              if closed >= MIN_PAPER_TRADES else
              _gate("PENDING", f"{closed}/{MIN_PAPER_TRADES} closed paper trades — "
                               "trade its signals through the discipline gate"))

        if closed == 0:
            g4 = _gate("PENDING", "No live trades yet")
        else:
            expectancy = pnl / closed
            g4 = (_gate("PASS", f"Live expectancy ₹{expectancy:,.0f}/trade "
                                f"(₹{pnl:,.0f} over {closed} trades)")
                  if expectancy > 0 else
                  _gate("FAIL", f"Live expectancy ₹{expectancy:,.0f}/trade — reality "
                                "disagrees with the backtest. Stop and investigate."))

        gates = [g1, g2, g3, g4]
        statuses = [g["status"] for g in gates]
        if all(st == "PASS" for st in statuses):
            verdict = "VALIDATED"
        elif "FAIL" in statuses:
            verdict = "FAILED"
        elif statuses[0] == "PENDING" and statuses[1] == "PENDING" and closed == 0:
            verdict = "UNTESTED"
        else:
            verdict = "IN_PROGRESS"

        results.append({"strategy_id": s["id"], "name": s["name"],
                        "description": s["description"],
                        "verdict": verdict,
                        "gates": {"sample": g1, "robustness": g2,
                                  "paper": g3, "live_edge": g4}})

    order = {"VALIDATED": 0, "IN_PROGRESS": 1, "UNTESTED": 2, "FAILED": 3}
    results.sort(key=lambda r: order[r["verdict"]])
    return {"status": "OK", "strategies": results,
            "thresholds": {"backtest_trades": MIN_BACKTEST_TRADES,
                           "robustness": MIN_ROBUSTNESS,
                           "paper_trades": MIN_PAPER_TRADES}}
