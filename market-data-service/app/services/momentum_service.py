"""The Momentum Engine: cross-sectional relative strength, computed honestly.

Core object: the RS rank — each stock's weighted trailing return (20% 1-month,
40% 3-month, 40% 6-month) ranked against the universe, as a 0-100 percentile.

Two forms, one definition:
  - `rs_rank_panel` — point-in-time series for BACKTESTS. The rank at bar T uses
    only closes up to T, so an `rs_rank gt 80` rule has zero lookahead. This is
    the part most platforms can't offer.
  - `momentum_board` — today's ranks from the screener snapshot for the LIVE
    sector-rotation board, leaders list and Alpha Stack layer.

Known failure mode (and why it's survivable here): momentum crashes when
regimes flip. The regime engine already down-weights entries in CHOP /
BEAR_RALLY — exactly when momentum dies.
"""
import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# lookbacks in BARS (≈ 1m / 3m / 6m on dailies) and their weights
RS_WINDOWS = ((21, 0.2), (63, 0.4), (126, 0.4))
MIN_BARS_FOR_RANK = 63          # below this a stock gets no rank (NaN), not a fake one

LEADER_MIN_RS = 80.0
LEADER_MAX_OFF_HIGH = -7.0      # within 7% of the 52-week high
LEADER_MIN_VOLUME_RATIO = 1.2


def weighted_momentum(close: pd.Series) -> pd.Series:
    """Weighted trailing return per bar (NaN until MIN_BARS_FOR_RANK)."""
    out = None
    for window, weight in RS_WINDOWS:
        ret = close.pct_change(window) * weight
        out = ret if out is None else out.add(ret, fill_value=None)
    # require at least the 3-month leg to exist
    out[close.rolling(MIN_BARS_FOR_RANK).count() < MIN_BARS_FOR_RANK] = float("nan")
    return out


def rs_rank_panel(closes: pd.DataFrame) -> pd.DataFrame:
    """closes: DataFrame indexed by date, one column per ticker.
    Returns the same shape holding 0-100 RS percentiles, point-in-time.
    Rank at row T uses only data up to T (trailing returns), so it is safe to
    feed into backtest rules."""
    momentum = pd.DataFrame({t: weighted_momentum(closes[t].astype(float))
                             for t in closes.columns}, index=closes.index)
    return momentum.rank(axis=1, pct=True) * 100.0


def momentum_board(session: Session) -> dict:
    """Live board from the screener snapshot: RS rank per stock, sector rotation
    heat, and the leaders (top-decile RS + near 52w high + volume interest)."""
    rows = session.execute(text("""
        SELECT s.id AS symbol_id, s.ticker, s.name, s.sector,
               snap.close, snap.return_1m_pct, snap.return_3m_pct, snap.return_1y_pct,
               snap.pct_from_52w_high, snap.volume_ratio, snap.as_of_date
        FROM screener_snapshot snap
        JOIN symbols s ON s.id = snap.symbol_id
        WHERE s.active AND snap.close IS NOT NULL
    """)).mappings().all()
    if len(rows) < 3:
        return {"status": "NO_DATA",
                "note": "Need at least a few synced stocks — run a sync + snapshot refresh"}

    frame = pd.DataFrame([dict(r) for r in rows])
    for col in ("return_1m_pct", "return_3m_pct", "return_1y_pct",
                "pct_from_52w_high", "volume_ratio"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    # snapshot proxy of the same weighted definition (1y stands in for 6m)
    frame["momentum"] = (0.2 * frame["return_1m_pct"].fillna(0)
                         + 0.4 * frame["return_3m_pct"].fillna(0)
                         + 0.4 * frame["return_1y_pct"].fillna(0))
    frame["rs_rank"] = frame["momentum"].rank(pct=True) * 100.0

    stocks = frame.sort_values("rs_rank", ascending=False)
    leaders = stocks[(stocks["rs_rank"] >= LEADER_MIN_RS)
                     & (stocks["pct_from_52w_high"] >= LEADER_MAX_OFF_HIGH)
                     & (stocks["volume_ratio"].fillna(0) >= LEADER_MIN_VOLUME_RATIO)]

    sectors = (frame.dropna(subset=["sector"])
               .groupby("sector")
               .agg(avg_rs=("rs_rank", "mean"), avg_1m=("return_1m_pct", "mean"),
                    stocks=("ticker", "count"))
               .sort_values("avg_rs", ascending=False).reset_index())

    def stock_row(r) -> dict:
        return {"ticker": r.ticker, "name": r.name, "sector": r.sector,
                "close": float(r.close),
                "rs_rank": round(float(r.rs_rank), 1),
                "return_1m_pct": (round(float(r.return_1m_pct), 1)
                                  if pd.notna(r.return_1m_pct) else None),
                "return_3m_pct": (round(float(r.return_3m_pct), 1)
                                  if pd.notna(r.return_3m_pct) else None),
                "pct_from_52w_high": (round(float(r.pct_from_52w_high), 1)
                                      if pd.notna(r.pct_from_52w_high) else None),
                "volume_ratio": (round(float(r.volume_ratio), 2)
                                 if pd.notna(r.volume_ratio) else None)}

    return {
        "status": "OK",
        "as_of": str(rows[0]["as_of_date"]),
        "universe": len(frame),
        "sectors": [{"sector": s.sector, "avg_rs": round(float(s.avg_rs), 1),
                     "avg_1m_pct": (round(float(s.avg_1m), 1)
                                    if pd.notna(s.avg_1m) else None),
                     "stocks": int(s.stocks)}
                    for s in sectors.itertuples()],
        "leaders": [stock_row(r) for r in leaders.itertuples()],
        "top": [stock_row(r) for r in stocks.head(15).itertuples()],
        "laggards": [stock_row(r) for r in stocks.tail(5).itertuples()],
    }


def rs_rank_for_symbol(session: Session, symbol_id: int) -> float | None:
    """This one stock's current RS percentile (used by the Alpha Stack layer)."""
    rows = session.execute(text("""
        SELECT snap.symbol_id, snap.return_1m_pct, snap.return_3m_pct, snap.return_1y_pct
        FROM screener_snapshot snap JOIN symbols s ON s.id = snap.symbol_id
        WHERE s.active AND snap.close IS NOT NULL
    """)).mappings().all()
    if len(rows) < 3:
        return None
    frame = pd.DataFrame([dict(r) for r in rows])
    for col in ("return_1m_pct", "return_3m_pct", "return_1y_pct"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["momentum"] = (0.2 * frame["return_1m_pct"].fillna(0)
                         + 0.4 * frame["return_3m_pct"].fillna(0)
                         + 0.4 * frame["return_1y_pct"].fillna(0))
    frame["rs_rank"] = frame["momentum"].rank(pct=True) * 100.0
    match = frame[frame["symbol_id"] == symbol_id]
    return round(float(match["rs_rank"].iloc[0]), 1) if len(match) else None
