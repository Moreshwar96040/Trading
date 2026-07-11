from sqlalchemy import select

from app.models import Alert, ScreenerSnapshot
from app.services.alert_service import evaluate_alerts

from datetime import date


def _snapshot(session, symbol_id, **values):
    snap = ScreenerSnapshot(symbol_id=symbol_id, as_of_date=date(2026, 7, 1),
                            close=100.0, **values)
    session.add(snap)
    session.commit()
    return snap


def test_alert_triggers_and_records_value(session, reliance):
    _snapshot(session, reliance.id, rsi_14=25.0)
    session.add(Alert(symbol_id=reliance.id, field="rsi_14", op="lt", value=30))
    session.commit()

    result = evaluate_alerts(session)

    assert result == {"checked": 1, "triggered": 1, "skipped": 0}
    alert = session.scalars(select(Alert)).first()
    assert alert.status == "TRIGGERED"
    assert float(alert.triggered_value) == 25.0
    assert alert.triggered_at is not None


def test_alert_stays_active_when_condition_not_met(session, reliance):
    _snapshot(session, reliance.id, rsi_14=55.0)
    session.add(Alert(symbol_id=reliance.id, field="rsi_14", op="lt", value=30))
    session.commit()

    result = evaluate_alerts(session)

    assert result["triggered"] == 0
    assert session.scalars(select(Alert)).first().status == "ACTIVE"


def test_triggered_alert_not_rechecked(session, reliance):
    _snapshot(session, reliance.id, rsi_14=25.0)
    session.add(Alert(symbol_id=reliance.id, field="rsi_14", op="lt", value=30,
                      status="TRIGGERED"))
    session.commit()

    assert evaluate_alerts(session)["checked"] == 0


def test_unknown_field_and_missing_snapshot_are_skipped(session, reliance):
    from app.models import Symbol
    other = Symbol(ticker="TCS", yahoo_symbol="TCS.NS", name="TCS Ltd")
    session.add(other)
    session.commit()

    _snapshot(session, reliance.id, rsi_14=25.0)
    session.add(Alert(symbol_id=reliance.id, field="not_a_field", op="lt", value=30))
    session.add(Alert(symbol_id=other.id, field="rsi_14", op="lt", value=30))  # no snapshot
    session.commit()

    result = evaluate_alerts(session)

    assert result == {"checked": 2, "triggered": 0, "skipped": 2}


def test_close_alert_gt(session, reliance):
    _snapshot(session, reliance.id)          # close=100
    session.add(Alert(symbol_id=reliance.id, field="close", op="gt", value=90))
    session.commit()

    assert evaluate_alerts(session)["triggered"] == 1
