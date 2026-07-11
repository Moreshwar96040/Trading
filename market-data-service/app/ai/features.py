"""Feature engineering for next-day return prediction. Pure pandas, no sklearn.

Every feature at row T uses only data up to and including T; the target is the
NEXT day's return (shift(-1)) — the standard no-leakage setup.
"""
import pandas as pd

from app.indicators import core

FEATURE_COLUMNS = ["ret_1d", "ret_2d", "ret_5d", "ret_10d", "rsi_14", "macd_hist_norm",
                   "volume_ratio", "sma20_ratio", "sma50_ratio", "dist_52w_high_pct"]
TARGET_COLUMN = "target_next_return_pct"


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV frame (ascending) → features + target. Rows with NaN are dropped.

    The LAST row has a NaN target (tomorrow is unknown) — it is kept separately by
    callers for live prediction via `latest_feature_row`.
    """
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    out = pd.DataFrame(index=df.index)
    out["ret_1d"] = close.pct_change() * 100
    out["ret_2d"] = close.pct_change(2) * 100
    out["ret_5d"] = close.pct_change(5) * 100
    out["ret_10d"] = close.pct_change(10) * 100
    out["rsi_14"] = core.rsi(close, 14)
    macd = core.macd(close)
    out["macd_hist_norm"] = macd["hist"] / close * 100
    out["volume_ratio"] = volume / volume.rolling(20).mean()
    out["sma20_ratio"] = close / core.sma(close, 20)
    out["sma50_ratio"] = close / core.sma(close, 50)
    rolling_high = close.rolling(252, min_periods=60).max()
    out["dist_52w_high_pct"] = (close / rolling_high - 1) * 100
    out[TARGET_COLUMN] = close.pct_change().shift(-1) * 100

    return out


def training_frame(features: pd.DataFrame) -> pd.DataFrame:
    """Rows usable for training (all features + target present)."""
    return features.dropna()


def latest_feature_row(features: pd.DataFrame) -> pd.Series | None:
    """The most recent row with complete features (target may be NaN) — the row
    we predict tomorrow from."""
    usable = features[FEATURE_COLUMNS].dropna()
    return usable.iloc[-1] if len(usable) else None
