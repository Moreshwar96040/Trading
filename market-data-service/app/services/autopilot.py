"""Paper autopilot: let the Alpha Stack actually trade, so we can grade it on money.

`conviction_history` measures whether the *score* predicts forward returns. That's
signal quality. It says nothing about whether the *system* is profitable, because a
real trade also carries a position size, a stop, an exit and a capital limit — any
of which can turn a genuinely predictive score into a losing strategy.

This module closes that loop: each day it takes the best live setups into the paper
book, records the conviction that justified each entry, and reconciles outcomes when
positions close. Realised P&L can then be attributed back to the score.

Two hard rules:

  PAPER ONLY. This never touches Upstox or MT5. There is no live code path.
  OFF BY DEFAULT. It does nothing unless AUTOPILOT_ENABLED=true.

Ownership note: the Spring backend is the sole writer of paper_orders and
paper_positions. The autopilot does NOT write them — it calls Spring's
POST /api/v1/paper/orders like any other client, and keeps only its own
attribution rows here. That keeps one writer per table.
"""
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

#: Only NORMAL and HIGH setups — matches the 1x/1.5x sizing bands.
MIN_CONVICTION = 55.0
#: Concurrent open autopilot positions. Keeps the book diversified and realistic.
MAX_POSITIONS = 8
#: Stop distance when the risk engine has nothing better to say.
FALLBACK_STOP_ATR_MULT = 2.5
#: Reward:risk used to derive a target from the stop.
TARGET_RR = 2.0


def _open_positions(session: Session) -> dict:
    """Autopilot rows still marked OPEN, keyed by symbol."""
    from app.models import AutopilotTrade
    return {t.symbol_id: t for t in session.scalars(
        select(AutopilotTrade).where(AutopilotTrade.status == "OPEN")).all()}


def _held_symbol_ids(session: Session) -> set:
    """Anything already in the paper book — never double up on a name."""
    try:
        return {r[0] for r in session.execute(text(
            "SELECT symbol_id FROM paper_positions WHERE quantity > 0")).all()}
    except Exception:                       # noqa: BLE001 — paper tables optional in tests
        return set()


def _strengths(breakdown: list[dict]) -> dict:
    by_layer = {b["layer"]: b.get("strength") for b in breakdown or []}
    return {f"{layer}_strength": by_layer.get(layer)
            for layer in ("technical", "quality", "news", "momentum",
                          "ml", "macro", "regime")}


def _risk_plan(session: Session, symbol_id: int, price: float) -> tuple:
    """(stop, target) from ATR — the same logic the manual 'Trade it' flow uses."""
    from app.models import ScreenerSnapshot
    snap = session.get(ScreenerSnapshot, symbol_id)
    atr = float(snap.atr_14) if snap is not None and snap.atr_14 is not None else None
    if not atr or atr <= 0:
        return None, None
    stop = round(price - FALLBACK_STOP_ATR_MULT * atr, 2)
    if stop <= 0 or stop >= price:
        return None, None
    target = round(price + TARGET_RR * (price - stop), 2)
    return stop, target


def select_candidates(setups: list[dict], held: set, open_count: int,
                      min_conviction: float = MIN_CONVICTION,
                      max_positions: int = MAX_POSITIONS) -> list[dict]:
    """Which setups to take today. Pure — the decision rule, unit-tested alone.

    Filters, in order: conviction bar, no news veto, non-zero size, not already
    held, then highest conviction first up to the free-slot count.
    """
    slots = max(0, max_positions - open_count)
    if slots <= 0:
        return []
    eligible = [s for s in setups
                if s.get("conviction", 0) >= min_conviction
                and not s.get("news_veto")
                and (s.get("risk_multiplier") or 0) > 0
                and s.get("symbol_id") not in held
                and s.get("close")]
    eligible.sort(key=lambda s: s["conviction"], reverse=True)
    return eligible[:slots]


