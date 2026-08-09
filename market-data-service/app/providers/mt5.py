"""MetaTrader 5 provider — read-only account + open positions (Exness and any
other MT5 broker).

Exness publishes no REST API for retail accounts; the supported integration is
the `MetaTrader5` package talking to a locally running MT5 terminal over IPC.
That has hard consequences this module isolates:

  - Windows-only, and the terminal must be installed AND logged in.
  - The import itself fails on Linux/macOS, so it is done lazily inside the call
    and every failure is reported as a status, never raised. The rest of the
    service (and its tests) run identically with no MT5 present.

Read-only by design: this module exposes account state and open positions. It
has no order, modify, or close functions — the same stance the app takes with
Upstox.
"""
import logging

log = logging.getLogger(__name__)

#: MT5 position type constants (0 = BUY, 1 = SELL) — mirrored so we never need
#: the package imported just to interpret a stored row.
POSITION_BUY, POSITION_SELL = 0, 1


def _import_mt5():
    """Import the MetaTrader5 package, or explain why it's unavailable."""
    try:
        import MetaTrader5 as mt5          # noqa: N813 — vendor's capitalisation
        return mt5, None
    except Exception as exc:               # noqa: BLE001 — ImportError on Linux, OSError on some builds
        return None, (f"MetaTrader5 package unavailable ({exc}). It is Windows-only: "
                      "pip install MetaTrader5 on the machine running the MT5 terminal.")


def fetch_account_state(login: int | None = None, password: str | None = None,
                        server: str | None = None,
                        terminal_path: str | None = None) -> dict:
    """Account summary + open positions from the local MT5 terminal.

    Credentials are optional: if the terminal is already logged in (the normal
    desktop case) `initialize()` attaches to that session. Returns a status dict
    rather than raising, so the UI can always render something honest.
    """
    mt5, err = _import_mt5()
    if mt5 is None:
        return {"status": "UNAVAILABLE", "note": err, "positions": []}

    kwargs = {}
    if terminal_path:
        kwargs["path"] = terminal_path
    if login and password and server:
        kwargs.update({"login": int(login), "password": password, "server": server})

    try:
        if not mt5.initialize(**kwargs):
            code, desc = mt5.last_error()
            return {"status": "NOT_CONNECTED", "positions": [],
                    "note": f"Could not attach to the MT5 terminal ({code}: {desc}). "
                            "Open MetaTrader 5, log into your Exness account, and keep it running."}
        try:
            info = mt5.account_info()
            if info is None:
                return {"status": "NOT_CONNECTED", "positions": [],
                        "note": "MT5 terminal is running but no account is logged in."}
            raw_positions = mt5.positions_get() or ()
            account = {
                "login": getattr(info, "login", None),
                "server": getattr(info, "server", None),
                "currency": getattr(info, "currency", None),
                "balance": float(getattr(info, "balance", 0) or 0),
                "equity": float(getattr(info, "equity", 0) or 0),
                "margin": float(getattr(info, "margin", 0) or 0),
                "margin_free": float(getattr(info, "margin_free", 0) or 0),
                "margin_level": float(getattr(info, "margin_level", 0) or 0),
                "profit": float(getattr(info, "profit", 0) or 0),
                "leverage": getattr(info, "leverage", None),
            }
            positions = [_normalize_position(p) for p in raw_positions]
            return {"status": "OK", "account": account, "positions": positions}
        finally:
            mt5.shutdown()
    except Exception as exc:               # noqa: BLE001 — never break the caller
        log.warning("MT5 fetch failed: %s", exc, exc_info=True)
        return {"status": "ERROR", "positions": [], "note": f"MT5 error: {exc}"}


#: MT5 deal entry constants: 0 = position opened, 1 = closed, 2 = reversed.
DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1
#: Deal types: 0 = buy, 1 = sell; 2+ are balance/credit/commission operations.
DEAL_TYPE_BUY, DEAL_TYPE_SELL = 0, 1


