"""Live strategy-signal evaluation (Phase A of the trading loop)."""
from datetime import date, timedelta

from sqlalchemy import select

from app.models import OhlcvDaily, Strategy, StrategySignal
from app.services.signal_service import evaluate_signals


def _load_prices(session, symbol_id, closes, start=date(2026, 1, 1)):
    for i, c in enumerate(closes):
        session.add(OhlcvDaily(symbol_id=symbol_id, trade_date=start + timedelta(days=i),
                               open=c, high=c + 1, low=c - 1, close=c, volume=1000))
    session.commit()


def _strategy(session, name, entry, exit_rules=None, **extra) -> Strategy:
    definition = {"entry": entry, "exit": exit_rules or [], "stop_loss_pct": 5, **extra}
    s = Strategy(name=name, definition=definition)
    session.add(s)
    session.commit()
    return s


def test_entry_signal_fires_on_last_bar(session, reliance):
    _load_prices(session, reliance.id, [100.0] * 40 + [150.0])   # last close > 120
    _strategy(session, "Breakout", [{"left": "close", "op": "gt", "right": 120}])

    result = evaluate_signals(session)

    assert result["signals"] == 1
    sig = session.scalars(select(StrategySignal)).one()
    assert sig.signal == "ENTRY"
    assert float(sig.close) == 150.0
    assert sig.as_of_date == date(2026, 1, 1) + timedelta(days=40)


def test_no_signal_when_rule_not_met(session, reliance):
    _load_prices(session, reliance.id, [100.0] * 41)
    _strategy(session, "Breakout", [{"left": "close", "op": "gt", "right": 120}])

    assert evaluate_signals(session)["signals"] == 0
    assert session.scalars(select(StrategySignal)).all() == []


def test_exit_signal_evaluated_independently(session, reliance):
    _load_prices(session, reliance.id, [100.0] * 40 + [80.0])
    _strategy(session, "MeanRev",
              entry=[{"left": "close", "op": "gt", "right": 200}],       # won't fire
              exit_rules=[{"left": "close", "op": "lt", "right": 90}])   # fires

    result = evaluate_signals(session)

    sig = session.scalars(select(StrategySignal)).one()
    assert sig.signal == "EXIT"
    assert result["signals"] == 1


def test_stale_signals_replaced_on_reevaluation(session, reliance):
    _load_prices(session, reliance.id, [100.0] * 40 + [150.0])
    strat = _strategy(session, "Breakout", [{"left": "close", "op": "gt", "right": 120}])

    assert evaluate_signals(session)["signals"] == 1
    # tighten the rule so nothing fires — the old signal must disappear
    strat.definition = {"entry": [{"left": "close", "op": "gt", "right": 999}],
                        "exit": [], "stop_loss_pct": 5}
    session.commit()

    assert evaluate_signals(session)["signals"] == 0
    assert session.scalars(select(StrategySignal)).all() == []


def test_invalid_strategy_skipped_not_crashed(session, reliance):
    _load_prices(session, reliance.id, [100.0] * 41)
    session.add(Strategy(name="Broken", definition={"entry": []}))     # invalid: no entry
    session.commit()

    result = evaluate_signals(session)

    assert result["signals"] == 0
    assert result["skipped_invalid"] == ["Broken"]


def test_short_history_symbol_ignored(session, reliance):
    _load_prices(session, reliance.id, [150.0] * 5)                    # < MIN_BARS
    _strategy(session, "Breakout", [{"left": "close", "op": "gt", "right": 120}])

    assert evaluate_signals(session)["symbols"] == 0