def run_autopilot(session: Session, settings, place_order=None) -> dict:
    """Score, select, and open paper trades. `place_order` is injectable so the
    selection logic can be tested without a live Spring backend."""
    if not getattr(settings, "autopilot_enabled", False):
        return {"status": "DISABLED",
                "note": "Set AUTOPILOT_ENABLED=true to let the Alpha Stack paper-trade."}

    from app.models import AutopilotTrade, Symbol
    from app.services.circuit_breakers import evaluate as check_breakers
    from app.services.conviction_service import alpha_stack

    # Checked before scoring, not after: if the breakers say stop, the score is
    # not information we should be acting on, so there is no point computing it.
    breakers = check_breakers(session)
    if breakers["halted"]:
        return {"status": "HALTED", "opened": 0,
                "breakers": breakers, "note": breakers["summary"]}

    stack = alpha_stack(session)
    setups = stack.get("setups") or []
    if not setups:
        return {"status": "NO_SETUPS", "opened": 0,
                "note": stack.get("note") or "No live setups to trade."}

    # alpha_stack returns tickers, not ids — resolve once.
    ids = {s.ticker: s.id for s in session.scalars(
        select(Symbol).where(Symbol.active)).all()}
    for s in setups:
        s["symbol_id"] = ids.get(s["ticker"])

    open_trades = _open_positions(session)
    held = _held_symbol_ids(session) | set(open_trades)
    picks = select_candidates(setups, held, len(open_trades))
    if not picks:
        return {"status": "OK", "opened": 0, "open_positions": len(open_trades),
                "note": "No new setups cleared the bar, or all slots are full."}

    placer = place_order or _place_via_backend
    opened, failures = [], []
    today = date.today()

    for setup in picks:
        price = float(setup["close"])
        stop, target = _risk_plan(session, setup["symbol_id"], price)
        try:
            result = placer(settings, ticker=setup["ticker"], price=price,
                            stop=stop, target=target,
                            risk_multiplier=float(setup.get("risk_multiplier") or 1.0))
        except Exception as exc:            # noqa: BLE001 — one rejection ≠ abort the run
            log.warning("Autopilot order failed for %s: %s", setup["ticker"], exc)
            failures.append(f"{setup['ticker']}: {exc}")
            continue
        if not result or not result.get("quantity"):
            failures.append(f"{setup['ticker']}: {result.get('reject') if result else 'no fill'}")
            continue

        session.add(AutopilotTrade(
            symbol_id=setup["symbol_id"], ticker=setup["ticker"],
            entry_date=today, entry_price=result.get("price") or price,
            quantity=int(result["quantity"]), stop_price=stop, target_price=target,
            paper_order_id=result.get("order_id"),
            conviction=setup["conviction"], verdict=setup.get("verdict"),
            risk_multiplier=setup.get("risk_multiplier"),
            **_strengths(setup.get("breakdown")),
            regime_code=(stack.get("regime") or {}).get("code"),
            sector=setup.get("sector"), status="OPEN"))
        opened.append({"ticker": setup["ticker"], "conviction": setup["conviction"],
                       "quantity": result["quantity"], "stop": stop})

    session.commit()
    log.info("Autopilot: opened %d, failed %d", len(opened), len(failures))
    return {"status": "OK", "opened": len(opened), "trades": opened,
            "failures": failures, "open_positions": len(open_trades) + len(opened)}


def _place_via_backend(settings, *, ticker: str, price: float, stop, target,
                       risk_multiplier: float) -> dict:
    """Place the order through Spring's paper API — it stays the only writer.

    Quantity comes from Spring's own risk-based sizer where possible; we scale by
    the Alpha Stack's conviction multiplier so a HIGH setup takes a bigger position
    than a NORMAL one, exactly as the manual flow does.
    """
    import httpx

    base = getattr(settings, "backend_base_url", "http://localhost:8080")
    quantity = None
    if stop and price > stop:
        try:
            sized = httpx.get(f"{base}/api/v1/risk/position-size",
                              params={"entryPrice": price, "stopPrice": stop},
                              timeout=10.0)
            if sized.status_code == 200:
                base_qty = int(sized.json().get("quantity") or 0)
                quantity = max(0, int(base_qty * risk_multiplier))
        except Exception as exc:            # noqa: BLE001 — fall through to a default
            log.debug("Risk sizing unavailable (%s); using fallback", exc)
    if not quantity:
        return {"quantity": 0, "reject": "could not size the position"}

    resp = httpx.post(f"{base}/api/v1/paper/orders", timeout=15.0, json={
        "ticker": ticker, "side": "BUY", "quantity": quantity,
        "stopPrice": stop, "targetPrice": target})
    if resp.status_code >= 400:
        return {"quantity": 0, "reject": f"HTTP {resp.status_code}"}
    body = resp.json()
    if body.get("status") != "FILLED":
        return {"quantity": 0, "reject": body.get("rejectReason") or body.get("status")}
    return {"quantity": body.get("quantity"), "price": body.get("price"),
            "order_id": body.get("id")}


