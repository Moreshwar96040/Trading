"""AI Trade Ideas: rank symbols by *confluence* of independent evidence (Phase D).

A good discretionary trader never acts on one indicator; they act when several
independent reads agree. This module scores that agreement per symbol:

    +  ML next-day prediction (direction, weighted by its honest test accuracy)
    +  live strategy ENTRY signals (each user strategy that fires is a vote)
    +  trend regime from the adaptive-risk engine
    +  fundamental quality (ROE, sane P/E)
    -  EXIT signals / downtrend / DOWN predictions subtract

Output: ranked ideas, each with an entry/stop/target plan and a human rationale.
Scoring is a pure function (unit-testable); DB assembly lives in `build_ideas`.
"""
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.risk import InsufficientDataError, RiskRecommendation, recommend_risk
from app.models import AiPrediction, ScreenerSnapshot, Strategy, StrategySignal, Symbol
from app.services.indicator_service import load_ohlcv

log = logging.getLogger(__name__)

MIN_ACCURACY_TO_COUNT = 50.0     # a model below coin-flip accuracy gets no vote


@dataclass
class IdeaInputs:
    predicted_return_pct: float | None = None
    direction: str | None = None                 # UP | DOWN | FLAT
    test_accuracy: float | None = None
    entry_signals: list[str] = field(default_factory=list)   # strategy names
    exit_signals: list[str] = field(default_factory=list)
    regime: str | None = None
    roe_pct: float | None = None
    pe_trailing: float | None = None


def score_idea(i: IdeaInputs) -> tuple[float, list[str]]:
    """Confluence score + the reasons behind it. Pure, deterministic."""
    score = 0.0
    reasons: list[str] = []

    if i.direction and i.test_accuracy is not None and i.test_accuracy >= MIN_ACCURACY_TO_COUNT:
        weight = 1.0 + (i.test_accuracy - MIN_ACCURACY_TO_COUNT) / 25.0   # 50%→1.0, 75%→2.0
        if i.direction == "UP":
            score += 2.0 * weight
            reasons.append(f"Model predicts +{i.predicted_return_pct}% "
                           f"(test accuracy {i.test_accuracy}%)")
        elif i.direction == "DOWN":
            score -= 2.0 * weight
            reasons.append(f"Model predicts {i.predicted_return_pct}% "
                           f"(test accuracy {i.test_accuracy}%)")

    for name in i.entry_signals[:2]:                     # cap: 2 strategies max
        score += 2.0
        reasons.append(f"Strategy '{name}' fired ENTRY")
    for name in i.exit_signals[:2]:
        score -= 2.0
        reasons.append(f"Strategy '{name}' fired EXIT")

    regime_points = {"STRONG_UPTREND": 2.0, "UPTREND": 1.0, "NEUTRAL": 0.0, "DOWNTREND": -2.0}
    if i.regime in regime_points:
        score += regime_points[i.regime]
        reasons.append(f"Regime: {i.regime.replace('_', ' ').lower()}")

    if i.roe_pct is not None and i.roe_pct >= 15:
        score += 1.0
        reasons.append(f"Quality: ROE {i.roe_pct}%")
    if i.pe_trailing is not None and 0 < i.pe_trailing <= 30:
        score += 0.5
        reasons.append(f"Valuation sane: P/E {i.pe_trailing}")

    return round(score, 2), reasons


def build_ideas(session: Session, limit: int = 10) -> dict:
    symbols = session.scalars(select(Symbol).where(Symbol.active)).all()
    predictions = {p.symbol_id: p for p in session.scalars(select(AiPrediction)).all()}
    snapshots = {s.symbol_id: s for s in session.scalars(select(ScreenerSnapshot)).all()}
    strategy_names = {s.id: s.name for s in session.scalars(select(Strategy)).all()}

    signals_by_symbol: dict[int, list[StrategySignal]] = {}
    for sig in session.scalars(select(StrategySignal)).all():
        signals_by_symbol.setdefault(sig.symbol_id, []).append(sig)

    ideas = []
    for sym in symbols:
        pred = predictions.get(sym.id)
        snap = snapshots.get(sym.id)
        sigs = signals_by_symbol.get(sym.id, [])

        risk: RiskRecommendation | None = None
        try:
            df = load_ohlcv(session, sym.id)
            risk = recommend_risk(df.set_index("trade_date"))
        except (InsufficientDataError, Exception) as exc:   # noqa: BLE001 — skip quietly
            if not isinstance(exc, InsufficientDataError):
                log.warning("Risk rec failed for %s: %s", sym.ticker, exc)

        inputs = IdeaInputs(
            predicted_return_pct=float(pred.predicted_return_pct) if pred else None,
            direction=pred.direction if pred else None,
            test_accuracy=float(pred.test_direction_accuracy)
                if pred and pred.test_direction_accuracy is not None else None,
            entry_signals=[strategy_names.get(s.strategy_id, "?")
                           for s in sigs if s.signal == "ENTRY"],
            exit_signals=[strategy_names.get(s.strategy_id, "?")
                          for s in sigs if s.signal == "EXIT"],
            regime=risk.regime if risk else None,
            roe_pct=float(snap.roe_pct) if snap and snap.roe_pct is not None else None,
            pe_trailing=float(snap.pe_trailing)
                if snap and snap.pe_trailing is not None else None,
        )
        score, reasons = score_idea(inputs)
        if score <= 0:
            continue

        ideas.append({
            "ticker": sym.ticker,
            "name": sym.name,
            "score": score,
            "reasons": reasons,
            "close": float(snap.close) if snap else None,
            "as_of_date": snap.as_of_date.isoformat() if snap else None,
            "entry_strategies": inputs.entry_signals,
            "risk_plan": risk.to_dict() if risk else None,
        })

    ideas.sort(key=lambda i: i["score"], reverse=True)
    return {"ideas": ideas[:limit], "symbols_scanned": len(symbols),
            "disclaimer": "Educational paper-trading tool — not investment advice."}
