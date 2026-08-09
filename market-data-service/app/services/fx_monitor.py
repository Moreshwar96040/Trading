"""FX / crypto risk monitor for MT5 (Exness) positions.

Deliberately NOT conviction scoring. The Alpha Stack's edge is ~70% fundamentals,
NSE relative strength, and Indian-market regime — none of which mean anything for
EURUSD or BTCUSD. Pretending otherwise would produce confident-looking scores
built on neutral placeholders.

What DOES transfer is risk management, because it's arithmetic on your own
position, not a claim about the asset:

  - no stop-loss              -> unbounded downside, and on leverage that's the
                                 account, not the position
  - price near / through stop -> decide before it decides for you
  - margin level              -> the actual liquidation risk on a leveraged book
  - single-symbol / currency concentration
  - swap bleed on positions carried a long time

Read-only: this reports. It never places, modifies, or closes an order.
"""
import logging
from collections import defaultdict

log = logging.getLogger(__name__)

NEAR_STOP_PCT = 1.0        # FX moves in small percentages — tighter than equities
MARGIN_WARN = 300.0        # % — below this the book is getting tight
MARGIN_DANGER = 150.0      # % — approaching stop-out territory
CONCENTRATION_PCT = 50.0   # one currency across positions
SWAP_BLEED = -5.0          # accumulated swap worth flagging


def _base_currencies(symbol: str) -> list[str]:
    """Rough currency split of an MT5 symbol: EURUSD -> [EUR, USD].
    Crypto and metals fall through as a single bucket (BTCUSD -> [BTC, USD])."""
    core = "".join(ch for ch in symbol.upper() if ch.isalpha())
    if len(core) >= 6:
        return [core[:3], core[3:6]]
    return [core] if core else []


def _stop_distance_pct(price_now: float, stop: float, side: str) -> float | None:
    """How far price sits from the stop, as a % of price, in the losing direction."""
    if not price_now or not stop:
        return None
    dist = (price_now - stop) if side == "BUY" else (stop - price_now)
    return dist / price_now * 100.0


def assess_fx_risk(state: dict) -> dict:
    """Turn an MT5 account snapshot into a prioritized action queue."""
    if state.get("status") != "OK":
        return {"status": state.get("status", "UNAVAILABLE"),
                "note": state.get("note"), "positions": [], "actions": []}

    account = state.get("account") or {}
    positions = state.get("positions") or []
    currency = account.get("currency") or ""
    actions: list[dict] = []
    exposure: dict[str, float] = defaultdict(float)
    no_stop: list[str] = []

    for p in positions:
        symbol = p.get("symbol") or "?"
        side = p.get("side", "BUY")
        price_now = float(p.get("price_current") or 0)
        stop = p.get("stop_loss")
        profit = float(p.get("profit") or 0)

        # Count how many POSITIONS touch each currency, not lots split across the
        # pair: splitting lots caps a USD-quoted book at exactly 50% and could
        # never flag, even when every ticket is a USD bet.
        for cur in set(_base_currencies(symbol)):
            exposure[cur] += 1.0

        if not stop:
            no_stop.append(symbol)
            actions.append({
                "severity": "high", "kind": "NO_STOP", "symbol": symbol,
                "text": f"{symbol} {side} {p.get('volume')} lot has no stop-loss — "
                        "on a leveraged position the downside is your account, not the trade."})
        else:
            dist = _stop_distance_pct(price_now, float(stop), side)
            if dist is not None and dist <= 0:
                actions.append({
                    "severity": "high", "kind": "STOP_BREACHED", "symbol": symbol,
                    "text": f"{symbol} has traded through its {stop} stop — "
                            "it should have closed; verify the position."})
            elif dist is not None and dist <= NEAR_STOP_PCT:
                actions.append({
                    "severity": "high", "kind": "NEAR_STOP", "symbol": symbol,
                    "text": f"{symbol} is {dist:.2f}% from its {stop} stop — decide now, "
                            "not after the next candle."})

        if float(p.get("swap") or 0) <= SWAP_BLEED:
            actions.append({
                "severity": "info", "kind": "SWAP_BLEED", "symbol": symbol,
                "text": f"{symbol} has accrued {p.get('swap')} {currency} in swap — "
                        "overnight financing is eating this trade."})

        if profit < 0 and stop is None:
            actions.append({
                "severity": "medium", "kind": "LOSING_NO_STOP", "symbol": symbol,
                "text": f"{symbol} is down {profit:.2f} {currency} with no stop set."})

    # ---- account-level: the leverage reality ----
    margin_level = float(account.get("margin_level") or 0)
    if margin_level and margin_level < MARGIN_DANGER:
        actions.append({
            "severity": "high", "kind": "MARGIN_DANGER", "symbol": None,
            "text": f"Margin level {margin_level:.0f}% — close to stop-out. "
                    "Reduce size or add funds before the broker decides for you."})
    elif margin_level and margin_level < MARGIN_WARN:
        actions.append({
            "severity": "medium", "kind": "MARGIN_TIGHT", "symbol": None,
            "text": f"Margin level {margin_level:.0f}% — little headroom for an adverse move."})

    if exposure and len(positions) >= 2:
        top_cur, touches = max(exposure.items(), key=lambda kv: kv[1])
        share = touches / len(positions) * 100.0
        if share > CONCENTRATION_PCT:
            actions.append({
                "severity": "medium", "kind": "CURRENCY_CONCENTRATION", "symbol": None,
                "text": f"{int(touches)} of {len(positions)} positions are exposed to "
                        f"{top_cur} ({share:.0f}%) — separate tickets, one bet."})

    if no_stop:
        actions.append({
            "severity": "info", "kind": "UNBOUNDED", "symbol": None,
            "text": f"Unbounded risk on {', '.join(no_stop)} — no stop means no "
                    "predefined loss."})

    rank = {"high": 0, "medium": 1, "info": 2}
    actions.sort(key=lambda a: rank[a["severity"]])
    return {
        "status": "OK", "account": account, "positions": positions, "actions": actions,
        "summary": {"open_positions": len(positions),
                    "high_priority": sum(1 for a in actions if a["severity"] == "high"),
                    "without_stop": len(no_stop),
                    "floating_pnl": round(sum(float(p.get("profit") or 0)
                                              for p in positions), 2)},
    }


def exness_account(settings) -> dict:
    """Fetch + assess in one call, driven by config."""
    from app.providers.mt5 import fetch_account_state
    state = fetch_account_state(
        login=getattr(settings, "mt5_login", None) or None,
        password=getattr(settings, "mt5_password", "") or None,
        server=getattr(settings, "mt5_server", "") or None,
        terminal_path=getattr(settings, "mt5_terminal_path", "") or None)
    return assess_fx_risk(state)
