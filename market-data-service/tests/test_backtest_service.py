from datetime import date, timedelta

from sqlalchemy import func, select

from app.backtest.service import run_and_persist, validate_definition
from app.models import Backtest, BacktestTrade, OhlcvDaily, Strategy


GOOD_DEFINITION = {
    "entry": [{"left": "close", "op": "gt", "right": 105}],
    "exit": [{"left": "close", "op": "lt", "right": 103}],
    "stop_loss_pct": 5,
}


def test_validate_definition_good():
    assert validate_definition(GOOD_DEFINITION) == []


def test_validate_definition_problems():
    assert "at least one entry rule is required" in validate_definition({"exit": []})
    problems = validate_definition({"entry": [{"left": "bogus", "op": "gt", "right": 1}]})
    assert any("unknown left series" in p for p in problems)
    assert any("needs an exit" in p for p in problems)
    assert any("stop_loss_pct" in p for p in
               validate_definition({**GOOD_DEFINITION, "stop_loss_pct": -1}))


def _seed(session, reliance, prices):
    start = date(2026, 1, 1)
    for i, p in enumerate(prices):
        session.add(OhlcvDaily(symbol_id=reliance.id, trade_date=start + timedelta(days=i),
                               open=p, high=p + 1, low=p - 1, close=p, adj_close=p,
                               volume=1000))
    strategy = Strategy(name="test-strat", definition=GOOD_DEFINITION)
    session.add(strategy)
    session.commit()
    return strategy


def test_run_and_persist_success(session, reliance):
    strategy = _seed(session, reliance, [100.0, 106.0, 110.0, 102.0, 108.0, 109.0])

    summary = run_and_persist(session, strategy.id,
                              {"initial_capital": 10000, "max_positions": 1,
                               "commission_pct": 0})

    # Trade 1: entry@bar2 open 110; bar3 gaps to 102 < stop 104.5 -> STOP_LOSS at open.
    # Trade 2: re-entry signal bar4 (108>105) -> entry@bar5, closed at end of data.
    assert summary["status"] == "SUCCESS"
    assert summary["trades"] == 2
    record = session.get(Backtest, summary["backtest_id"])
    assert record.status == "SUCCESS"
    assert record.metrics["trades"] == 2
    assert len(record.equity_curve) > 0
    trades = session.scalars(select(BacktestTrade).order_by(BacktestTrade.entry_date)).all()
    assert len(trades) == 2
    assert trades[0].exit_reason == "STOP_LOSS"
    assert float(trades[0].exit_price) == 102.0          # gapped through the stop
    assert trades[1].exit_reason == "END_OF_DATA"


def test_run_unknown_strategy_raises(session):
    try:
        run_and_persist(session, 999, {})
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Unknown strategy" in str(exc)


def test_run_without_data_marks_failed(session, reliance):
    strategy = Strategy(name="no-data", definition=GOOD_DEFINITION)
    session.add(strategy)
    session.commit()

    try:
        run_and_persist(session, strategy.id, {})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    record = session.scalars(select(Backtest)).first()
    assert record.status == "FAILED"
    assert "No price data" in record.error
