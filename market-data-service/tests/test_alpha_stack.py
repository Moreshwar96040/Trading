from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from app.ai.quality_score import quality_score
from app.backtest.rules import (FUNDAMENTAL_FIELDS, combined_signal,
                                fundamental_fields_used, is_valid_series,
                                validate_rules)
from app.models import (AiInsight, AiPrediction, Fundamentals, ScreenerSnapshot,
                        Strategy, StrategySignal, Symbol)
from app.services.conviction_service import alpha_stack


# ---------- quality score ----------

def test_quality_score_strong_company():
    q = quality_score({"roe_pct": 30, "profit_margin_pct": 22, "earnings_growth_pct": 25,
                       "revenue_growth_pct": 18, "debt_to_equity": 0.1, "pe_trailing": 14})
    assert q["score"] >= 85
    assert q["grade"] == "A"


def test_quality_score_junk_company():
    q = quality_score({"roe_pct": -5, "profit_margin_pct": -10, "earnings_growth_pct": -30,
                       "revenue_growth_pct": -15, "debt_to_equity": 3.5, "pe_trailing": -2})
    assert q["score"] <= 15
    assert q["grade"] == "D"


def test_quality_score_missing_data_is_neutral():
    q = quality_score({})
    assert 40 <= q["score"] <= 60          # half credit everywhere


# ---------- fundamentals in the rules engine ----------

def test_fundamental_series_valid_and_detected():
    assert is_valid_series("roe_pct")
    assert validate_rules([{"left": "roe_pct", "op": "gt", "right": 15}]) == []
    used = fundamental_fields_used([{"left": "close", "op": "gt", "right": "sma_50"},
                                    {"left": "roe_pct", "op": "gt", "right": 15}])
    assert used == {"roe_pct"}
    assert FUNDAMENTAL_FIELDS >= used


def test_fundamental_rule_evaluates_as_constant_column():
    idx = [date(2026, 1, i) for i in range(1, 11)]
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                       "volume": 1000, "roe_pct": 18.0}, index=idx)
    sig = combined_signal(df, [{"left": "roe_pct", "op": "gt", "right": 15}])
    assert sig.all()
    sig2 = combined_signal(df, [{"left": "roe_pct", "op": "gt", "right": 25}])
    assert not sig2.any()


# ---------- conviction / alpha stack ----------

def _seed_signal(session: Session, ticker: str = "TCS") -> Symbol:
    sym = Symbol(ticker=ticker, yahoo_symbol=f"{ticker}.NS", name=f"{ticker} Ltd", sector="IT")
    strategy = Strategy(name=f"GC-{ticker}", definition={"entry": [], "exit": []})
    session.add_all([sym, strategy])
    session.flush()
    session.add(StrategySignal(strategy_id=strategy.id, symbol_id=sym.id, signal="ENTRY",
                               as_of_date=date(2026, 7, 10), close=3000))
    session.add(ScreenerSnapshot(symbol_id=sym.id, as_of_date=date(2026, 7, 10),
                                 close=3000, sma_50=2800, sma_200=2600, rsi_14=60,
                                 atr_14=50, return_1m_pct=4.0))
    session.commit()
    return sym


def test_alpha_stack_no_signals(session: Session):
    assert alpha_stack(session)["status"] == "NO_SIGNALS"


def test_alpha_stack_ranks_quality_above_junk(session: Session):
    good = _seed_signal(session, "GOOD")
    junk = _seed_signal(session, "JUNK")
    session.add(Fundamentals(symbol_id=good.id, roe_pct=30, profit_margin_pct=20,
                             earnings_growth_pct=20, revenue_growth_pct=15,
                             debt_to_equity=0.2, pe_trailing=18))
    session.add(Fundamentals(symbol_id=junk.id, roe_pct=-5, profit_margin_pct=-8,
                             earnings_growth_pct=-20, revenue_growth_pct=-10,
                             debt_to_equity=3.0, pe_trailing=-1))
    session.commit()
    stack = alpha_stack(session)
    order = [s["ticker"] for s in stack["setups"]]
    assert order.index("GOOD") < order.index("JUNK")
    good_setup = next(s for s in stack["setups"] if s["ticker"] == "GOOD")
    junk_setup = next(s for s in stack["setups"] if s["ticker"] == "JUNK")
    assert good_setup["conviction"] > junk_setup["conviction"]


def test_negative_news_vetoes_sizing(session: Session):
    sym = _seed_signal(session)
    session.add(AiInsight(symbol_id=sym.id, kind="NEWS",
                          content={"sentiment": "negative"}, fingerprint="x"))
    session.commit()
    setup = alpha_stack(session)["setups"][0]
    assert setup["news_veto"] is True
    assert setup["risk_multiplier"] == 0.0
    assert setup["verdict"] == "VETOED"


def test_ml_down_vote_lowers_conviction(session: Session):
    sym = _seed_signal(session)
    baseline = alpha_stack(session)["setups"][0]["conviction"]
    session.add(AiPrediction(symbol_id=sym.id, as_of_date=date(2026, 7, 10),
                             predicted_return_pct=-1.2, direction="DOWN",
                             test_direction_accuracy=60))
    session.commit()
    with_vote = alpha_stack(session)["setups"][0]["conviction"]
    assert with_vote < baseline


def test_ticker_filter(session: Session):
    _seed_signal(session, "AAA")
    _seed_signal(session, "BBB")
    stack = alpha_stack(session, ticker="aaa")
    assert [s["ticker"] for s in stack["setups"]] == ["AAA"]
