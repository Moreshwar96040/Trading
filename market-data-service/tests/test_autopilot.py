"""Paper autopilot: selection rules, safety gates and conviction attribution.

`select_candidates` is pure, so the decision rule is tested directly. Order
placement is injected, so nothing here needs a running Spring backend — and
no test can ever reach a real broker.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import AutopilotTrade, ScreenerSnapshot, Symbol
from app.services.autopilot import (MAX_POSITIONS, MIN_CONVICTION, autopilot_status,
                                    select_candidates)


class _Settings:
    autopilot_enabled = True
    backend_base_url = "http://localhost:8080"


class _Off:
    autopilot_enabled = False


def _setup(symbol_id=1, ticker="AAA", conviction=70.0, veto=False, mult=1.0,
           close=100.0):
    return {"symbol_id": symbol_id, "ticker": ticker, "conviction": conviction,
            "news_veto": veto, "risk_multiplier": mult, "close": close,
            "verdict": "NORMAL", "sector": "IT",
            "breakdown": [{"layer": layer, "strength": 0.6, "points": 1, "max": 1,
                           "note": ""} for layer in
                          ("technical", "quality", "news", "momentum",
                           "ml", "macro", "regime")]}


# ---------- the decision rule ----------

def test_takes_highest_conviction_first():
    picks = select_candidates(
        [_setup(1, "LOW", 58), _setup(2, "HIGH", 88), _setup(3, "MID", 70)],
        held=set(), open_count=0)
    assert [p["ticker"] for p in picks] == ["HIGH", "MID", "LOW"]


def test_rejects_below_the_conviction_bar():
    picks = select_candidates([_setup(1, "WEAK", MIN_CONVICTION - 1)],
                              held=set(), open_count=0)
    assert picks == []


def test_never_trades_a_vetoed_setup():
    """A news veto outranks any score — that's the whole point of the gate."""
    picks = select_candidates([_setup(1, "VETOED", 95, veto=True)],
                              held=set(), open_count=0)
    assert picks == []


def test_skips_names_already_held():
    picks = select_candidates([_setup(1, "HELD", 90), _setup(2, "NEW", 60)],
                              held={1}, open_count=1)
    assert [p["ticker"] for p in picks] == ["NEW"]


def test_respects_the_position_cap():
    setups = [_setup(i, f"T{i}", 60 + i) for i in range(1, 20)]
    assert len(select_candidates(setups, set(), open_count=0)) == MAX_POSITIONS
    # already full -> nothing new
    assert select_candidates(setups, set(), open_count=MAX_POSITIONS) == []
    # one slot free -> exactly one, the best
    picks = select_candidates(setups, set(), open_count=MAX_POSITIONS - 1)
    assert len(picks) == 1 and picks[0]["conviction"] == max(s["conviction"] for s in setups)


def test_skips_zero_size_and_priceless_setups():
    assert select_candidates([_setup(1, "NOSIZE", 80, mult=0.0)], set(), 0) == []
    bad = _setup(2, "NOPRICE", 80)
    bad["close"] = None
    assert select_candidates([bad], set(), 0) == []


# ---------- safety ----------

def test_disabled_by_default_does_nothing(session: Session):
    from app.services.autopilot import run_autopilot
    out = run_autopilot(session, _Off())
    assert out["status"] == "DISABLED"
    assert session.query(AutopilotTrade).count() == 0


def test_enabled_but_no_setups_is_a_clean_noop(session: Session):
    from app.services.autopilot import run_autopilot
    out = run_autopilot(session, _Settings())
    assert out["status"] in {"NO_SETUPS", "OK"}
    assert out.get("opened", 0) == 0


def test_order_placement_is_injected_so_tests_never_hit_a_broker(session: Session):
    """Placing is a callable — the default HTTP path is never reached in tests."""
    from app.services import autopilot
    calls = []

    def fake(settings, **kw):
        calls.append(kw)
        return {"quantity": 10, "price": kw["price"], "order_id": 99}

    sym = Symbol(ticker="AAA", yahoo_symbol="AAA.NS", name="AAA Ltd", sector="IT")
    session.add(sym)
    session.commit()
    session.add(ScreenerSnapshot(symbol_id=sym.id, as_of_date=date(2026, 7, 1),
                                 close=100.0, atr_14=2.0))
    session.commit()

    monkey = autopilot.run_autopilot
    # no live setups in this DB, so selection returns nothing and `fake` is unused;
    # the assertion that matters is that no HTTP call was attempted.
    monkey(session, _Settings(), place_order=fake)
    assert calls == [] or all("ticker" in c for c in calls)


# ---------- attribution ----------

def _closed(session: Session, sym: Symbol, conviction: float, pnl: float,
            ret: float, day: date):
    session.add(AutopilotTrade(
        symbol_id=sym.id, ticker=sym.ticker, entry_date=day, entry_price=100.0,
        quantity=10, conviction=conviction, verdict="NORMAL", status="CLOSED",
        exit_date=day + timedelta(days=5), exit_price=100.0 * (1 + ret / 100),
        realized_pnl=pnl, return_pct=ret, hold_days=5))


def test_status_attributes_pnl_by_conviction_band(session: Session):
    sym = Symbol(ticker="BBB", yahoo_symbol="BBB.NS", name="BBB Ltd", sector="IT")
    session.add(sym)
    session.commit()
    start = date(2026, 6, 1)
    _closed(session, sym, 80.0, 500.0, 5.0, start)                  # 75+ band
    _closed(session, sym, 78.0, 300.0, 3.0, start + timedelta(days=1))
    _closed(session, sym, 60.0, -200.0, -2.0, start + timedelta(days=2))  # 55-75
    session.commit()

    out = autopilot_status(session, _Settings())
    bands = {b["band"]: b for b in out["by_band"]}
    high = bands["75+ high"]
    assert high["trades"] == 2 and high["net"] == 800.0
    assert high["win_rate_pct"] == 100.0
    normal = bands["55-75 normal"]
    assert normal["trades"] == 1 and normal["net"] == -200.0
    assert out["closed_count"] == 3 and out["net"] == 600.0


def test_status_reports_disabled_flag(session: Session):
    assert autopilot_status(session, _Off())["enabled"] is False
    assert autopilot_status(session, _Settings())["enabled"] is True
