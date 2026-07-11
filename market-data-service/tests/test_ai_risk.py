"""Adaptive risk recommendation engine (R4) — regime + volatility scaling."""
import numpy as np
import pandas as pd
import pytest

from app.ai.risk import InsufficientDataError, recommend_risk


def _frame(close: np.ndarray, spread: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame({
        "open": close, "high": close + spread, "low": close - spread,
        "close": close, "volume": [1000] * len(close),
    })


def test_insufficient_data_raises():
    with pytest.raises(InsufficientDataError):
        recommend_risk(_frame(np.linspace(100, 110, 30)))


def test_strong_uptrend_trails_and_lets_profit_run():
    close = np.linspace(100, 300, 260)          # persistent, accelerating uptrend
    rec = recommend_risk(_frame(close))
    assert rec.regime == "STRONG_UPTREND"
    assert rec.trail is True
    assert rec.take_profit_pct is None          # let it run behind the trailing stop
    assert rec.stop_price < rec.as_of_price


def test_downtrend_tightens_stop():
    up = np.linspace(100, 200, 130)
    down = np.linspace(200, 140, 130)
    rec = recommend_risk(_frame(np.concatenate([up, down])))
    assert rec.regime == "DOWNTREND"
    assert rec.trail is False
    assert rec.atr_stop_mult == pytest.approx(1.5)   # tight — counter-trend is risky


def test_stop_scales_with_volatility():
    base = np.linspace(100, 130, 260)
    calm = recommend_risk(_frame(base, spread=0.5))
    wild = recommend_risk(_frame(base, spread=5.0))
    # same price path, higher ATR -> wider absolute stop distance
    assert (wild.as_of_price - wild.stop_price) > (calm.as_of_price - calm.stop_price)


def test_entry_price_override_and_reward_risk():
    close = np.linspace(100, 160, 260)
    rec = recommend_risk(_frame(close), entry_price=150.0)
    assert rec.as_of_price == pytest.approx(150.0, abs=0.01)
    if rec.take_profit_pct is not None:
        assert rec.reward_risk is not None and rec.reward_risk > 0
