"""Portfolio construction.

The constructor is pure, so every constraint can be driven to its edge without a
database. That is the point of separating it from `build_from_setups`.
"""
from app.services.portfolio_constructor import Candidate, construct

EQUITY = 1_000_000.0


def _c(ticker, conviction=70.0, sector="IT", close=100.0, stop=95.0, **kw):
    return Candidate(symbol_id=abs(hash(ticker)) % 10_000, ticker=ticker,
                     conviction=conviction, close=close, sector=sector,
                     stop=stop, **kw)


def _tickers(portfolio):
    return [a.ticker for a in portfolio.allocations]


def _reason(portfolio, ticker):
    return next(r["reason"] for r in portfolio.rejected if r["ticker"] == ticker)


# ---------- the core failure the module exists to prevent ----------

def test_one_sector_cannot_take_the_whole_book():
    """Eight banks is one position with eight commission bills."""
    banks = [_c(f"BANK{i}", conviction=90 - i, sector="Financials")
             for i in range(8)]
    p = construct(banks, EQUITY)
    financial_risk = p.sector_risk["Financials"]
    assert financial_risk <= p.risk_budget * 0.35 + 1e-6
    assert len(p.allocations) < 8
    assert "cap" in _reason(p, "BANK7")


def test_a_diversified_list_fills_more_slots_than_a_concentrated_one():
    concentrated = construct([_c(f"B{i}", sector="Financials") for i in range(8)],
                             EQUITY)
    diversified = construct([_c(f"D{i}", sector=f"Sector{i}") for i in range(8)],
                            EQUITY)
    assert len(diversified.allocations) > len(concentrated.allocations)


# ---------- correlation ----------

def test_a_highly_correlated_name_is_rejected_outright():
    p = construct([_c("A", conviction=90, sector="IT"),
                   _c("B", conviction=85, sector="Energy")],
                  EQUITY, correlations={("A", "B"): 0.92})
    assert _tickers(p) == ["A"]
    assert "correlated" in _reason(p, "B")


def test_correlation_keys_work_in_either_order():
    p = construct([_c("A", conviction=90), _c("B", conviction=85, sector="Energy")],
                  EQUITY, correlations={("B", "A"): 0.92})
    assert _tickers(p) == ["A"]


def test_negative_correlation_counts_too():
    """A -0.9 pair is the same bet held backwards, not diversification."""
    p = construct([_c("A", conviction=90), _c("B", conviction=85, sector="Energy")],
                  EQUITY, correlations={("A", "B"): -0.92})
    assert _tickers(p) == ["A"]


def test_existing_holdings_participate_in_the_correlation_check():
    p = construct([_c("NEW")], EQUITY, existing_tickers=["OLD"],
                  correlations={("NEW", "OLD"): 0.9})
    assert not p.allocations and "OLD" in _reason(p, "NEW")


# ---------- risk budget ----------

def test_total_risk_never_exceeds_the_budget():
    names = [_c(f"N{i}", sector=f"S{i}", conviction=80, risk_multiplier=1.5)
             for i in range(8)]
    p = construct(names, EQUITY, risk_budget_pct=3.0)
    assert p.risk_deployed <= p.risk_budget + 1e-6


def test_no_single_name_can_dominate():
    p = construct([_c("HERO", conviction=99, risk_multiplier=5.0)], EQUITY)
    assert p.allocations[0].risk_share <= 0.20 + 1e-6


def test_a_wider_stop_gets_fewer_shares_for_the_same_risk():
    """Risk, not share count, is what is being budgeted."""
    tight = construct([_c("T", stop=99.0)], EQUITY).allocations[0]
    wide = construct([_c("W", stop=90.0)], EQUITY).allocations[0]
    assert tight.quantity > wide.quantity
    assert abs(tight.risk_amount - wide.risk_amount) < tight.risk_amount * 0.05


def test_existing_sector_risk_is_counted():
    """Otherwise you build a concentrated book one diversified day at a time."""
    prior = {"IT": 1_000_000.0 * 6.0 / 100.0 * 0.35}      # IT already at its cap
    p = construct([_c("INFY", sector="IT")], EQUITY, existing_sectors=prior)
    assert not p.allocations and "cap" in _reason(p, "INFY")


# ---------- eligibility ----------

def test_a_name_without_a_stop_is_refused_not_guessed():
    p = construct([_c("NOSTOP", stop=None)], EQUITY)
    assert not p.allocations and "risk cannot be measured" in _reason(p, "NOSTOP")


def test_a_stop_above_the_entry_is_treated_as_no_stop():
    p = construct([_c("BAD", close=100.0, stop=105.0)], EQUITY)
    assert not p.allocations


def test_the_veto_and_the_conviction_bar_are_absolute():
    p = construct([_c("VETO", conviction=95, news_veto=True),
                   _c("WEAK", conviction=40, sector="Energy")], EQUITY)
    assert not p.allocations
    assert _reason(p, "VETO") == "news veto"
    assert "below the" in _reason(p, "WEAK")


def test_zero_risk_multiplier_is_honoured():
    p = construct([_c("ZERO", risk_multiplier=0.0)], EQUITY)
    assert not p.allocations


# ---------- ordering and reporting ----------

def test_highest_conviction_is_served_first():
    p = construct([_c("LOW", conviction=60, sector="A"),
                   _c("HIGH", conviction=90, sector="B")], EQUITY)
    assert _tickers(p)[0] == "HIGH"


def test_position_count_is_still_capped():
    names = [_c(f"N{i}", sector=f"S{i}") for i in range(20)]
    p = construct(names, EQUITY, max_positions=5)
    assert len(p.allocations) == 5
    assert "position limit" in _reason(p, "N19")


def test_every_rejection_carries_a_reason():
    names = [_c(f"N{i}", sector="IT", conviction=90 - i) for i in range(12)]
    p = construct(names, EQUITY)
    assert p.rejected
    assert all(r["reason"] for r in p.rejected)


def test_no_budget_means_no_positions():
    p = construct([_c("A")], EQUITY, risk_budget_pct=0.0)
    assert not p.allocations and "No risk budget" in p.note


def test_the_summary_reports_budget_usage():
    out = construct([_c("A"), _c("B", sector="Energy")], EQUITY).to_dict()
    assert out["positions"] == 2
    assert 0 < out["risk_used_pct"] <= 100
