from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import ScreenerSnapshot, Symbol
from app.services.guardian_service import position_health

# Paper tables are Spring-owned; the unit tests create minimal mirrors so the
# read-only SQL in guardian_service has something to query.
PAPER_DDL = [
    """CREATE TABLE paper_accounts (
        id INTEGER PRIMARY KEY, name TEXT, initial_cash NUMERIC,
        cash NUMERIC, realized_pnl NUMERIC DEFAULT 0)""",
    """CREATE TABLE paper_positions (
        id INTEGER PRIMARY KEY, account_id INTEGER, symbol_id INTEGER,
        quantity INTEGER, avg_cost NUMERIC, strategy_id INTEGER,
        stop_price NUMERIC, target_price NUMERIC)""",
]


def _setup(session: Session) -> Symbol:
    for ddl in PAPER_DDL:
        session.execute(text(ddl))
    session.execute(text(
        "INSERT INTO paper_accounts (id, name, initial_cash, cash) "
        "VALUES (1, 'default', 1000000, 500000)"))
    sym = Symbol(ticker="TCS", yahoo_symbol="TCS.NS", name="TCS Ltd", sector="IT")
    session.add(sym)
    session.commit()
    return sym


def _snapshot(session: Session, sym: Symbol, close: float, atr: float = 40.0,
              sma200: float | None = None) -> None:
    session.add(ScreenerSnapshot(symbol_id=sym.id, as_of_date=date(2026, 7, 10),
                                 close=close, atr_14=atr,
                                 sma_200=sma200 if sma200 is not None else close * 0.9))
    session.commit()


def _position(session: Session, sym: Symbol, qty: int, avg_cost: float,
              stop: float | None, target: float | None = None) -> None:
    session.execute(text(
        "INSERT INTO paper_positions (account_id, symbol_id, quantity, avg_cost, "
        "stop_price, target_price) VALUES (1, :sid, :q, :c, :s, :t)"),
        {"sid": sym.id, "q": qty, "c": avg_cost, "s": stop, "t": target})
    session.commit()


def test_no_positions(session: Session):
    for ddl in PAPER_DDL:
        session.execute(text(ddl))
    session.commit()
    assert position_health(session)["status"] == "NO_POSITIONS"


def test_missing_stop_is_flagged_high(session: Session):
    sym = _setup(session)
    _snapshot(session, sym, close=3000)
    _position(session, sym, qty=10, avg_cost=2900, stop=None)
    report = position_health(session)
    kinds = {a["kind"]: a for a in report["actions"]}
    assert kinds["STOP_MISSING"]["severity"] == "high"


def test_near_stop_flagged(session: Session):
    sym = _setup(session)
    _snapshot(session, sym, close=3000)
    _position(session, sym, qty=10, avg_cost=3100, stop=2950)   # 1.7% above stop
    kinds = {a["kind"] for a in position_health(session)["actions"]}
    assert "NEAR_STOP" in kinds


def test_raise_stop_suggested_when_in_profit(session: Session):
    sym = _setup(session)
    _snapshot(session, sym, close=3400, atr=40)    # suggested = 3400 - 2.5*40 = 3300
    _position(session, sym, qty=10, avg_cost=3000, stop=3050)
    actions = position_health(session)["actions"]
    raise_stop = next(a for a in actions if a["kind"] == "RAISE_STOP")
    assert raise_stop["suggested_stop"] == 3300.0


def test_stop_breached_flagged(session: Session):
    sym = _setup(session)
    _snapshot(session, sym, close=2900)
    _position(session, sym, qty=10, avg_cost=3100, stop=2950)
    kinds = {a["kind"] for a in position_health(session)["actions"]}
    assert "STOP_BREACHED" in kinds


def test_trend_flip_when_below_sma200(session: Session):
    sym = _setup(session)
    _snapshot(session, sym, close=3000, sma200=3200)
    _position(session, sym, qty=10, avg_cost=2900, stop=2800)
    kinds = {a["kind"] for a in position_health(session)["actions"]}
    assert "TREND_FLIP" in kinds


def test_stop_exposure_summary_present(session: Session):
    sym = _setup(session)
    _snapshot(session, sym, close=3000)
    _position(session, sym, qty=10, avg_cost=2900, stop=2850)
    report = position_health(session)
    exposure = next(a for a in report["actions"] if a["kind"] == "STOP_EXPOSURE")
    assert "1,500" in exposure["text"]         # (3000-2850)*10
    assert report["summary"]["open_positions"] == 1
