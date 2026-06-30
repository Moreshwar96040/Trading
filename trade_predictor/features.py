"""
Feature engineering for the NSE trade-price predictor.
All features use only past/current information; the target is shifted forward,
so there is no look-ahead leakage. Indicators are computed per-ticker.
"""
import numpy as np
import pandas as pd


def _rsi(close, n=14):
    delta = close.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    down = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / (down + 1e-9)
    return 100 - 100 / (1 + rs)


def _atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def add_features(df):
    """Add technical features to a single ticker's frame (sorted by Date)."""
    df = df.sort_values("Date").reset_index(drop=True).copy()
    price = df["AdjClose"].where(df["AdjClose"] > 0, df["Close"])
    df["price"] = price
    df["logret"] = np.log(price / price.shift(1))

    # lagged returns
    for k in (1, 2, 3, 5, 10):
        df[f"ret_lag{k}"] = df["logret"].shift(k)

    # momentum
    for k in (5, 10, 20):
        df[f"mom{k}"] = price / price.shift(k) - 1.0

    # moving-average ratios + slope
    for k in (5, 10, 20, 50):
        ma = price.rolling(k).mean()
        df[f"ma_ratio{k}"] = price / ma - 1.0
        df[f"ma_slope{k}"] = ma.diff() / (ma.shift(1) + 1e-9)

    # volatility
    for k in (5, 10, 20):
        df[f"vol{k}"] = df["logret"].rolling(k).std()

    # RSI, ATR
    df["rsi14"] = _rsi(price, 14)
    df["atr14"] = _atr(df, 14) / (price + 1e-9)

    # MACD
    ema12 = price.ewm(span=12, adjust=False).mean()
    ema26 = price.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    df["macd"] = macd / (price + 1e-9)
    df["macd_hist"] = (macd - sig) / (price + 1e-9)

    # Bollinger position
    ma20 = price.rolling(20).mean()
    sd20 = price.rolling(20).std()
    df["bb_pos"] = (price - ma20) / (2 * sd20 + 1e-9)

    # volume
    vma = df["Volume"].rolling(20).mean()
    df["vol_ratio"] = df["Volume"] / (vma + 1e-9)
    df["vol_chg"] = df["Volume"].pct_change(fill_method=None).clip(-5, 5)

    # calendar
    dts = pd.to_datetime(df["Date"])
    df["dow"] = dts.dt.dayofweek
    df["month"] = dts.dt.month

    # ---- targets (shifted forward -> predict the FUTURE) ----
    df["target_ret"] = df["logret"].shift(-1)            # next-day log return
    df["target_dir"] = (df["target_ret"] > 0).astype(int)  # up/down
    return df


FEATURE_COLS = [
    "ret_lag1", "ret_lag2", "ret_lag3", "ret_lag5", "ret_lag10",
    "mom5", "mom10", "mom20",
    "ma_ratio5", "ma_ratio10", "ma_ratio20", "ma_ratio50",
    "ma_slope5", "ma_slope10", "ma_slope20", "ma_slope50",
    "vol5", "vol10", "vol20",
    "rsi14", "atr14", "macd", "macd_hist", "bb_pos",
    "vol_ratio", "vol_chg", "dow", "month",
]


def build_panel(combined_csv):
    """Build the stacked feature panel for all tickers."""
    raw = pd.read_csv(combined_csv, parse_dates=["Date"])
    frames = []
    for tic, g in raw.groupby("Ticker"):
        f = add_features(g)
        f["Ticker"] = tic
        frames.append(f)
    panel = pd.concat(frames, ignore_index=True)
    # ticker as integer code (categorical feature)
    panel["ticker_id"] = panel["Ticker"].astype("category").cat.codes
    return panel
