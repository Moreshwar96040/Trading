"""Exness/MT5 closed-trade analysis. Fully offline: deal pairing and the
analytics are pure functions over plain objects.
"""
from app.providers.mt5 import pair_deals
from app.services.fx_review import analyze_fx_trades


class _Deal:
    """Stand-in for an MT5 deal object."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _pair(position_id, symbol="EURUSD", side=0, volume=1.0, open_price=1.10,
          close_price=1.11, profit=100.0, commission=-2.0, swap=0.0,
          t_open=1_000_000, t_close=1_003_600):
    """One entry deal + one exit deal sharing a position_id."""
    return [
        _Deal(position_id=position_id, symbol=symbol, type=side, entry=0,
              volume=volume, price=open_price, profit=0.0, commission=commission / 2,
              swap=0.0, time=t_open),
        _Deal(position_id=position_id, symbol=symbol, type=1 - side, entry=1,
              volume=volume, price=close_price, profit=profit,
              commission=commission / 2, swap=swap, time=t_close),
    ]


def _state(trades):
    return {"status": "OK", "trades": trades, "days": 90}


# ---------- deal pairing ----------

def test_pairs_entry_and_exit_into_one_trade():
    trades = pair_deals(_pair(1, profit=100.0, commission=-4.0, swap=-1.0))
    assert len(trades) == 1
    t = trades[0]
    assert t["symbol"] == "EURUSD" and t["side"] == "BUY"
    assert t["profit"] == 100.0 and t["commission"] == -4.0 and t["swap"] == -1.0
    assert t["net"] == 95.0                      # profit + commission + swap
    assert t["hold_hours"] == 1.0


def test_skips_balance_operations_and_open_positions():
    deals = _pair(1) + [
        _Deal(position_id=None, symbol="", type=2, entry=0, profit=500.0),  # deposit
        _Deal(position_id=9, symbol="GBPUSD", type=0, entry=0, volume=1.0,  # still open
              price=1.2, profit=0.0, commission=0.0, swap=0.0, time=1_000_000),
    ]
    trades = pair_deals(deals)
    assert len(trades) == 1 and trades[0]["position_id"] == 1


def test_sell_side_detected_from_entry_deal():
    trades = pair_deals(_pair(2, side=1))
    assert trades[0]["side"] == "SELL"


def test_trades_sorted_newest_first():
    deals = _pair(1, t_close=1_000) + _pair(2, t_close=9_000)
    assert [t["position_id"] for t in pair_deals(deals)] == [2, 1]


# ---------- analytics ----------

def _t(net, symbol="EURUSD", hold=2.0, swap=0.0, volume=1.0):
    return {"position_id": id(object()), "symbol": symbol, "side": "BUY",
            "volume": volume, "price_open": 1.1, "price_close": 1.11,
            "profit": net, "commission": 0.0, "swap": swap, "net": net,
            "opened_at": 1_000_000, "closed_at": 1_003_600, "hold_hours": hold}


def test_core_stats_are_correct():
    out = analyze_fx_trades(_state([_t(100), _t(50), _t(-30), _t(-20)]))
    s = out["stats"]
    assert s["trades"] == 4 and s["wins"] == 2 and s["losses"] == 2
    assert s["win_rate_pct"] == 50.0
    assert s["net"] == 100.0
    assert s["gross_profit"] == 150.0 and s["gross_loss"] == 50.0
    assert s["profit_factor"] == 3.0
    assert s["expectancy"] == 25.0
    assert s["avg_win"] == 75.0 and s["avg_loss"] == 25.0
    assert s["payoff_ratio"] == 3.0
    assert s["best"] == 100 and s["worst"] == -30


def test_payoff_leak_when_losses_exceed_wins():
    out = analyze_fx_trades(_state([_t(20), _t(20), _t(-80)]))
    assert "PAYOFF" in {l["kind"] for l in out["leaks"]}


def test_hold_asymmetry_leak_detects_hoping_on_losers():
    out = analyze_fx_trades(_state([_t(50, hold=1.0), _t(60, hold=1.0),
                                    _t(-40, hold=20.0)]))
    kinds = {l["kind"] for l in out["leaks"]}
    assert "HOLD_ASYMMETRY" in kinds


def test_swap_drag_leak():
    out = analyze_fx_trades(_state([_t(100, swap=-30.0), _t(50, swap=-10.0)]))
    assert "SWAP_DRAG" in {l["kind"] for l in out["leaks"]}


def test_losing_symbol_is_named():
    trades = [_t(-10, symbol="GBPJPY") for _ in range(4)] + [_t(200)]
    out = analyze_fx_trades(_state(trades))
    leak = next(l for l in out["leaks"] if l["kind"] == "LOSING_SYMBOL")
    assert "GBPJPY" in leak["text"]


def test_unprofitable_book_flagged():
    out = analyze_fx_trades(_state([_t(10), _t(-100)]))
    assert "UNPROFITABLE" in {l["kind"] for l in out["leaks"]}


def test_healthy_book_has_no_high_severity_leaks():
    trades = [_t(100, hold=3.0), _t(90, hold=3.0), _t(-20, hold=2.0)]
    out = analyze_fx_trades(_state(trades))
    assert not [l for l in out["leaks"] if l["severity"] == "high"]


def test_per_symbol_table_sorted_worst_first():
    out = analyze_fx_trades(_state([_t(100, symbol="EURUSD"), _t(-50, symbol="BTCUSD")]))
    assert out["symbols"][0]["symbol"] == "BTCUSD"
    assert out["symbols"][0]["net"] == -50.0


def test_no_trades_and_unavailable_states():
    assert analyze_fx_trades(_state([]))["status"] == "NO_TRADES"
    out = analyze_fx_trades({"status": "UNAVAILABLE", "note": "no package"})
    assert out["status"] == "UNAVAILABLE" and out["note"] == "no package"
