"""Indicator series for charting: reads OHLCV from DB, computes on demand."""
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators import core
from app.models import OhlcvDaily, Symbol

#: Extra history fetched before `from` so indicators are warm at the window start.
WARMUP_ROWS = 210


def load_ohlcv(session: Session, symbol_id: int, until: date | None = None) -> pd.DataFrame:
    stmt = (select(OhlcvDaily.trade_date, OhlcvDaily.open, OhlcvDaily.high,
                   OhlcvDaily.low, OhlcvDaily.close, OhlcvDaily.volume)
            .where(OhlcvDaily.symbol_id == symbol_id)
            .order_by(OhlcvDaily.trade_date))
    if until:
        stmt = stmt.where(OhlcvDaily.trade_date <= until)
    rows = session.execute(stmt).all()
    df = pd.DataFrame(rows, columns=["trade_date", "open", "high", "low", "close", "volume"])
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    return df


def indicator_series(session: Session, symbol: Symbol,
                     from_date: date | None, to_date: date | None) -> dict:
    """Series shaped for chart overlays: {dates: [...], sma_20: [...], ...}."""
    df = load_ohlcv(session, symbol.id, until=to_date)
    if df.empty:
        return {"ticker": symbol.ticker, "dates": [], "series": {}}

    close = df["close"]
    out = pd.DataFrame({
        "sma_20": core.sma(close, 20),
        "sma_50": core.sma(close, 50),
        "sma_200": core.sma(close, 200),
        "ema_20": core.ema(close, 20),
        "rsi_14": core.rsi(close, 14),
    })
    m = core.macd(close)
    out["macd"], out["macd_signal"], out["macd_hist"] = m["macd"], m["signal"], m["hist"]
    bb = core.bollinger(close)
    out["bb_upper"], out["bb_lower"] = bb["upper"], bb["lower"]
    out["atr_14"] = core.atr(df["high"], df["low"], close, 14)
    ich = core.ichimoku(df["high"], df["low"], close)
    out["ichimoku_tenkan"], out["ichimoku_kijun"] = ich["tenkan"], ich["kijun"]
    out["ichimoku_senkou_a"], out["ichimoku_senkou_b"] = ich["senkou_a"], ich["senkou_b"]
    sr = core.support_resistance(df["high"], df["low"])
    out["support"], out["resistance"] = sr["support"], sr["resistance"]
    out.insert(0, "trade_date", df["trade_date"])

    if from_date:
        out = out[out["trade_date"] >= from_date]

    dates = [d.isoformat() for d in out["trade_date"]]
    series = {col: [None if pd.isna(v) else round(float(v), 6) for v in out[col]]
              for col in out.columns if col != "trade_date"}
    return {"ticker": symbol.ticker, "dates": dates, "series": series}