def fetch_deal_history(days: int = 90, login: int | None = None,
                       password: str | None = None, server: str | None = None,
                       terminal_path: str | None = None) -> dict:
    """Closed trades from the terminal's deal history, newest first.

    MT5 stores *deals* (fills), not trades: an entry deal and an exit deal share
    a `position_id`. We pair them so each row is one round-trip with its true
    P&L including commission and swap — the number that actually hit the account.
    Balance/credit operations (deposits, bonuses) are excluded.
    """
    mt5, err = _import_mt5()
    if mt5 is None:
        return {"status": "UNAVAILABLE", "note": err, "trades": []}

    kwargs = {}
    if terminal_path:
        kwargs["path"] = terminal_path
    if login and password and server:
        kwargs.update({"login": int(login), "password": password, "server": server})

    try:
        if not mt5.initialize(**kwargs):
            code, desc = mt5.last_error()
            return {"status": "NOT_CONNECTED", "trades": [],
                    "note": f"Could not attach to the MT5 terminal ({code}: {desc})."}
        try:
            from datetime import datetime, timedelta, timezone
            to = datetime.now(timezone.utc) + timedelta(days=1)
            frm = to - timedelta(days=days + 1)
            deals = mt5.history_deals_get(frm, to) or ()
            return {"status": "OK", "trades": pair_deals(deals), "days": days}
        finally:
            mt5.shutdown()
    except Exception as exc:                   # noqa: BLE001
        log.warning("MT5 history fetch failed: %s", exc, exc_info=True)
        return {"status": "ERROR", "trades": [], "note": f"MT5 error: {exc}"}


def pair_deals(deals) -> list[dict]:
    """Group raw deals by position_id into closed round-trips. Pure — unit-tested
    against plain objects, so it needs no terminal."""
    by_position: dict = {}
    for d in deals:
        if getattr(d, "type", None) not in (DEAL_TYPE_BUY, DEAL_TYPE_SELL):
            continue                            # skip balance / credit / bonus rows
        pid = getattr(d, "position_id", None)
        if pid is None:
            continue
        by_position.setdefault(pid, []).append(d)

    trades: list[dict] = []
    for pid, legs in by_position.items():
        entries = [d for d in legs if getattr(d, "entry", None) == DEAL_ENTRY_IN]
        exits = [d for d in legs if getattr(d, "entry", None) == DEAL_ENTRY_OUT]
        if not entries or not exits:
            continue                            # still open, or history truncated
        first, last = entries[0], exits[-1]
        profit = sum(float(getattr(d, "profit", 0) or 0) for d in legs)
        commission = sum(float(getattr(d, "commission", 0) or 0) for d in legs)
        swap = sum(float(getattr(d, "swap", 0) or 0) for d in legs)
        opened = float(getattr(first, "time", 0) or 0)
        closed = float(getattr(last, "time", 0) or 0)
        trades.append({
            "position_id": pid,
            "symbol": getattr(first, "symbol", "") or "",
            # the ENTRY deal's type is the trade's direction
            "side": "BUY" if getattr(first, "type", 0) == DEAL_TYPE_BUY else "SELL",
            "volume": float(getattr(first, "volume", 0) or 0),
            "price_open": float(getattr(first, "price", 0) or 0),
            "price_close": float(getattr(last, "price", 0) or 0),
            "profit": round(profit, 2),
            "commission": round(commission, 2),
            "swap": round(swap, 2),
            # what actually landed in the account
            "net": round(profit + commission + swap, 2),
            "opened_at": opened,
            "closed_at": closed,
            "hold_hours": round((closed - opened) / 3600.0, 2) if closed and opened else None,
        })
    trades.sort(key=lambda t: t["closed_at"], reverse=True)
    return trades


def _normalize_position(p) -> dict:
    """MT5 position object -> our flat dict (tolerant of missing attributes)."""
    volume = float(getattr(p, "volume", 0) or 0)
    price_open = float(getattr(p, "price_open", 0) or 0)
    price_now = float(getattr(p, "price_current", 0) or 0)
    side = "BUY" if getattr(p, "type", POSITION_BUY) == POSITION_BUY else "SELL"
    # Percent move in the trade's favour — direction-aware, so a short that falls
    # shows a gain. Money P&L still comes from the broker's own `profit`.
    pnl_pct = None
    if price_open:
        raw = (price_now / price_open - 1) * 100.0
        pnl_pct = round(raw if side == "BUY" else -raw, 3)
    return {
        "ticket": getattr(p, "ticket", None),
        "symbol": getattr(p, "symbol", ""),
        "side": side,
        "volume": volume,
        "price_open": price_open,
        "price_current": price_now,
        "stop_loss": float(getattr(p, "sl", 0) or 0) or None,
        "take_profit": float(getattr(p, "tp", 0) or 0) or None,
        "profit": float(getattr(p, "profit", 0) or 0),
        "swap": float(getattr(p, "swap", 0) or 0),
        "pnl_pct": pnl_pct,
        "comment": getattr(p, "comment", "") or None,
    }
