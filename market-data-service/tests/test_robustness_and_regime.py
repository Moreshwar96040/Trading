from datetime import date

from sqlalchemy.orm import Session

from app.backtest.robustness import HoldoutComparison, monte_carlo, robustness_score
from app.models import ScreenerSnapshot, Symbol
from app.services.regime_service import compute_regime


# ---------- Monte Carlo ----------

def test_monte_carlo_empty_returns_none():
    assert monte_carlo([]) is None


def test_monte_carlo_all_winners_never_loses():
    mc = monte_carlo([2.0] * 40, n_resamples=200)
    assert mc["prob_loss_pct"] == 0.0
    assert mc["return_p5"] > 0
    assert mc["return_p95"] >= mc["return_p50"] >= mc["return_p5"]


def test_monte_carlo_deterministic_with_seed():
    trades = [3.0, -1.0, 2.0, -2.5, 4.0, 1.0, -0.5, 2.2]
    assert monte_carlo(trades, seed=7) == monte_carlo(trades, seed=7)


def test_monte_carlo_histogram_covers_all_resamples():
    mc = monte_carlo([1.5, -1.0, 2.0, -0.5], n_resamples=300)
    assert sum(mc["histogram"]["counts"]) == 300


# ---------- holdout consistency ----------

def test_consistency_full_when_oos_matches():
    h = HoldoutComparison(10.0, 12.0, 20, 8)
    assert h.consistency() == 1.0


def test_consistency_partial_when_oos_fades():
    h = HoldoutComparison(10.0, 4.0, 20, 8)
    assert abs(h.consistency() - 0.4) < 1e-9


def test_consistency_zero_when_oos_negative_after_positive_is():
    h = HoldoutComparison(10.0, -5.0, 20, 8)
    assert h.consistency() == 0.0


# ---------- score & verdict ----------

def test_score_overfit_when_edge_collapses_oos():
    mc = monte_carlo([5.0, -1.0] * 20)          # strong in-sample stats
    h = HoldoutComparison(40.0, -8.0, 30, 10)   # collapses out of sample
    rep = robustness_score(40, mc, h)
    assert rep["components"]["holdout"] == 0
    assert rep["verdict"] in ("FRAGILE", "PROMISING")   # holdout drags it down


def test_score_robust_for_consistent_strategy():
    mc = monte_carlo([2.0, -0.8] * 25)
    h = HoldoutComparison(20.0, 18.0, 35, 15)
    rep = robustness_score(50, mc, h)
    assert rep["score"] >= 75
    assert rep["verdict"] == "ROBUST"


def test_score_penalizes_tiny_samples():
    rep = robustness_score(4, monte_carlo([3.0, 2.0, -1.0, 4.0]), None)
    assert rep["components"]["sample_size"] < 10
    assert any("too few" in r.lower() or "far too few" in r.lower() for r in rep["reasons"])


# ---------- regime ----------

def _snap(session: Session, ticker: str, close: float, sma50: float, sma200: float,
          rsi: float = 55.0) -> None:
    sym = Symbol(ticker=ticker, yahoo_symbol=f"{ticker}.NS", name=ticker, sector="X")
    session.add(sym)
    session.flush()
    session.add(ScreenerSnapshot(symbol_id=sym.id, as_of_date=date(2026, 7, 10),
                                 close=close, sma_50=sma50, sma_200=sma200,
                                 rsi_14=rsi, atr_14=close * 0.02, return_1m_pct=1.0))


def test_regime_no_data(session: Session):
    assert compute_regime(session)["status"] == "NO_DATA"


def test_regime_risk_on_when_breadth_broad(session: Session):
    for i in range(8):
        _snap(session, f"UP{i}", close=110, sma50=100, sma200=90)
    for i in range(2):
        _snap(session, f"DN{i}", close=80, sma50=100, sma200=90)
    session.commit()
    r = compute_regime(session)
    assert r["status"] == "OK"
    assert r["regime"] == "RISK_ON"
    assert r["breadth"]["pct_above_sma200"] == 100.0 or r["breadth"]["pct_above_sma200"] >= 65


def test_regime_risk_off_when_breadth_broken(session: Session):
    for i in range(9):
        _snap(session, f"DN{i}", close=80, sma50=95, sma200=100)
    _snap(session, "UP0", close=120, sma50=100, sma200=95)
    session.commit()
    r = compute_regime(session)
    assert r["regime"] == "RISK_OFF"
    assert "below" in r["guidance"] or "downtrend" in r["label"].lower()
