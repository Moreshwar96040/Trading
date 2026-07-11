from datetime import date, timedelta

import pandas as pd
import pytest

from app.backtest.engine import BacktestParams, run_backtest
from app.backtest.metrics import compute_metrics


def _frame(prices: list[float], start=date(2026, 1, 1), spread=1.0) -> pd.DataFrame:
    """Synthetic OHLCV: open == close of the bar (flat bars) unless spread given."""
    idx = [start + timedelta(days=i) for i in range(len(prices))]
    return pd.DataFrame({
        "open": prices,
        "high": [p + spread for p in prices],
        "low": [p - spread for p in prices],
        "close": prices,
        "volume": [1000] * len(prices),
    }, index=idx)


ENTER_ABOVE_105 = [{"left": "close", "op": "gt", "right": 105}]
EXIT_BELOW_103 = [{"left": "close", "op": "lt", "right": 103}]


def test_entry_executes_next_open_no_lookahead():
    #                 0    1    2     3     4
    prices = [100.0, 106.0, 110.0, 111.0, 112.0]   # signal on bar 1 -> entry at bar 2 open
    result = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0))
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_date == date(2026, 1, 3)     # bar index 2
    assert trade.entry_price == 110.0


def test_exit_signal_executes_next_open():
    prices = [100.0, 106.0, 110.0, 102.0, 108.0, 109.0]
    # entry signal bar1 -> buy bar2 @110; exit signal bar3 (<103) -> sell bar4 open @108
    result = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, EXIT_BELOW_103,
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0))
    trade = result.trades[0]
    assert trade.exit_date == date(2026, 1, 5)
    assert trade.exit_price == 108.0
    assert trade.exit_reason == "SIGNAL"


def test_stop_loss_intrabar():
    prices = [100.0, 106.0, 110.0, 109.0, 108.0]
    # entry bar2 @110, stop 5% -> 104.5; bar3 low = 108 (no), bar4 low=107 (no) — widen:
    frame = _frame(prices, spread=6.0)              # bar3 low = 103 <= 104.5 -> stop
    result = run_backtest({"X": frame}, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0, stop_loss_pct=5.0))
    trade = result.trades[0]
    assert trade.exit_reason == "STOP_LOSS"
    assert trade.exit_price == pytest.approx(104.5)


def test_take_profit_intrabar():
    prices = [100.0, 106.0, 110.0, 115.0, 118.0]
    frame = _frame(prices, spread=8.0)              # bar3 high 123 >= 121 (10% of 110)
    result = run_backtest({"X": frame}, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0, take_profit_pct=10.0))
    trade = result.trades[0]
    assert trade.exit_reason == "TAKE_PROFIT"
    assert trade.exit_price == pytest.approx(121.0)


def test_max_holding_days():
    prices = [100.0, 106.0] + [110.0] * 10
    result = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0, max_holding_days=3))
    trade = result.trades[0]
    assert trade.exit_reason == "MAX_DAYS"
    # entry bar2, held bars 2,3,4 -> exit at bar5 open
    assert trade.exit_date == date(2026, 1, 6)


def test_end_of_data_closes_position():
    prices = [100.0, 106.0, 110.0, 111.0]
    result = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0))
    assert result.trades[0].exit_reason == "END_OF_DATA"
    assert result.trades[0].exit_price == 111.0


def test_commission_reduces_pnl():
    prices = [100.0, 106.0, 110.0, 111.0]
    free = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, [],
                        BacktestParams(10_000, 1, commission_pct=0.0))
    costly = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, [],
                          BacktestParams(10_000, 1, commission_pct=0.5))
    assert costly.trades[0].pnl < free.trades[0].pnl


def test_max_positions_respected():
    prices = [100.0, 106.0, 110.0, 111.0, 112.0, 113.0]
    data = {t: _frame(prices) for t in ["A", "B", "C"]}
    result = run_backtest(data, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=100_000, max_positions=2,
                                         commission_pct=0.0))
    assert len(result.trades) == 2                   # third symbol never entered


def test_equity_curve_starts_at_capital_and_metrics_sane():
    prices = [100.0, 106.0, 110.0, 121.0, 133.0]
    result = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0))
    metrics = compute_metrics(result.equity_curve, result.trades, 10_000)

    assert result.equity_curve.iloc[0] == pytest.approx(10_000)
    assert metrics["total_return_pct"] > 0
    assert metrics["trades"] == 1
    assert metrics["win_rate_pct"] == 100.0
    assert metrics["max_drawdown_pct"] <= 0


def test_known_drawdown():
    equity = pd.Series([100.0, 120.0, 90.0, 110.0])
    metrics = compute_metrics(equity, [], 100.0)
    assert metrics["max_drawdown_pct"] == pytest.approx(-25.0)   # 120 -> 90


def _ohlc_frame(rows: list[tuple], start=date(2026, 1, 1)) -> pd.DataFrame:
    idx = [start + timedelta(days=i) for i in range(len(rows))]
    o, h, l, c = zip(*rows)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": [1000] * len(rows)}, index=idx)


def test_atr_stop_fires_when_price_drops():
    prices = [100.0, 106.0, 110.0, 110.0, 110.0, 100.0]   # entry bar2 @110, deep drop bar5
    result = run_backtest({"X": _frame(prices)}, ENTER_ABOVE_105, [],
                          BacktestParams(initial_capital=10_000, max_positions=1,
                                         commission_pct=0.0, atr_stop_mult=2.0))
    trade = result.trades[0]
    assert trade.exit_reason == "ATR_STOP"
    assert trade.exit_price < trade.entry_price


def test_trailing_atr_stop_locks_in_more_than_fixed():
    # gentle climb, then a deep intraday drop on the last bar pierces both stops.
    rows = [(100, 101, 99, 100), (106, 107, 105, 106), (108, 109, 107, 108),
            (110, 111, 109, 110), (112, 113, 111, 112), (114, 115, 113, 114),
            (120, 120, 95, 100)]
    frame = _ohlc_frame(rows)
    fixed = run_backtest({"X": frame}, ENTER_ABOVE_105, [],
                         BacktestParams(10_000, 1, commission_pct=0.0, atr_stop_mult=2.0))
    trailing = run_backtest({"X": frame}, ENTER_ABOVE_105, [],
                            BacktestParams(10_000, 1, commission_pct=0.0,
                                           atr_stop_mult=2.0, atr_trail=True))
    assert fixed.trades[0].exit_reason == "ATR_STOP"
    assert trailing.trades[0].exit_reason == "ATR_STOP"
    # the ratcheting stop exits at a higher price -> captures more of the run
    assert trailing.trades[0].exit_price > fixed.trades[0].exit_price
