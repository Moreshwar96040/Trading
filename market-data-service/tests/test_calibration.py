"""Adaptive conviction: recorder, labeller and the calibration/weight engine.

The important tests plant a KNOWN relationship in synthetic data and check the
engine recovers it — and, just as important, that it stays quiet when there is
nothing there. A calibration engine that finds signal in noise is worse than none.
"""
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ai.calibration import (MIN_SAMPLES_DIAGNOSTIC, MIN_SAMPLES_WEIGHTS,
                                calibration_report)
from app.models import ConvictionHistory, OhlcvDaily, Symbol
from app.services.conviction_recorder import label_outcomes


def _sym(session: Session, ticker="TCS") -> Symbol:
    sym = Symbol(ticker=ticker, yahoo_symbol=f"{ticker}.NS", name=f"{ticker} Ltd",
                 sector="IT")
    session.add(sym)
    session.commit()
    return sym


def _row(session: Session, symbol_id: int, day: date, *, label=None,
         quality=0.5, news=0.5, conviction=50.0, veto=False, **kw):
    session.add(ConvictionHistory(
        symbol_id=symbol_id, as_of_date=day, conviction=conviction,
        verdict="NORMAL", news_veto=veto, has_live_signal=False,
        technical_strength=kw.get("technical", 0.5), quality_strength=quality,
        news_strength=news, momentum_strength=kw.get("momentum", 0.5),
        ml_strength=0.5, macro_strength=0.5, regime_strength=0.5,
        close=100.0, fwd_return_10d=label))


def _seed(session: Session, n: int, *, signal_layer="quality", noise=1.0, seed=7):
    """n rows where `signal_layer` genuinely predicts the label, others are noise."""
    rng = random.Random(seed)
    sym = _sym(session)
    start = date(2026, 1, 1)
    for i in range(n):
        strength = rng.random()
        label = (strength - 0.5) * 10 + rng.gauss(0, noise)     # planted signal
        kwargs = {"quality": 0.5, "news": rng.random(),
                  "technical": rng.random(), "momentum": rng.random()}
        kwargs[signal_layer] = strength
        _row(session, sym.id, start + timedelta(days=i), label=round(label, 4),
             conviction=round(20 + strength * 70, 2), **kwargs)
    session.commit()
    return sym


# ---------- gates ----------

def test_reports_collecting_before_diagnostic_threshold(session: Session):
    _seed(session, 5)
    out = calibration_report(session)
    assert out["status"] == "COLLECTING"
    assert out["needed"] == MIN_SAMPLES_DIAGNOSTIC
    assert "cannot be backfilled" in out["note"]


def test_diagnostics_unlock_but_weights_stay_gated(session: Session):
    _seed(session, MIN_SAMPLES_DIAGNOSTIC + 20)
    out = calibration_report(session)
    assert out["status"] == "OK"
    assert out["layer_ic"] and out["calibration"]
    # not enough rows for a 7-parameter fit yet
    assert out["weights"]["status"] == "INSUFFICIENT"
    assert out["weights"]["needed"] == MIN_SAMPLES_WEIGHTS


# ---------- does it find real signal? ----------

def test_ic_detects_the_planted_layer(session: Session):
    _seed(session, 250, signal_layer="quality", noise=1.0)
    out = calibration_report(session)
    by_layer = {r["layer"]: r for r in out["layer_ic"]}
    assert by_layer["quality"]["ic"] > 0.3
    assert by_layer["quality"]["significant"] is True
    # a pure-noise layer should not be flagged significant
    assert by_layer["news"]["significant"] is False


def test_weights_shift_toward_the_predictive_layer(session: Session):
    _seed(session, 300, signal_layer="quality", noise=1.0)
    w = calibration_report(session)["weights"]
    assert w["status"] == "OK"
    by_layer = {r["layer"]: r for r in w["weights"]}
    assert by_layer["quality"]["delta"] > 0          # quality earns weight
    assert abs(sum(r["suggested"] for r in w["weights"]) - 100.0) < 0.5


