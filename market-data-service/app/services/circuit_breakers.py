"""Circuit breakers — the conditions under which the system must stop trading itself.

A self-learning system's most dangerous failure mode is not being wrong; it is
being wrong *confidently and continuously*, because every mechanism inside it is
designed to keep going. The gates in `app/ai/gates.py` stop a bad model getting
in. These stop a model that has already got in, and has started losing.

Each breaker answers one question, and each is deliberately blunt — a breaker
with judgement is a breaker that can be talked out of tripping:

    DRAWDOWN     the autopilot book is down more than we agreed to lose
    LOSS_STREAK  consecutive losers beyond what the hit rate should produce
    IC_COLLAPSE  the score has stopped ranking forward returns at all
    STALE_DATA   we are trading on prices that are no longer current
    DEAD_LABELS  outcomes stopped being recorded, so nothing is being learned

Tripping is a *halt on new entries*, never a forced liquidation. Panic-selling
an existing book on a metric is how a bad week becomes a bad year; existing
positions keep their stops and exit on their own terms.

Resetting is manual, and that is on purpose. An auto-resetting breaker is a
breaker that lets the same failure repeat on a timer.
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

#: Peak-to-trough on realised autopilot P&L, as a share of the peak.
MAX_DRAWDOWN_PCT = 15.0
#: Consecutive losing closes. At a 45% hit rate, six in a row is ~2% likely.
MAX_LOSS_STREAK = 6
#: Below this the score is not ranking anything; it is decoration.
MIN_ROLLING_IC = 0.0
IC_WINDOW_DAYS = 90
IC_MIN_SAMPLES = 100
#: Trading days of silence before prices count as stale.
MAX_PRICE_STALENESS_DAYS = 3
#: Days without a newly labelled outcome before the learning loop counts as dead.
MAX_LABEL_GAP_DAYS = 21


@dataclass(frozen=True)
class Breaker:
    name: str
    tripped: bool
    severity: str            # HALT | WARN | OK
    reason: str
    detail: dict | None = None

    def to_dict(self) -> dict:
        return {"breaker": self.name, "tripped": self.tripped,
                "severity": self.severity, "reason": self.reason,
                **({"detail": self.detail} if self.detail else {})}


def _ok(name: str, reason: str, detail: dict | None = None) -> Breaker:
    return Breaker(name, False, "OK", reason, detail)


# ---------- individual breakers ----------

def check_drawdown(closed_pnl: list[float],
                   limit_pct: float = MAX_DRAWDOWN_PCT) -> Breaker:
    """Peak-to-trough on the cumulative realised curve.

    Measured against the running peak rather than the starting balance, because
    the number that matters psychologically and practically is how much of the
    gain has been handed back.
    """
    if not closed_pnl:
        return _ok("drawdown", "no closed trades yet")
    equity, peak, trough_from_peak = 0.0, 0.0, 0.0
    for pnl in closed_pnl:
        equity += pnl
        peak = max(peak, equity)
        trough_from_peak = min(trough_from_peak, equity - peak)
    # A book that has never been in profit has no peak to measure against, and
    # dividing by zero to report a comfortable 0% would be the worst possible
    # answer — that is exactly the book we most want to halt. Fall back to gross
    # turnover: losing everything you ever put at risk reads as 100%.
    denominator = peak if peak > 0 else sum(abs(p) for p in closed_pnl)
    drawdown_pct = (round(abs(trough_from_peak) / denominator * 100.0, 2)
                    if denominator > 0 else 0.0)
    tripped = drawdown_pct >= limit_pct
    return Breaker("drawdown", tripped, "HALT" if tripped else "OK",
                   f"{drawdown_pct:.1f}% peak-to-trough on realised P&L"
                   + (f" — limit is {limit_pct:.0f}%" if tripped else ""),
                   {"drawdown_pct": drawdown_pct, "limit_pct": limit_pct})


def check_loss_streak(closed_pnl: list[float],
                      limit: int = MAX_LOSS_STREAK) -> Breaker:
    """Consecutive losers, most recent first. A long streak is either bad luck or
    a broken edge, and we cannot tell which from inside the streak — so we stop
    and look."""
    streak = 0
    for pnl in reversed(closed_pnl):
        if pnl < 0:
            streak += 1
        else:
            break
    tripped = streak >= limit
    return Breaker("loss_streak", tripped, "HALT" if tripped else "OK",
                   f"{streak} consecutive losing trades"
                   + (f" — limit is {limit}" if tripped else ""),
                   {"streak": streak, "limit": limit})


def check_ic_collapse(session: Session, window_days: int = IC_WINDOW_DAYS,
                      floor: float = MIN_ROLLING_IC) -> Breaker:
    """Is conviction still ranking forward returns, recently?

    A model can look fine on all-time statistics for a long while after it has
    stopped working, because the good old days keep voting. This looks only at
    the recent window.
    """
    import pandas as pd

    from app.ai.calibration import _spearman
    from app.models import ConvictionHistory

    cutoff = date.today() - timedelta(days=window_days)
    rows = session.execute(
        select(ConvictionHistory.conviction, ConvictionHistory.fwd_return_10d)
        .where(ConvictionHistory.fwd_return_10d.isnot(None),
               ConvictionHistory.as_of_date >= cutoff)).all()
    if len(rows) < IC_MIN_SAMPLES:
        return _ok("ic_collapse",
                   f"{len(rows)} labelled setups in the last {window_days} days — "
                   f"need {IC_MIN_SAMPLES} before a rolling IC means anything",
                   {"n": len(rows)})

    ic = _spearman(pd.Series([float(r[0]) for r in rows]),
                   pd.Series([float(r[1]) for r in rows]))
    if ic is None or ic != ic:
        return _ok("ic_collapse", "rolling IC could not be computed", {"n": len(rows)})
    ic = round(float(ic), 4)
    tripped = ic <= floor
    return Breaker("ic_collapse", tripped, "HALT" if tripped else "OK",
                   f"rolling {window_days}-day IC {ic:+.4f} on {len(rows)} setups"
                   + (" — conviction has stopped ranking returns" if tripped else ""),
                   {"ic": ic, "n": len(rows), "window_days": window_days})


def check_price_staleness(session: Session,
                          limit_days: int = MAX_PRICE_STALENESS_DAYS) -> Breaker:
    """Trading on stale prices is worse than not trading — the score looks
    confident and describes a market that has moved on."""
    from sqlalchemy import func

    from app.models import OhlcvDaily

    latest = session.scalar(select(func.max(OhlcvDaily.trade_date)))
    if latest is None:
        return Breaker("stale_data", True, "HALT", "no price history at all")
    age = (date.today() - latest).days
    tripped = age > limit_days
    return Breaker("stale_data", tripped, "HALT" if tripped else "OK",
                   f"latest price bar is {age} day(s) old ({latest})"
                   + (f" — limit is {limit_days}" if tripped else ""),
                   {"latest_bar": str(latest), "age_days": age})


def check_labelling_alive(session: Session,
                          limit_days: int = MAX_LABEL_GAP_DAYS) -> Breaker:
    """If outcomes stopped being labelled, the system is no longer learning — it
    is just trading. That is a warning, not a halt: the model in use is still the
    one that was validated."""
    from sqlalchemy import func

    from app.models import ConvictionHistory

    latest = session.scalar(select(func.max(ConvictionHistory.labelled_at)))
    if latest is None:
        return Breaker("dead_labels", False, "WARN",
                       "no outcomes labelled yet — the learning loop has not "
                       "started producing training data")
    age = (date.today() - latest.date()).days
    tripped = age > limit_days
    return Breaker("dead_labels", tripped, "WARN" if tripped else "OK",
                   f"last outcome labelled {age} day(s) ago"
                   + (" — the labeller may not be running" if tripped else ""),
                   {"age_days": age})


# ---------- combination ----------

def evaluate(session: Session, closed_pnl: list[float] | None = None) -> dict:
    """Run every breaker. Any HALT-severity trip stops new autopilot entries."""
    if closed_pnl is None:
        closed_pnl = _closed_pnl(session)

    breakers = [check_drawdown(closed_pnl), check_loss_streak(closed_pnl),
                check_ic_collapse(session), check_price_staleness(session),
                check_labelling_alive(session)]
    halts = [b for b in breakers if b.tripped and b.severity == "HALT"]
    warns = [b for b in breakers if b.tripped and b.severity == "WARN"]

    if halts:
        summary = ("Entries halted: " + "; ".join(b.reason for b in halts)
                   + ". Open positions keep their stops and exit normally.")
    elif warns:
        summary = "Trading allowed, with warnings: " + "; ".join(b.reason for b in warns)
    else:
        summary = "All clear — no breaker tripped."

    return {"halted": bool(halts), "halt_reasons": [b.name for b in halts],
            "warnings": [b.name for b in warns],
            "breakers": [b.to_dict() for b in breakers],
            "summary": summary,
            "note": ("A halt blocks new entries only, and resets manually — an "
                     "auto-resetting breaker just lets the same failure repeat.")}


#: A learner-promoted champion must prove itself within this many days.
AUTO_PROBATION_DAYS = 45
#: Rolling IC below this, while an automatic model is live, reverts it.
PROBATION_MIN_IC = 0.0


def auto_rollback_if_failing(session: Session) -> dict:
    """Revert an automatic weight change that is not working.

    This is the property that makes full autonomy survivable. A system allowed to
    promote itself must also be able to *un*-promote itself, or its worst decision
    persists until a human happens to look.

    Deliberately narrow. It only reverts a champion the *learner* promoted, and
    only back to a set a person approved. It never touches a human's choice —
    if you promoted something and it is losing, that is your call to reverse, and
    a machine overriding your explicit decision would be a worse failure than the
    one it was trying to fix.
    """
    from app.services.model_registry import (GLOBAL_SCOPE, REGIME_SCOPES,
                                             AUTOMATED_ACTORS, get_anchor,
                                             get_champion, revert_to_anchor)

    reverted, checked = [], []
    ic = check_ic_collapse(session, floor=PROBATION_MIN_IC)

    for scope in (GLOBAL_SCOPE, *REGIME_SCOPES):
        champion = get_champion(session, scope=scope)
        if champion is None:
            continue
        promoted_by = (champion.promoted_by or "").strip().lower()
        if promoted_by not in AUTOMATED_ACTORS or champion.is_anchor:
            continue                        # a person's decision — not ours to undo
        checked.append(scope)

        age_days = ((datetime.now(timezone.utc) - champion.promoted_at).days
                    if champion.promoted_at else 0)
        if not ic.tripped:
            continue
        if age_days > AUTO_PROBATION_DAYS:
            # Past probation the model is no longer "the new thing"; reverting it
            # on a rolling metric would just thrash between two mediocre sets.
            continue

        anchor = get_anchor(session, scope=scope)
        if anchor is None:
            continue
        out = revert_to_anchor(
            session, "auto-rollback", scope=scope,
            reason=(f"automatic model {champion.label} on probation and "
                    f"{ic.reason}"))
        if out.get("status") == "OK":
            reverted.append({"scope": scope, "from": champion.label,
                             "to": out["champion"], "age_days": age_days})
            _log_revert(session, scope, champion.label, out["champion"], ic.reason)

    return {"reverted": reverted, "checked": checked,
            "ic": ic.to_dict(),
            "note": ("Only learner-promoted models are auto-reverted, and only "
                     "back to a set you approved. Your own promotions are never "
                     "overridden.")}


def _log_revert(session: Session, scope: str, from_label: str, to_label: str,
                why: str) -> None:
    from app.services.auto_adapt import _record
    _record(session, scope=scope, action="ROLLED_BACK",
            reason=f"Auto-reverted {from_label} -> {to_label}: {why}",
            triggered_by="auto-rollback")


def _closed_pnl(session: Session) -> list[float]:
    """Realised autopilot P&L in close order."""
    from app.models import AutopilotTrade
    trades = session.scalars(
        select(AutopilotTrade)
        .where(AutopilotTrade.status == "CLOSED",
               AutopilotTrade.realized_pnl.isnot(None))
        .order_by(AutopilotTrade.exit_date)).all()
    return [float(t.realized_pnl) for t in trades]
