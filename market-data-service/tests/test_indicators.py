"""Indicator math verified against hand-computed / spreadsheet values."""
import numpy as np
import pandas as pd
import pytest

from app.indicators import core


@pytest.fixture
def close():
    return pd.Series([10.0, 11.0, 12.0, 11.0, 10.0, 9.0, 10.0, 11.0, 12.0, 13.0])


def test_sma_simple(close):
    result = core.sma(close, 3)
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(11.0)          # (10+11+12)/3
    assert result.iloc[-1] == pytest.approx(12.0)         # (11+12+13)/3


def test_ema_recursive_definition(close):
    result = core.ema(close, 3)                            # alpha = 0.5
    # EMA(adjust=False): e0=10; e1=0.5*11+0.5*10=10.5; e2=0.5*12+0.5*10.5=11.25
    assert result.iloc[2] == pytest.approx(11.25)


def test_rsi_all_gains_is_100():
    up = pd.Series(np.linspace(10, 30, 30))
    assert core.rsi(up, 14).iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_near_zero():
    down = pd.Series(np.linspace(30, 10, 30))
    assert core.rsi(down, 14).iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_rsi_bounded_and_warmup_nan(close):
    result = core.rsi(close, 5)
    assert result[:5].isna().all()
    valid = result[5:]
    assert ((valid >= 0) & (valid <= 100)).all()


def test_macd_is_fast_minus_slow(close):
    m = core.macd(close, fast=3, slow=6, signal=3)
    expected = core.ema(close, 3) - core.ema(close, 6)
    pd.testing.assert_series_equal(m["macd"], expected, check_names=False)
    pd.testing.assert_series_equal(m["hist"], m["macd"] - m["signal"], check_names=False)


def test_bollinger_symmetry(close):
    bb = core.bollinger(close, period=5, num_std=2.0)
    mid, up, lo = bb["mid"].iloc[-1], bb["upper"].iloc[-1], bb["lower"].iloc[-1]
    assert up - mid == pytest.approx(mid - lo)
    assert up >= mid >= lo


def test_atr_constant_range():
    n = 30
    high = pd.Series([12.0] * n)
    low = pd.Series([10.0] * n)
    close_ = pd.Series([11.0] * n)
    # TR is constantly 2.0 -> smoothed ATR converges to 2.0
    assert core.atr(high, low, close_, 14).iloc[-1] == pytest.approx(2.0, rel=1e-3)


@pytest.fixture
def ohlc():
    n = 120
    close = pd.Series(100 + np.sin(np.linspace(0, 12, n)) * 10 + np.linspace(0, 20, n))
    high = close + 1.0
    low = close - 1.0
    return high, low, close


def test_ichimoku_lines_are_midpoints(ohlc):
    high, low, close = ohlc
    ich = core.ichimoku(high, low, close, tenkan=9, kijun=26, senkou_b=52)
    # Tenkan at bar T = (max(high[T-8:T]) + min(low[T-8:T])) / 2
    t = 60
    expected = (high.iloc[t - 8:t + 1].max() + low.iloc[t - 8:t + 1].min()) / 2
    assert ich["tenkan"].iloc[t] == pytest.approx(expected)


def test_ichimoku_senkou_shifted_forward_no_lookahead(ohlc):
    high, low, close = ohlc
    ich = core.ichimoku(high, low, close, displacement=26)
    # senkou_a at T equals the (tenkan+kijun)/2 computed 26 bars earlier
    raw = (ich["tenkan"] + ich["kijun"]) / 2.0
    assert ich["senkou_a"].iloc[80] == pytest.approx(raw.iloc[80 - 26])


def test_ichimoku_warmup_is_nan(ohlc):
    high, low, close = ohlc
    ich = core.ichimoku(high, low, close)
    assert ich["senkou_b"].iloc[:52].isna().all()   # 52-period base, before warm-up


def test_swing_points_flag_local_extremes():
    high = pd.Series([1, 2, 5, 2, 1, 2, 3, 2, 1], dtype=float)
    low = pd.Series([1, 0, 1, 1, 0, 1, 1, 1, 0], dtype=float)
    sw = core.swing_points(high, low, left=2, right=2)
    assert sw["swing_high"].iloc[2] == 5.0        # the peak
    assert sw["swing_high"].notna().sum() >= 1