def test_shrinkage_keeps_suggestions_near_the_prior(session: Session):
    """Even with a blazing signal the suggestion must not leap to the raw fit —
    a few hundred noisy samples don't justify abandoning the prior."""
    _seed(session, 300, signal_layer="quality", noise=0.3)
    w = calibration_report(session)["weights"]
    q = next(r for r in w["weights"] if r["layer"] == "quality")
    assert q["suggested"] < q["learned_raw"]         # pulled back toward current
    assert w["shrinkage"] == 0.3


def test_pure_noise_produces_no_significant_layers(session: Session):
    """The most important negative test: random data must not look like edge."""
    rng = random.Random(11)
    sym = _sym(session, "NOISE")
    start = date(2026, 1, 1)
    for i in range(250):
        _row(session, sym.id, start + timedelta(days=i),
             label=round(rng.gauss(0, 2), 4), quality=rng.random(),
             news=rng.random(), technical=rng.random(), momentum=rng.random(),
             conviction=round(rng.uniform(20, 90), 2))
    session.commit()
    out = calibration_report(session)
    significant = [r["layer"] for r in out["layer_ic"] if r["significant"]]
    assert not significant, f"found phantom signal in noise: {significant}"


# ---------- calibration curve + veto audit ----------

def test_calibration_curve_buckets_by_band(session: Session):
    _seed(session, 200)
    bands = calibration_report(session)["calibration"]
    assert [b["band"] for b in bands] == ["<40 stand aside", "40-55 small",
                                          "55-75 normal", "75+ high"]
    assert sum(b["n"] for b in bands) > 0


def test_veto_audit_flags_a_veto_that_blocks_winners(session: Session):
    sym = _sym(session, "VETO")
    start = date(2026, 1, 1)
    for i in range(40):                      # vetoed setups did WELL -> costly veto
        _row(session, sym.id, start + timedelta(days=i), label=5.0, veto=True)
    for i in range(40, 80):
        _row(session, sym.id, start + timedelta(days=i), label=-1.0, veto=False)
    session.commit()
    audit = calibration_report(session)["veto_audit"]
    assert audit["n"] == 40
    assert "costing you" in audit["verdict"]


# ---------- labeller ----------

def test_labeller_computes_forward_returns_and_excursions(session: Session):
    sym = _sym(session, "LBL")
    start = date(2026, 3, 2)
    session.add(ConvictionHistory(
        symbol_id=sym.id, as_of_date=start, conviction=60.0, verdict="NORMAL",
        news_veto=False, has_live_signal=True, close=100.0,
        technical_strength=0.8, quality_strength=0.6, news_strength=0.5,
        momentum_strength=0.5, ml_strength=0.5, macro_strength=0.5,
        regime_strength=0.5))
    for i in range(1, 25):                   # +1% per bar
        px = 100.0 * (1 + i / 100.0)
        session.add(OhlcvDaily(symbol_id=sym.id, trade_date=start + timedelta(days=i),
                               open=px, high=px * 1.01, low=px * 0.99, close=px,
                               volume=1000))
    session.commit()

    out = label_outcomes(session)
    assert out["labelled"] == 1
    row = session.get(ConvictionHistory, (sym.id, start))
    assert round(float(row.fwd_return_5d)) == 5
    assert round(float(row.fwd_return_10d)) == 10
    assert float(row.mfe_pct) > float(row.fwd_return_10d)   # high exceeds close
    assert row.labelled_at is not None


def test_labeller_leaves_immature_rows_null(session: Session):
    sym = _sym(session, "YOUNG")
    start = date(2026, 3, 2)
    session.add(ConvictionHistory(
        symbol_id=sym.id, as_of_date=start, conviction=60.0, verdict="NORMAL",
        news_veto=False, has_live_signal=False, close=100.0))
    for i in range(1, 4):                    # only 3 bars — nothing matures
        session.add(OhlcvDaily(symbol_id=sym.id, trade_date=start + timedelta(days=i),
                               open=100, high=101, low=99, close=100, volume=10))
    session.commit()
    assert label_outcomes(session)["labelled"] == 0
    assert session.get(ConvictionHistory, (sym.id, start)).fwd_return_10d is None
