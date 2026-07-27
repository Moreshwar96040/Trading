"""Portfolio Alpha Monitor: does a held stock get the right ADD/HOLD/TRIM/SELL call?

The decision logic is pure, so most of this tests `_decide` directly across the
conviction/veto/trend matrix; two end-to-end tests confirm the wiring against
live holdings and the paper book.
"""
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import AiInsight, ScreenerSnapshot, Strategy, StrategySignal, Symbol
from app.services.portfolio_monitor import _decide, portfolio_alpha_review


class _Settings:
    anthropic_api_key = ""            # no LLM in tests — warm-up degrades to no-op


def _setup(session: Session, ticker="TCS", close=3000.0, atr=45.0) -> Symbol:
    sym = Symbol(ticker=ticker, yahoo_symbol=f"{ticker}.NS", name=f"{ticker} Ltd", sector="IT")
    session.add(sym)
    session.commit()
    session.add(ScreenerSnapshot(symbol_id=sym.id, as_of_date=date(2026, 7, 10),
                                 close=close, sma_50=close * 0.95, sma_200=close * 0.9,
                                 rsi_14=58, atr_14=atr, return_1m_pct=3.0))
    session.commit()
    return sym


def _bd(**strengths) -> list[dict]:
    return [{"layer": k, "points": 0, "max": 10, "strength": v, "note": ""}
            for k, v in strengths.items()]


# ---------- decision matrix (pure) ----------

def test_veto_forces_sell():
    setup = {"conviction": 62, "news_veto": True, "verdict": "VETOED",
             "close": 100, "breakdown": _bd(news=0.0)}
    d = _decide(setup, {"direction": "stable"}, {"avg_cost": 80})
    assert d["action"] == "SELL"
    assert d["pnl_pct"] == 25.0            # 100 vs 80


def test_collapsed_conviction_sells():
    setup = {"conviction": 33, "news_veto": False, "verdict": "STAND_ASIDE",
             "close": 90, "breakdown": _bd(technical=0.3, quality=0.4)}
    assert _decide(setup, {"direction": "stable"}, {"avg_cost": 100})["action"] == "SELL"


def test_mediocre_or_deteriorating_trims():
    weak = {"conviction": 48, "news_veto": False, "verdict": "SMALL",
            "close": 100, "breakdown": _bd(quality=0.3)}
    assert _decide(weak, {"direction": "stable"}, {"avg_cost": 90})["action"] == "TRIM"
    # even a healthy score trims when the news trend is rolling over
    fading = {"conviction": 66, "news_veto": False, "verdict": "NORMAL",
              "close": 100, "breakdown": _bd(news=0.45)}
    assert _decide(fading, {"direction": "deteriorating"}, {"avg_cost": 90})["action"] == "TRIM"


def test_high_conviction_adds():
    setup = {"conviction": 82, "news_veto": False, "verdict": "HIGH",
             "close": 120, "breakdown": _bd(technical=0.95, quality=0.9, news=0.8)}
    d = _decide(setup, {"direction": "improving"}, {"avg_cost": 100})
    assert d["action"] == "ADD"
    assert "technical" in d["rationale"] or "quality" in d["rationale"]


def test_normal_band_holds():
    setup = {"conviction": 63, "news_veto": False, "verdict": "NORMAL",
             "close": 100, "breakdown": _bd(technical=0.7)}
    assert _decide(setup, {"direction": "stable"}, {"avg_cost": 95})["action"] == "HOLD"


def test_high_conviction_but_deteriorating_does_not_add():
    setup = {"conviction": 80, "news_veto": False, "verdict": "HIGH",
             "close": 100, "breakdown": _bd(technical=0.9)}
    # deteriorating news blocks ADD and routes to TRIM instead
    assert _decide(setup, {"direction": "deteriorating"}, {"avg_cost": 90})["action"] == "TRIM"


# ---------- end to end ----------

def test_review_scores_live_holding(session: Session):
    sym = _setup(session, "INFY", close=1500.0)
    # a fired signal + strong fundamentals + positive news -> high conviction -> ADD
    strat = Strategy(name="GC", definition={"entry": []})
    session.add(strat)
    session.flush()
    session.add(StrategySignal(strategy_id=strat.id, symbol_id=sym.id, signal="ENTRY",
                               as_of_date=date(2026, 7, 10), close=1500))
    session.add(AiInsight(symbol_id=sym.id, kind="NEWS",
                          content={"sentiment": "positive"}, fingerprint="x"))
    from app.models import Fundamentals
    session.add(Fundamentals(symbol_id=sym.id, roe_pct=28, profit_margin_pct=20,
                             earnings_growth_pct=22, revenue_growth_pct=16,
                             debt_to_equity=0.2, pe_trailing=22))
    session.commit()

    out = portfolio_alpha_review(session, _Settings(),
                                 live_positions=[{"ticker": "INFY", "quantity": 10,
                                                  "avg_cost": 1400, "last_price": 1500}])
    assert out["status"] == "OK"
    r = out["reviews"][0]
    assert r["ticker"] == "INFY" and r["source"] == "LIVE"
    assert r["action"] in {"ADD", "HOLD"}
    assert r["pnl_pct"] == round((1500 / 1400 - 1) * 100, 2)
    assert out["summary"]["holdings"] == 1


def test_untracked_holding_is_flagged_not_crashed(session: Session):
    out = portfolio_alpha_review(session, _Settings(),
                                 live_positions=[{"ticker": "NOTREAL", "quantity": 5,
                                                  "avg_cost": 10}])
    assert out["reviews"][0]["action"] == "UNKNOWN"


def test_no_holdings_is_clean(session: Session):
    assert portfolio_alpha_review(session, _Settings(), live_positions=[])["status"] \
        == "NO_POSITIONS"
