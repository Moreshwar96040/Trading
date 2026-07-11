import pandas as pd
import pytest

from app.backtest.rules import (RuleError, combined_signal, resolve_series, rule_signal,
                                validate_rules)


@pytest.fixture
def df():
    n = 30
    return pd.DataFrame({
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.5 + i for i in range(n)],
        "volume": [1000] * n,
    })


def test_resolve_price_and_parametrized_series(df):
    assert resolve_series(df, "close").iloc[0] == 100.5
    assert resolve_series(df, "sma_5").iloc[4] == pytest.approx(102.5)
    assert resolve_series(df, "rsi_14").iloc[-1] == pytest.approx(100.0)  # monotonic up
    with pytest.raises(RuleError):
        resolve_series(df, "wma_10")


def test_gt_rule_against_number(df):
    sig = rule_signal(df, {"left": "close", "op": "gt", "right": 110})
    assert not sig.iloc[0]
    assert sig.iloc[-1]


def test_crosses_above_fires_exactly_once():
    # fast crosses slow exactly at index 3
    fast = [1.0, 2.0, 3.0, 5.0, 6.0]
    df = pd.DataFrame({"open": fast, "high": fast, "low": fast, "close": fast,
                       "volume": [1] * 5})
    sig = rule_signal(df, {"left": "close", "op": "crosses_above", "right": 4})
    assert list(sig) == [False, False, False, True, False]


def test_crossover_nan_warmup_never_fires(df):
    # sma_20 is NaN for 19 bars — no phantom crossovers during warm-up
    sig = rule_signal(df, {"left": "sma_5", "op": "crosses_above", "right": "sma_20"})
    assert not sig[:20].any()


def test_combined_signal_is_and(df):
    rules = [{"left": "close", "op": "gt", "right": 105},
             {"left": "close", "op": "lt", "right": 110}]
    sig = combined_signal(df, rules)
    closes = df["close"]
    expected = (closes > 105) & (closes < 110)
    assert (sig == expected).all()


def test_empty_rules_never_signal(df):
    assert not combined_signal(df, []).any()


def test_validate_rules_catches_problems():
    problems = validate_rules([
        {"left": "closeX", "op": "gt", "right": 1},
        {"left": "close", "op": "like", "right": 1},
        {"left": "close", "op": "gt", "right": True},
        "not-a-dict",
    ])
    assert len(problems) == 4
    assert validate_rules([{"left": "sma_20", "op": "crosses_above", "right": "sma_50"}]) == []
