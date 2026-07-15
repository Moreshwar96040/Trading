from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.models import ScreenerSnapshot, Symbol
from app.services.momentum_service import (momentum_board, rs_rank_for_symbol,
                                           rs_rank_panel, weighted_momentum)


def _closes(days: int, daily_ret: float, start: float = 100.0) -> pd.Series:
    idx = [date(2025, 1, 1) + timedelta(days=i) for i in range(days)]
    return pd.Series([start * (1 + daily_ret) ** i for i in range(days)], index=idx)


# ---------- point-in-time panel ----------

def test_rs_rank_leader_beats_laggard():
    closes = pd.DataFrame({
        "UP": _closes(200, 0.004),      # steady climber
        "FLAT": _closes(200, 0.0),
        "DOWN": _closes(200, -0.003),
    })
    ranks = rs_rank_panel(closes)
    last = ranks.iloc[-1]
    assert last["UP"] > last["FLAT"] > last["DOWN"]
    assert last["UP"] == 100.0          # best of 3 = 100th percentile


def test_rs_rank_needs_history():
    closes = pd.DataFrame({"A": _closes(30, 0.01), "B": _closes(30, -0.01)})
    ranks = rs_rank_panel(closes)
    assert ranks.iloc[-1].isna().all()   # < 63 bars -> no rank, not a fake one


def test_rs_rank_is_point_in_time():
    """The rank at bar T must not change when future bars are appended."""
    up, down = _closes(200, 0.004), _closes(200, -0.003)
    ranks_full = rs_rank_panel(pd.DataFrame({"UP": up, "DOWN": down}))
    ranks_cut = rs_rank_panel(pd.DataFrame({"UP": up.iloc[:150], "DOWN": down.iloc[:150]}))
    t = up.index[149]
    assert ranks_full.loc[t, "UP"] == ranks_cut.loc[t, "UP"]


def test_weighted_momentum_prefers_recent_strength():
    steady = weighted_momentum(_closes(200, 0.002)).iloc[-1]
    fading = weighted_momentum(pd.concat([
        _closes(150, 0.004),
        _closes(50, -0.004, start=_closes(150, 0.004).iloc[-1]),
    ]).reset_index(drop=True).set_axis(
        [date(2025, 1, 1) + timedelta(days=i) for i in range(200)])).iloc[-1]
    assert steady > fading


# ---------- live board ----------

def _snap(session: Session, ticker: str, r1m: float, r3m: float, r1y: float,
          off_high: float = -2.0, vol: float = 1.5, sector: str = "IT") -> Symbol:
    sym = Symbol(ticker=ticker, yahoo_symbol=f"{ticker}.NS", name=f"{ticker} Ltd",
                 sector=sector)
    session.add(sym)
    session.flush()
    session.add(ScreenerSnapshot(symbol_id=sym.id, as_of_date=date(2026, 7, 10),
                                 close=100, return_1m_pct=r1m, return_3m_pct=r3m,
                                 return_1y_pct=r1y, pct_from_52w_high=off_high,
                                 volume_ratio=vol))
    session.commit()
    return sym


def test_board_ranks_and_finds_leaders(session: Session):
    _snap(session, "LEAD", 12, 30, 60, off_high=-1, vol=2.0, sector="Auto")
    _snap(session, "MID", 2, 5, 10)
    _snap(session, "LAG", -8, -15, -30, off_high=-40, vol=0.8, sector="FMCG")
    board = momentum_board(session)
    assert board["status"] == "OK"
    assert board["top"][0]["ticker"] == "LEAD"
    assert [s["ticker"] for s in board["leaders"]] == ["LEAD"]
    sectors = {s["sector"]: s["avg_rs"] for s in board["sectors"]}
    assert sectors["Auto"] > sectors["FMCG"]


def test_board_no_data(session: Session):
    assert momentum_board(session)["status"] == "NO_DATA"


def test_rs_rank_for_symbol(session: Session):
    lead = _snap(session, "LEAD", 12, 30, 60)
    _snap(session, "MID", 2, 5, 10)
    lag = _snap(session, "LAG", -8, -15, -30)
    assert rs_rank_for_symbol(session, lead.id) == 100.0
    assert rs_rank_for_symbol(session, lag.id) < 50.0


# ---------- rs_rank in the rules engine ----------

def test_rs_rank_rule_validates_and_resolves():
    from app.backtest.rules import combined_signal, is_valid_series, validate_rules
    assert is_valid_series("rs_rank")
    assert validate_rules([{"left": "rs_rank", "op": "gt", "right": 80}]) == []

    idx = [date(2026, 1, 1) + timedelta(days=i) for i in range(10)]
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                       "volume": 1000, "rs_rank": 90.0}, index=idx)
    assert combined_signal(df, [{"left": "rs_rank", "op": "gt", "right": 80}]).all()
