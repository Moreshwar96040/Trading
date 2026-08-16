"""Circuit breakers.

A breaker that cannot be made to trip in a test is a breaker that will not trip
in production either, so each one is driven to its threshold deliberately.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services.circuit_breakers import (MAX_LOSS_STREAK, check_drawdown,
                                           check_ic_collapse,
                                           check_labelling_alive,
                                           check_loss_streak,
                                           check_price_staleness, evaluate)


# ---------- drawdown ----------

def test_drawdown_is_measured_from_the_peak_not_the_start():
    """Up 100 then down 20 is a 20% drawdown, not a 80-point profit worth ignoring."""
    r = check_drawdown([100.0, -20.0], limit_pct=15.0)
    assert r.tripped and r.detail["drawdown_pct"] == 20.0


def test_a_rising_curve_never_trips():
    assert not check_drawdown([10.0, 10.0, 10.0, 10.0]).tripped


def test_a_book_that_was_never_profitable_still_trips():
    """The dangerous case: peak is zero, so a naive percentage would read 0%."""
    r = check_drawdown([-50.0, -50.0])
    assert r.tripped and r.detail["drawdown_pct"] == 100.0


def test_no_trades_is_not_a_drawdown():
    assert not check_drawdown([]).tripped


def test_recovery_still_counts_the_dip():
    """Down and back up is still a drawdown that happened — the breaker looks at
    the worst point, not the current one."""
    r = check_drawdown([100.0, -30.0, 40.0], limit_pct=15.0)
    assert r.tripped


# ---------- loss streak ----------

def test_loss_streak_trips_at_the_limit():
    assert check_loss_streak([-1.0] * MAX_LOSS_STREAK).tripped


def test_a_single_win_resets_the_streak():
    pnl = [-1.0] * (MAX_LOSS_STREAK - 1) + [5.0] + [-1.0] * 2
    r = check_loss_streak(pnl)
    assert not r.tripped and r.detail["streak"] == 2


def test_streak_counts_from_the_most_recent_trade():
    """Old losses are history; recent ones are a signal."""
    pnl = [-1.0] * 10 + [1.0]
    assert check_loss_streak(pnl).detail["streak"] == 0


# ---------- IC collapse ----------

def _seed_conviction(session: Session, n: int, *, predictive: bool,
                     days_ago: int = 10) -> None:
    import random

    from app.models import ConvictionHistory, Symbol

    rng = random.Random(3)
    span = 60                    # days the rows are spread across, inside the window
    symbols = []
    for i in range((n // span) + 1):
        s = Symbol(ticker=f"IC{i}", yahoo_symbol=f"IC{i}.NS", name=f"IC Test {i}",
                   exchange="NSE", active=True)
        session.add(s)
        symbols.append(s)
    session.flush()
    base = date.today() - timedelta(days=days_ago)
    for i in range(n):
        conviction = rng.uniform(20, 90)
        label = (conviction - 55) / 10.0 if predictive else rng.gauss(0, 3)
        session.add(ConvictionHistory(
            symbol_id=symbols[i // span].id,
            as_of_date=base - timedelta(days=i % span),
            conviction=round(conviction, 2), verdict="WATCH",
            fwd_return_10d=round(label, 4), close=100.0))
    session.commit()


def test_ic_collapse_stays_quiet_until_there_is_enough_data(session: Session):
    """Silence is the right answer when we cannot tell — a breaker that trips on
    missing data halts a healthy system on its first week."""
    _seed_conviction(session, 20, predictive=False)
    r = check_ic_collapse(session)
    assert not r.tripped and "need" in r.reason


def test_ic_collapse_trips_when_the_score_stops_ranking(session: Session):
    _seed_conviction(session, 200, predictive=False)
    r = check_ic_collapse(session, floor=0.05)
    assert r.tripped and r.severity == "HALT"


def test_a_working_score_does_not_trip(session: Session):
    _seed_conviction(session, 200, predictive=True)
    assert not check_ic_collapse(session).tripped


def test_ic_window_ignores_ancient_history(session: Session):
    """A model that worked last year and is broken now must still trip."""
    _seed_conviction(session, 200, predictive=True, days_ago=400)
    r = check_ic_collapse(session, window_days=90)
    assert not r.tripped and "need" in r.reason      # nothing recent to judge


# ---------- data freshness ----------

def test_no_prices_at_all_is_a_halt(session: Session):
    r = check_price_staleness(session)
    assert r.tripped and r.severity == "HALT"


def test_stale_prices_halt_trading(session: Session):
    from app.models import OhlcvDaily, Symbol
    sym = Symbol(ticker="STL", yahoo_symbol="STL.NS", name="Stale",
                 exchange="NSE", active=True)
    session.add(sym)
    session.flush()
    session.add(OhlcvDaily(symbol_id=sym.id,
                           trade_date=date.today() - timedelta(days=30),
                           open=1, high=1, low=1, close=1, volume=1))
    session.commit()
    r = check_price_staleness(session)
    assert r.tripped and r.detail["age_days"] == 30


def test_fresh_prices_pass(session: Session):
    from app.models import OhlcvDaily, Symbol
    sym = Symbol(ticker="FRS", yahoo_symbol="FRS.NS", name="Fresh",
                 exchange="NSE", active=True)
    session.add(sym)
    session.flush()
    session.add(OhlcvDaily(symbol_id=sym.id, trade_date=date.today(),
                           open=1, high=1, low=1, close=1, volume=1))
    session.commit()
    assert not check_price_staleness(session).tripped


# ---------- labelling ----------

def test_dead_labelling_warns_rather_than_halting(session: Session):
    """The model in use was still validated — this is a maintenance problem,
    not a reason to stop trading."""
    from app.models import ConvictionHistory, Symbol
    sym = Symbol(ticker="LBL", yahoo_symbol="LBL.NS", name="Label",
                 exchange="NSE", active=True)
    session.add(sym)
    session.flush()
    session.add(ConvictionHistory(
        symbol_id=sym.id, as_of_date=date.today() - timedelta(days=200),
        conviction=50.0, verdict="WATCH", close=100.0, fwd_return_10d=1.0,
        labelled_at=datetime.now(timezone.utc) - timedelta(days=90)))
    session.commit()
    r = check_labelling_alive(session)
    assert r.tripped and r.severity == "WARN"


# ---------- combination ----------

def test_a_halt_blocks_entries_and_says_why(session: Session):
    out = evaluate(session, closed_pnl=[100.0, -50.0])
    assert out["halted"]                       # no prices seeded -> stale_data halts
    assert "stale_data" in out["halt_reasons"]
    assert "Open positions keep their stops" in out["summary"]


def test_warnings_alone_do_not_halt(session: Session):
    from app.models import OhlcvDaily, Symbol
    sym = Symbol(ticker="OKY", yahoo_symbol="OKY.NS", name="Okay",
                 exchange="NSE", active=True)
    session.add(sym)
    session.flush()
    session.add(OhlcvDaily(symbol_id=sym.id, trade_date=date.today(),
                           open=1, high=1, low=1, close=1, volume=1))
    session.commit()
    out = evaluate(session, closed_pnl=[])
    assert not out["halted"]


def test_autopilot_refuses_to_run_while_halted(session: Session):
    """The breaker must actually be wired in, not merely reported."""
    from app.services.autopilot import run_autopilot

    class Settings:
        autopilot_enabled = True

    out = run_autopilot(session, Settings())
    assert out["status"] == "HALTED" and out["opened"] == 0