def reconcile_closed(session: Session) -> dict:
    """Mark autopilot trades closed once the paper book no longer holds them.

    The Spring position manager does the actual selling (stop/target/trailing);
    we detect the disappearance and attach the realised outcome.
    """
    from app.models import AutopilotTrade

    open_trades = _open_positions(session)
    if not open_trades:
        return {"closed": 0}
    still_held = _held_symbol_ids(session)

    closed = 0
    for symbol_id, trade in open_trades.items():
        if symbol_id in still_held:
            continue                        # position still open — nothing to do
        # Latest SELL fill for this symbol gives the exit price and realised P&L.
        row = session.execute(text("""
            SELECT price, realized_pnl, placed_at
            FROM paper_orders
            WHERE symbol_id = :sid AND side = 'SELL' AND status = 'FILLED'
            ORDER BY placed_at DESC LIMIT 1
        """), {"sid": symbol_id}).mappings().first()

        trade.status = "CLOSED"
        trade.exit_date = (row["placed_at"].date() if row and row["placed_at"]
                           else date.today())
        if row and row["price"] is not None:
            exit_price = float(row["price"])
            trade.exit_price = exit_price
            if trade.entry_price and float(trade.entry_price) > 0:
                trade.return_pct = round(
                    (exit_price / float(trade.entry_price) - 1) * 100.0, 4)
        if row and row["realized_pnl"] is not None:
            trade.realized_pnl = float(row["realized_pnl"])
        if trade.exit_date and trade.entry_date:
            trade.hold_days = (trade.exit_date - trade.entry_date).days
        trade.exit_reason = "closed in paper book"
        session.merge(trade)
        closed += 1

    session.commit()
    return {"closed": closed}


def autopilot_status(session: Session, settings) -> dict:
    """Open trades + realised performance attributed by conviction band."""
    from app.ai.calibration import BANDS
    from app.models import AutopilotTrade

    trades = session.scalars(select(AutopilotTrade)).all()
    open_rows = [t for t in trades if t.status == "OPEN"]
    closed = [t for t in trades if t.status == "CLOSED" and t.realized_pnl is not None]

    bands = []
    for low, high, label in BANDS:
        bucket = [t for t in closed if low <= float(t.conviction) < high]
        if not bucket:
            bands.append({"band": label, "trades": 0, "net": 0.0,
                          "win_rate_pct": None, "avg_return_pct": None})
            continue
        nets = [float(t.realized_pnl) for t in bucket]
        rets = [float(t.return_pct) for t in bucket if t.return_pct is not None]
        bands.append({
            "band": label, "trades": len(bucket), "net": round(sum(nets), 2),
            "win_rate_pct": round(sum(1 for v in nets if v > 0) / len(nets) * 100.0, 1),
            "avg_return_pct": round(sum(rets) / len(rets), 2) if rets else None,
            "expectancy": round(sum(nets) / len(nets), 2)})

    total_net = round(sum(float(t.realized_pnl) for t in closed), 2) if closed else 0.0
    return {
        "enabled": bool(getattr(settings, "autopilot_enabled", False)),
        "min_conviction": MIN_CONVICTION, "max_positions": MAX_POSITIONS,
        "open": [{"ticker": t.ticker, "entry_date": str(t.entry_date),
                  "entry_price": float(t.entry_price) if t.entry_price else None,
                  "quantity": t.quantity, "conviction": float(t.conviction),
                  "stop_price": float(t.stop_price) if t.stop_price else None}
                 for t in sorted(open_rows, key=lambda t: t.entry_date, reverse=True)],
        "closed_count": len(closed), "net": total_net,
        "by_band": bands,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
