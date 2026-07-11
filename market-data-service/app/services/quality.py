"""Data-quality gate. Every row entering ohlcv_daily passes through here.

Rules (mirrors the DB CHECK constraints so bad rows are rejected with a reason
instead of blowing up the batch): prices > 0, high >= low, volume >= 0, valid date,
no nulls in required fields.
"""
import logging

import pandas as pd

from app.providers.base import OHLCV_COLUMNS

log = logging.getLogger(__name__)

_REQUIRED = ["trade_date", "open", "high", "low", "close", "volume"]


def validate_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Return (clean_rows, rejected_count). Logs a reason per rejected row."""
    if df.empty:
        return df.reindex(columns=OHLCV_COLUMNS), 0

    df = df.reindex(columns=OHLCV_COLUMNS)
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
    for col in ["open", "high", "low", "close", "adj_close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    problems = pd.Series("", index=df.index)
    problems[df[_REQUIRED].isna().any(axis=1)] += "missing required field;"
    for col in ["open", "high", "low", "close"]:
        problems[df[col].le(0).fillna(False)] += f"{col} <= 0;"
    problems[(df["high"] < df["low"]).fillna(False)] += "high < low;"
    problems[df["volume"].lt(0).fillna(False)] += "volume < 0;"

    bad = problems != ""
    for idx in df.index[bad]:
        log.warning("Rejected row (%s): %s", problems[idx], df.loc[idx].to_dict())

    clean = df[~bad].copy()
    clean["volume"] = clean["volume"].astype("int64")
    return clean, int(bad.sum())
