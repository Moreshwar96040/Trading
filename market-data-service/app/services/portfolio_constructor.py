"""Portfolio construction — turning a ranked list into a book you can survive.

`select_candidates` in the autopilot takes the top N by conviction. That is a
ranking, not a portfolio, and the difference shows up exactly when it hurts: the
Alpha Stack's layers are largely macro-driven, so on any given day the top eight
names are frequently eight banks, or eight IT exporters. Eight correlated
positions is one position with eight commission bills, and the drawdown arrives
all at once.

This module applies the constraints that make a ranked list into a book:

    sector cap         no sector may exceed a share of the deployed risk
    correlation cap    reject a name too correlated with what is already in
    risk budget        total risk (Σ position risk) is bounded, not position count
    per-name cap       no single name may dominate, however convinced we are
    minimum edge       below the conviction bar nothing is taken, ever

Design decisions worth defending:

  * **Greedy, not optimised.** A mean-variance optimiser needs an expected-return
    vector and a covariance matrix, and both are estimated from the same short,
    noisy history. The optimiser then concentrates precisely where the estimation
    error is largest — it is an error-maximiser wearing a lab coat. Greedy
    selection under hard caps is worse in theory and considerably better in
    practice at this data scale.

  * **Risk budget, not slot count.** Eight slots means a quiet stock and a
    volatile one count the same, which they emphatically do not. We size by
    distance to stop and bound the sum.

  * **Every rejection is recorded with a reason.** A constructor that silently
    drops names is impossible to trust or debug, so the output carries the
    rejected list and why each fell out.

Pure functions throughout: correlations and prices are passed in, never fetched.
"""
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

#: Share of deployed risk any one sector may carry.
MAX_SECTOR_SHARE = 0.35
#: Pairwise correlation above which two names are treated as the same bet.
MAX_CORRELATION = 0.75
#: Share of the risk budget any single position may carry.
MAX_POSITION_SHARE = 0.20
#: Total portfolio risk as a share of equity — the sum of all "distance to stop".
RISK_BUDGET_PCT = 6.0
#: Risk per position as a share of equity, before conviction scaling.
BASE_RISK_PCT = 1.0
MIN_CONVICTION = 55.0
MAX_POSITIONS = 8


@dataclass
class Candidate:
    """One name under consideration. `stop` is what makes risk measurable."""
    symbol_id: int
    ticker: str
    conviction: float
    close: float
    sector: str | None = None
    stop: float | None = None
    risk_multiplier: float = 1.0
    news_veto: bool = False

    @property
    def risk_per_share(self) -> float | None:
        if self.stop is None or self.stop <= 0 or self.stop >= self.close:
            return None
        return self.close - self.stop


@dataclass
class Allocation:
    ticker: str
    symbol_id: int
    conviction: float
    quantity: int
    entry_price: float
    stop: float
    risk_amount: float
    risk_share: float
    sector: str | None
    note: str


@dataclass
class Portfolio:
    allocations: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    risk_deployed: float = 0.0
    risk_budget: float = 0.0
    sector_risk: dict = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "allocations": [a.__dict__ for a in self.allocations],
            "rejected": self.rejected,
            "risk_deployed": round(self.risk_deployed, 2),
            "risk_budget": round(self.risk_budget, 2),
            "risk_used_pct": (round(self.risk_deployed / self.risk_budget * 100, 1)
                              if self.risk_budget > 0 else 0.0),
            "sector_risk": {k: round(v, 2) for k, v in self.sector_risk.items()},
            "positions": len(self.allocations),
            "note": self.note,
        }


def _reject(ticker: str, reason: str) -> dict:
    return {"ticker": ticker, "reason": reason}


def _too_correlated(ticker: str, held: list, correlations: dict,
                    limit: float) -> str | None:
    """Correlation is treated as a hard gate rather than a penalty: a 0.9-correlated
    pair is not 'slightly worse', it is the same trade twice."""
    for other in held:
        key = (ticker, other) if (ticker, other) in correlations else (other, ticker)
        rho = correlations.get(key)
        if rho is not None and abs(rho) > limit:
            return f"{abs(rho):.2f} correlated with {other} already in the book"
    return None