def test_support_resistance_is_lagged_and_stepped():
    high = pd.Series([1, 2, 5, 2, 1, 1, 1, 1, 1], dtype=float)
    low = pd.Series([1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=float)
    sr = core.support_resistance(high, low, left=2, right=2)
    # peak at index 2 (value 5) confirmed 2 bars later -> resistance known from index 4 on
    assert pd.isna(sr["resistance"].iloc[3])
    assert sr["resistance"].iloc[6] == 5.0


# ---------- Ichimoku screener fields (snapshot layer) ----------

def _series(values):
    close = pd.Series(values, dtype=float)
    return close * 1.01, close * 0.99, close


def _reversal(down_len=90, up_len=14):
    """Long decline then a sharp turn — Tenkan (blue) crosses Kijun (red) late."""
    import numpy as np
    return np.concatenate([np.linspace(200, 100, down_len),
                           np.linspace(100, 165, up_len)])


def test_fresh_tk_cross_reports_a_small_age():
    from app.services.snapshot_service import _ichimoku_fields
    f = _ichimoku_fields(*_series(_reversal(down_len=90, up_len=14)))
    assert f["tk_cross_age_days"] is not None
    assert f["tk_cross_age_days"] <= 10          # the cross is recent, not stale


def test_downtrend_has_no_bullish_cross_and_sits_below_cloud():
    import numpy as np
    from app.services.snapshot_service import _ichimoku_fields
    f = _ichimoku_fields(*_series(np.linspace(300, 100, 140)))
    assert f["tk_cross_age_days"] is None        # bearish: no live cross age
    assert f["ichimoku_bullish"] == 0
    assert f["pct_above_cloud"] < 0              # price under the cloud


def test_bullish_flag_needs_both_cross_and_cloud_breakout():
    from app.services.snapshot_service import _ichimoku_fields
    f = _ichimoku_fields(*_series(_reversal(down_len=90, up_len=50)))
    assert f["tenkan_9"] > f["kijun_26"]
    assert f["pct_above_cloud"] > 0
    assert f["ichimoku_bullish"] == 1


def test_cloud_edges_are_ordered():
    from app.services.snapshot_service import _ichimoku_fields
    f = _ichimoku_fields(*_series(_reversal()))
    assert f["cloud_top"] >= f["cloud_bottom"]


def test_snapshot_row_exposes_ichimoku_fields():
    """The screener DSL can only filter what the snapshot row carries."""
    from datetime import date
    import numpy as np
    from app.services.snapshot_service import compute_snapshot_row
    values = _reversal()
    df = pd.DataFrame({
        "trade_date": [date(2026, 1, 1)] * len(values),
        "open": values, "high": values * 1.01, "low": values * 0.99,
        "close": values, "volume": np.full(len(values), 1000),
    })
    row = compute_snapshot_row(df)
    for field in ("tenkan_9", "kijun_26", "cloud_top", "cloud_bottom",
                  "tk_cross_age_days", "pct_above_cloud", "ichimoku_bullish"):
        assert field in row, field


# ---------- major support screener fields ----------

def test_support_fields_flag_price_coiled_near_swing_low():
    import numpy as np
    from app.services.snapshot_service import _support_fields
    vals = np.concatenate([np.linspace(150, 100, 15),   # fall to a swing low ~100
                           np.linspace(100, 130, 10),   # bounce (confirms the low)
                           np.linspace(130, 104, 8)])    # pull back near it
    close = pd.Series(vals)
    f = _support_fields(close * 1.01, close * 0.99, close)
    assert f["support"] is not None
    assert 0 <= f["pct_from_support"] <= 8            # just above support


def test_support_none_in_pure_uptrend_with_no_recent_swing_low():
    import numpy as np
    from app.services.snapshot_service import _support_fields
    up = pd.Series(np.linspace(100, 200, 40))
    assert _support_fields(up * 1.01, up * 0.99, up)["support"] is None


def test_snapshot_row_exposes_support_fields():
    from datetime import date
    import numpy as np
    from app.services.snapshot_service import compute_snapshot_row
    vals = np.concatenate([np.linspace(150, 100, 15), np.linspace(100, 130, 10),
                           np.linspace(130, 104, 8)])
    df = pd.DataFrame({"trade_date": [date(2026, 1, 1)] * len(vals),
                       "open": vals, "high": vals * 1.01, "low": vals * 0.99,
                       "close": vals, "volume": np.full(len(vals), 1000)})
    row = compute_snapshot_row(df)
    assert "support" in row and "pct_from_support" in row
