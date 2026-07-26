from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Backtest, Strategy
from app.services.edge_gates import edge_gates

PAPER_DDL = """CREATE TABLE paper_orders (
    id INTEGER PRIMARY KEY, account_id INTEGER, symbol_id INTEGER,
    side TEXT, quantity INTEGER, price NUMERIC, realized_pnl NUMERIC,
    status TEXT, strategy_id INTEGER, stop_price NUMERIC, target_price NUMERIC)"""


def _strategy(session: Session, name: str = "S1") -> Strategy:
    session.execute(text(PAPER_DDL))
    s = Strategy(name=name, definition={"entry": [], "exit": []})
    session.add(s)
    session.commit()
    return s


def _backtest(session: Session, strategy_id: int, trades: int, score: int,
              oos: float | None) -> None:
    session.add(Backtest(strategy_id=strategy_id, params={}, status="SUCCESS",
                         metrics={"trades": trades,
                                  "robustness": {"score": score,
                                                 "holdout": {"out_sample_return_pct": oos}}}))
    session.commit()


def _paper_sells(session: Session, strategy_id: int, pnls: list[float]) -> None:
    for pnl in pnls:
        session.execute(text(
            "INSERT INTO paper_orders (side, quantity, realized_pnl, status, strategy_id) "
            "VALUES ('SELL', 1, :p, 'FILLED', :sid)"), {"p": pnl, "sid": strategy_id})
    session.commit()


def test_untested_strategy(session: Session):
    _strategy(session)
    report = edge_gates(session)
    s = report["strategies"][0]
    assert s["verdict"] == "UNTESTED"
    assert s["gates"]["sample"]["status"] == "PENDING"


def test_fails_on_small_sample_and_weak_robustness(session: Session):
    s = _strategy(session)
    _backtest(session, s.id, trades=8, score=30, oos=-5.0)
    result = edge_gates(session)["strategies"][0]
    assert result["gates"]["sample"]["status"] == "FAIL"
    assert result["gates"]["robustness"]["status"] == "FAIL"
    assert result["verdict"] == "FAILED"


def test_fully_validated_strategy(session: Session):
    s = _strategy(session)
    _backtest(session, s.id, trades=45, score=78, oos=12.0)
    _paper_sells(session, s.id, [500.0] * 10 + [-200.0] * 6)   # 16 closed, +ve expectancy
    result = edge_gates(session)["strategies"][0]
    assert all(result["gates"][g]["status"] == "PASS"
               for g in ("sample", "robustness", "paper", "live_edge"))
    assert result["verdict"] == "VALIDATED"


def test_live_edge_failure_flags_red(session: Session):
    s = _strategy(session)
    _backtest(session, s.id, trades=45, score=78, oos=12.0)
    _paper_sells(session, s.id, [-300.0] * 16)                 # reality disagrees
    result = edge_gates(session)["strategies"][0]
    assert result["gates"]["live_edge"]["status"] == "FAIL"
    assert result["verdict"] == "FAILED"


def test_in_progress_when_paper_pending(session: Session):
    s = _strategy(session)
    _backtest(session, s.id, trades=45, score=78, oos=12.0)
    _paper_sells(session, s.id, [400.0] * 5)                   # only 5 of 15
    result = edge_gates(session)["strategies"][0]
    assert result["gates"]["paper"]["status"] == "PENDING"
    assert result["verdict"] == "IN_PROGRESS"


def test_validated_sorts_first(session: Session):
    good = _strategy(session, "GOOD")
    bad = Strategy(name="BAD", definition={"entry": []})
    session.add(bad)
    session.commit()
    _backtest(session, good.id, trades=45, score=80, oos=10.0)
    _paper_sells(session, good.id, [100.0] * 16)
    _backtest(session, bad.id, trades=5, score=20, oos=-3.0)
    names = [s["name"] for s in edge_gates(session)["strategies"]]
    assert names == ["GOOD", "BAD"]