def construct(candidates: list, equity: float, *,
              correlations: dict | None = None,
              existing_sectors: dict | None = None,
              existing_tickers: list | None = None,
              risk_budget_pct: float = RISK_BUDGET_PCT,
              base_risk_pct: float = BASE_RISK_PCT,
              max_sector_share: float = MAX_SECTOR_SHARE,
              max_position_share: float = MAX_POSITION_SHARE,
              max_correlation: float = MAX_CORRELATION,
              min_conviction: float = MIN_CONVICTION,
              max_positions: int = MAX_POSITIONS) -> Portfolio:
    """Build a book from a ranked candidate list under hard constraints.

    `correlations` maps (ticker_a, ticker_b) -> rho, in either key order.
    `existing_sectors` is risk already deployed per sector, so the caps apply to
    the whole book rather than only to today's additions — the alternative lets
    you build a concentrated portfolio one diversified day at a time.
    """
    correlations = correlations or {}
    sector_risk = dict(existing_sectors or {})
    held = list(existing_tickers or [])

    budget = equity * risk_budget_pct / 100.0
    deployed = sum(sector_risk.values())
    per_name_cap = budget * max_position_share

    portfolio = Portfolio(risk_budget=budget, sector_risk=sector_risk)
    if budget <= 0:
        portfolio.note = "No risk budget — nothing can be deployed."
        return portfolio

    for c in sorted(candidates, key=lambda x: x.conviction, reverse=True):
        if len(portfolio.allocations) >= max_positions:
            portfolio.rejected.append(_reject(c.ticker, "position limit reached"))
            continue
        if c.news_veto:
            portfolio.rejected.append(_reject(c.ticker, "news veto"))
            continue
        if c.conviction < min_conviction:
            portfolio.rejected.append(
                _reject(c.ticker, f"conviction {c.conviction:.0f} below the "
                                  f"{min_conviction:.0f} bar"))
            continue
        if c.risk_multiplier <= 0:
            portfolio.rejected.append(_reject(c.ticker, "risk engine sized it to zero"))
            continue
        risk_per_share = c.risk_per_share
        if risk_per_share is None:
            # No stop means no measurable risk, and an unmeasurable position
            # cannot be fitted into a risk budget. Refusing is the honest answer.
            portfolio.rejected.append(
                _reject(c.ticker, "no valid stop — risk cannot be measured"))
            continue

        clash = _too_correlated(c.ticker, held, correlations, max_correlation)
        if clash:
            portfolio.rejected.append(_reject(c.ticker, clash))
            continue

        # Intended risk, scaled by conviction, then clipped by every cap in turn.
        wanted = min(equity * base_risk_pct / 100.0 * c.risk_multiplier,
                     per_name_cap, budget - deployed)

        sector = c.sector or "Unclassified"
        sector_headroom = budget * max_sector_share - sector_risk.get(sector, 0.0)
        if sector_headroom <= 0:
            portfolio.rejected.append(
                _reject(c.ticker, f"{sector} already at its "
                                  f"{max_sector_share:.0%} cap"))
            continue
        wanted = min(wanted, sector_headroom)

        quantity = int(wanted // risk_per_share)
        if quantity < 1:
            portfolio.rejected.append(
                _reject(c.ticker, "remaining budget is smaller than one share's risk"))
            continue

        actual_risk = quantity * risk_per_share
        deployed += actual_risk
        sector_risk[sector] = sector_risk.get(sector, 0.0) + actual_risk
        held.append(c.ticker)

        capped = []
        if abs(wanted - sector_headroom) < 1e-9:
            capped.append(f"trimmed by the {sector} cap")
        if abs(wanted - per_name_cap) < 1e-9:
            capped.append("trimmed by the per-name cap")
        if abs(wanted - (budget - deployed + actual_risk)) < 1e-9:
            capped.append("took the last of the risk budget")

        portfolio.allocations.append(Allocation(
            ticker=c.ticker, symbol_id=c.symbol_id, conviction=c.conviction,
            quantity=quantity, entry_price=c.close, stop=c.stop,
            risk_amount=round(actual_risk, 2),
            risk_share=round(actual_risk / budget, 4), sector=sector,
            note="; ".join(capped) or "sized at intended risk"))

    portfolio.risk_deployed = deployed
    portfolio.sector_risk = sector_risk
    portfolio.note = (
        f"{len(portfolio.allocations)} positions using "
        f"{deployed / budget * 100:.0f}% of a {risk_budget_pct:.0f}% risk budget. "
        f"{len(portfolio.rejected)} candidates rejected — every one with a reason.")
    return portfolio


def build_from_setups(session, setups: list, equity: float, **kwargs) -> dict:
    """Adapter: Alpha Stack setups -> Candidates -> a constructed book.

    Kept separate from `construct` so the constraint logic stays pure and
    testable without a database.
    """
    from app.models import ScreenerSnapshot, Symbol
    from app.services.autopilot import FALLBACK_STOP_ATR_MULT

    ids = {s.ticker: s for s in session.query(Symbol).filter(Symbol.active).all()}
    candidates = []
    for s in setups:
        sym = ids.get(s.get("ticker"))
        if sym is None or not s.get("close"):
            continue
        close = float(s["close"])
        snap = session.get(ScreenerSnapshot, sym.id)
        atr = float(snap.atr_14) if snap is not None and snap.atr_14 else None
        stop = round(close - FALLBACK_STOP_ATR_MULT * atr, 2) if atr else None
        candidates.append(Candidate(
            symbol_id=sym.id, ticker=sym.ticker, conviction=float(s["conviction"]),
            close=close, sector=sym.sector, stop=stop,
            risk_multiplier=float(s.get("risk_multiplier") or 0.0),
            news_veto=bool(s.get("news_veto"))))

    return construct(candidates, equity, **kwargs).to_dict()
