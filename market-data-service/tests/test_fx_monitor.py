"""FX/crypto risk monitor (Exness via MT5).

All offline: `assess_fx_risk` is pure over an account snapshot, and the MT5
provider is exercised only for its graceful-degradation path (the package is
Windows-only and absent in CI).
"""
from app.providers.mt5 import _normalize_position, fetch_account_state
from app.services.fx_monitor import _base_currencies, assess_fx_risk


class _Pos:
    """Stand-in for an MT5 position object."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _state(positions, **account):
    base = {"currency": "USD", "balance": 5000.0, "equity": 5000.0,
            "margin": 500.0, "margin_free": 4500.0, "margin_level": 1000.0,
            "profit": 0.0, "login": 123, "server": "Exness-MT5Real", "leverage": 500}
    base.update(account)
    return {"status": "OK", "account": base, "positions": positions}


def _p(symbol="EURUSD", side="BUY", price_current=1.09, stop_loss=None, **kw):
    row = {"symbol": symbol, "side": side, "volume": 0.5, "price_open": 1.08,
           "price_current": price_current, "stop_loss": stop_loss,
           "take_profit": None, "profit": 10.0, "swap": 0.0}
    row.update(kw)
    return row


# ---------- provider degradation ----------

def test_provider_reports_unavailable_without_mt5():
    """No MetaTrader5 package (Linux/CI) must be a status, never an exception."""
    out = fetch_account_state()
    assert out["status"] in {"UNAVAILABLE", "NOT_CONNECTED", "ERROR"}
    assert out["positions"] == []
    assert out.get("note")


def test_normalize_position_is_direction_aware():
    buy = _normalize_position(_Pos(ticket=1, symbol="EURUSD", type=0, volume=1.0,
                                   price_open=1.00, price_current=1.02, sl=0.0, tp=0.0,
                                   profit=200.0, swap=0.0, comment=""))
    assert buy["side"] == "BUY" and buy["pnl_pct"] > 0
    # a short that falls is a WINNER — the sign must flip
    sell = _normalize_position(_Pos(ticket=2, symbol="EURUSD", type=1, volume=1.0,
                                    price_open=1.00, price_current=0.98, sl=0.0, tp=0.0,
                                    profit=200.0, swap=0.0, comment=""))
    assert sell["side"] == "SELL" and sell["pnl_pct"] > 0
    assert sell["stop_loss"] is None            # 0.0 means "unset", not a real stop


# ---------- currency parsing ----------

def test_base_currencies_splits_fx_and_handles_crypto():
    assert _base_currencies("EURUSD") == ["EUR", "USD"]
    assert _base_currencies("BTCUSD") == ["BTC", "USD"]
    assert _base_currencies("XAU") == ["XAU"]


# ---------- risk assessment ----------

def test_missing_stop_is_high_priority():
    out = assess_fx_risk(_state([_p(stop_loss=None)]))
    kinds = {a["kind"] for a in out["actions"]}
    assert "NO_STOP" in kinds
    assert out["summary"]["without_stop"] == 1
    assert any(a["severity"] == "high" for a in out["actions"])


def test_near_stop_flags_before_it_hits():
    # BUY at 1.0900 with a stop at 1.0895 -> ~0.05% away
    out = assess_fx_risk(_state([_p(price_current=1.0900, stop_loss=1.0895)]))
    assert "NEAR_STOP" in {a["kind"] for a in out["actions"]}


def test_stop_far_away_is_quiet():
    out = assess_fx_risk(_state([_p(price_current=1.10, stop_loss=1.05)]))
    kinds = {a["kind"] for a in out["actions"]}
    assert "NEAR_STOP" not in kinds and "NO_STOP" not in kinds


def test_breached_stop_is_reported():
    # a SELL whose price rose above the stop
    out = assess_fx_risk(_state([_p(side="SELL", price_current=1.12, stop_loss=1.10)]))
    assert "STOP_BREACHED" in {a["kind"] for a in out["actions"]}


def test_margin_level_danger_and_warning():
    danger = assess_fx_risk(_state([_p(stop_loss=1.05)], margin_level=120.0))
    assert "MARGIN_DANGER" in {a["kind"] for a in danger["actions"]}
    warn = assess_fx_risk(_state([_p(stop_loss=1.05)], margin_level=250.0))
    assert "MARGIN_TIGHT" in {a["kind"] for a in warn["actions"]}
    calm = assess_fx_risk(_state([_p(stop_loss=1.05)], margin_level=900.0))
    assert not {"MARGIN_DANGER", "MARGIN_TIGHT"} & {a["kind"] for a in calm["actions"]}


def test_currency_concentration_flagged():
    """Every ticket quoted in USD is one bet wearing three hats."""
    out = assess_fx_risk(_state([
        _p(symbol="EURUSD", price_current=1.09, stop_loss=1.05),
        _p(symbol="GBPUSD", price_current=1.27, stop_loss=1.22),
        _p(symbol="AUDUSD", price_current=0.66, stop_loss=0.63)]))
    assert "CURRENCY_CONCENTRATION" in {a["kind"] for a in out["actions"]}


def test_diverse_book_is_not_flagged_for_concentration():
    out = assess_fx_risk(_state([
        _p(symbol="EURGBP", price_current=0.85, stop_loss=0.82),
        _p(symbol="AUDJPY", price_current=98.0, stop_loss=95.0)]))
    assert "CURRENCY_CONCENTRATION" not in {a["kind"] for a in out["actions"]}


def test_swap_bleed_flagged():
    out = assess_fx_risk(_state([_p(stop_loss=1.05, swap=-12.0)]))
    assert "SWAP_BLEED" in {a["kind"] for a in out["actions"]}


def test_floating_pnl_summed():
    out = assess_fx_risk(_state([_p(stop_loss=1.05, profit=25.0),
                                 _p(symbol="BTCUSD", stop_loss=60000, profit=-10.0)]))
    assert out["summary"]["floating_pnl"] == 15.0
    assert out["summary"]["open_positions"] == 2


def test_unavailable_state_passes_through_cleanly():
    out = assess_fx_risk({"status": "UNAVAILABLE", "note": "no package", "positions": []})
    assert out["status"] == "UNAVAILABLE" and out["actions"] == []
    assert out["note"] == "no package"
