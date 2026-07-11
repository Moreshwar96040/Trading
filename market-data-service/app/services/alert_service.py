"""Evaluates ACTIVE alerts against the current screener_snapshot values.

Runs automatically after each daily-sync snapshot refresh, and on demand via
POST /internal/alerts/evaluate. One-shot: a triggered alert stays TRIGGERED
until re-armed from the UI.
"""
import logging
import operator
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, ScreenerSnapshot

log = logging.getLogger(__name__)

_OPS = {"gt": operator.gt, "gte": operator.ge, "lt": operator.lt,
        "lte": operator.le, "eq": operator.eq}


def evaluate_alerts(session: Session) -> dict:
    """Returns {checked, triggered, skipped}. Unknown fields are skipped (not failed)."""
    alerts = session.scalars(select(Alert).where(Alert.status == "ACTIVE")).all()
    triggered, skipped = 0, 0

    for alert in alerts:
        snapshot = session.get(ScreenerSnapshot, alert.symbol_id)
        if snapshot is None:
            skipped += 1
            continue
        current = getattr(snapshot, alert.field, None)
        compare = _OPS.get(alert.op)
        if current is None or compare is None:
            skipped += 1
            continue
        if compare(float(current), float(alert.value)):
            alert.status = "TRIGGERED"
            alert.triggered_at = datetime.now(timezone.utc)
            alert.triggered_value = float(current)
            triggered += 1
            log.info("Alert %d triggered: symbol_id=%d %s %s %s (current=%s)",
                     alert.id, alert.symbol_id, alert.field, alert.op, alert.value, current)

    session.commit()
    return {"checked": len(alerts), "triggered": triggered, "skipped": skipped}
