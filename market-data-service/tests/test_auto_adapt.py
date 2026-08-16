"""Autonomous adaptation.

A system that promotes its own weights has to be tested on what it *refuses* to
do, far more than on what it does. Most of what follows drives it toward a bad
change and asserts that it declines and says why.
"""
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.ai.calibration import LAYERS
from app.ai.gates import (MAX_LAYER_DRIFT, gate_drift_bounded,
                          gate_frozen_params_untouched)
from app.scoring import WeightSet
from app.services.auto_adapt import adapt_scope, adaptation_history, run_auto_adaptation
from app.services.model_registry import (GLOBAL_SCOPE, champion_weights,
                                         get_anchor, get_champion, promote,
                                         register, revert_to_anchor,
                                         scope_for_regime, weights_for_regime)

ANCHOR = {"technical": 25.0, "quality": 25.0, "news": 18.0, "momentum": 14.0,
          "ml": 7.0, "macro": 6.0, "regime": 5.0}


class _On:
    auto_adapt_enabled = True


class _Off:
    auto_adapt_enabled = False


def _seed_history(session: Session, n: int = 600, *, driver: str = "quality",
                  regime: str | None = None, seed: int = 5,
                  strength: float = 10.0, noise: float = 1.0) -> None:
    """Labelled history where one layer genuinely predicts the forward return.

    `strength` controls how dominant that layer is. The default is deliberately
    extreme (one layer explains almost everything) to test the guards; realistic
    edges are far weaker, which is what `strength=1.5` models.
    """
    from app.models import ConvictionHistory, OhlcvDaily, Symbol

    rng = random.Random(seed)
    regimes = [regime] if regime else ["RISK_ON", "CHOP", "RISK_OFF"]
    symbols = []
    for i in range(20):
        s = Symbol(ticker=f"A{i:03d}", yahoo_symbol=f"A{i:03d}.NS", name=f"A{i}",
                   exchange="NSE", active=True)
        session.add(s)
        symbols.append(s)
    session.flush()
    # Fresh prices so the data-staleness breaker doesn't halt adaptation.
    session.add(OhlcvDaily(symbol_id=symbols[0].id, trade_date=date.today(),
                           open=1, high=1, low=1, close=1, volume=1))

    start = date(2024, 1, 1)
    for k in range(n):
        strengths = {layer: rng.random() for layer in LAYERS}
        label = (strengths[driver] - 0.5) * strength + rng.gauss(0, noise)
        session.add(ConvictionHistory(
            symbol_id=symbols[k % len(symbols)].id,
            as_of_date=start + timedelta(days=k // len(symbols)),
            conviction=50.0, verdict="WATCH", close=100.0,
            regime_code=regimes[k % len(regimes)],
            fwd_return_10d=round(label, 4),
            **{f"{layer}_strength": round(v, 4) for layer, v in strengths.items()}))
    session.commit()


def _anchor(session: Session, scope: str = GLOBAL_SCOPE, params: dict | None = None):
    """A human-approved baseline, the way a real promotion would create one."""
    v = register(session, kind="WEIGHTS", scope=scope, label=f"human-{scope}",
                 params=params or ANCHOR)
    promote(session, v.id, "moreshwar", "baseline")
    return v


# ---------- the drift bound ----------

def test_a_small_move_is_within_the_bound():
    candidate = {**ANCHOR, "quality": 30.0}
    assert gate_drift_bounded(ANCHOR, candidate).passed


def test_a_large_move_is_blocked_and_named():
    candidate = {**ANCHOR, "quality": 60.0}
    r = gate_drift_bounded(ANCHOR, candidate)
    assert not r.passed and "quality" in r.reason


def test_a_layer_cannot_be_switched_off_automatically():
    """Zeroing a layer is a change of thesis, and a thesis needs a person."""
    r = gate_drift_bounded(ANCHOR, {**ANCHOR, "news": 0.5})
    assert not r.passed


def test_drift_is_measured_from_the_anchor_not_the_incumbent(session: Session):
    """The ratchet test. Two automatic promotions of +9 each must not be allowed
    to land 18 points from the baseline a human approved."""
    _anchor(session)
    step_one = {**ANCHOR, "quality": 34.0}         # +9, allowed
    assert gate_drift_bounded(ANCHOR, step_one).passed

    auto = register(session, kind="WEIGHTS", label="auto-1", params=step_one)
    promote(session, auto.id, "learner", "automatic", automated=True)

    # The anchor must NOT have moved with the automatic promotion.
    anchor_now = get_anchor(session)
    assert anchor_now.label == "human-global"

    step_two = {**ANCHOR, "quality": 43.0}         # +9 from incumbent, +18 from anchor
    assert not gate_drift_bounded(anchor_now.params_json, step_two).passed


def test_a_human_promotion_re_anchors(session: Session):
    """Approving a change explicitly resets the budget — that is the point of
    approving it."""
    _anchor(session)
    moved = register(session, kind="WEIGHTS", label="big", params={**ANCHOR,
                                                                  "quality": 45.0})
    promote(session, moved.id, "moreshwar", "I want this")
    assert get_anchor(session).label == "big"
    assert gate_drift_bounded(get_anchor(session).params_json,
                              {**ANCHOR, "quality": 50.0}).passed


# ---------- frozen safety rules ----------

def test_the_news_veto_is_not_learnable():
    r = gate_frozen_params_untouched({**ANCHOR, "news_veto_threshold": 0.2})
    assert not r.passed and "news_veto_threshold" in r.reason


def test_plain_layer_weights_are_fine():
    assert gate_frozen_params_untouched(ANCHOR).passed


# ---------- regime scoping ----------

def test_each_regime_maps_to_a_learning_bucket():
    assert scope_for_regime("RISK_ON") == "risk_on"
    assert scope_for_regime("CHOP") == "neutral"
    assert scope_for_regime("BEAR_RALLY") == "risk_off"
    assert scope_for_regime(None) == GLOBAL_SCOPE


def test_a_regime_without_its_own_champion_uses_global(session: Session):
    """A scope only diverges once it has earned it."""
    _anchor(session)
    assert weights_for_regime(session, "RISK_ON").label == "human-global"


def test_a_regime_champion_overrides_global(session: Session):
    _anchor(session)
    risk_on = register(session, kind="WEIGHTS", scope="risk_on", label="ro",
                       params={**ANCHOR, "momentum": 20.0, "ml": 1.0})
    promote(session, risk_on.id, "moreshwar")
    assert weights_for_regime(session, "RISK_ON").label == "ro"
    assert weights_for_regime(session, "RISK_OFF").label == "human-global"


def test_scopes_have_independent_champions(session: Session):
    """The single-champion rule is per scope now — promoting in one must not
    retire the other."""
    _anchor(session)
    ro = register(session, kind="WEIGHTS", scope="risk_on", label="ro",
                  params=ANCHOR)
    promote(session, ro.id, "moreshwar")
    assert get_champion(session, scope=GLOBAL_SCOPE).label == "human-global"
    assert get_champion(session, scope="risk_on").label == "ro"


# ---------- the loop's refusals ----------

def test_off_by_default(session: Session):
    out = run_auto_adaptation(session, _Off())
    assert out["status"] == "DISABLED"


def test_it_will_not_learn_while_the_breakers_are_tripped(session: Session):
    """No prices seeded, so data-staleness halts. Learning from a period already
    flagged as broken teaches the model to be worse."""
    out = run_auto_adaptation(session, _On())
    assert out["status"] == "HALTED"


def test_thin_data_is_skipped_with_an_explanation(session: Session):
    _anchor(session)
    out = adapt_scope(session, GLOBAL_SCOPE)
    assert out["action"] == "SKIPPED" and "needs" in out["reason"]


def test_cooldown_blocks_back_to_back_promotions(session: Session):
    from app.models import AdaptationEvent
    _seed_history(session)
    _anchor(session)
    session.add(AdaptationEvent(scope=GLOBAL_SCOPE, action="PROMOTED",
                                reason="earlier", occurred_at=datetime.now(timezone.utc)))
    session.commit()
    out = adapt_scope(session, GLOBAL_SCOPE)
    assert out["action"] == "SKIPPED" and "cooldown" in out["reason"].lower()


def test_a_candidate_beyond_the_bound_is_shadowed_not_promoted(session: Session):
    """Quality alone drives the label, so the raw fit wants a huge shift. The
    system must want it, register it, and still not take it."""
    from app.models import ModelVersion
    _seed_history(session, n=800, driver="quality")
    _anchor(session, params={**ANCHOR, "quality": 5.0})   # far from where data points
    out = adapt_scope(session, GLOBAL_SCOPE)
    assert out["action"] == "REJECTED"
    assert "drift_bounded" in out["failed"]
    # It is still registered, because this is exactly the change worth reviewing.
    shadow = session.query(ModelVersion).filter(
        ModelVersion.created_by == "learner").first()
    assert shadow is not None and shadow.status == "SHADOW"
    assert champion_weights(session).label == "human-global"    # unchanged


def test_a_dry_run_changes_nothing(session: Session):
    from app.models import ModelVersion
    _seed_history(session)
    _anchor(session)
    before = session.query(ModelVersion).count()
    out = run_auto_adaptation(session, _On(), dry_run=True)
    assert out["status"] == "OK"
    assert session.query(ModelVersion).count() == before


# ---------- the loop's promotions ----------

def test_it_can_promote_itself_within_the_bounds(session: Session):
    """The capability actually working, on a realistically modest edge.

    This is the happy path, and it must be tested with a *weak* signal — a
    dominant one produces a huge suggested reweight that the drift cap correctly
    blocks, which would make a passing test that never exercised a promotion.
    """
    _seed_history(session, n=900, driver="quality", strength=1.5, noise=2.5)
    _anchor(session)
    out = adapt_scope(session, GLOBAL_SCOPE)
    assert out["action"] == "PROMOTED", out

    champion = get_champion(session)
    assert champion.promoted_by == "learner"
    assert not champion.is_anchor                     # automatic never re-anchors
    assert champion_weights(session).version_id == champion.id
    assert out["max_drift"] <= MAX_LAYER_DRIFT
    # The anchor is untouched, so the next automatic step is still measured
    # against what the human approved.
    assert get_anchor(session).label == "human-global"


def test_the_promoted_weights_are_the_ones_scoring_uses(session: Session):
    """An adaptation nothing reads is not an adaptation."""
    _seed_history(session, n=900, driver="quality", strength=1.5, noise=2.5)
    _anchor(session)
    before = champion_weights(session).as_dict()
    assert adapt_scope(session, GLOBAL_SCOPE)["action"] == "PROMOTED"
    assert champion_weights(session).as_dict() != before


def test_every_outcome_is_logged_including_doing_nothing(session: Session):
    """A log that only records changes cannot answer 'why hasn't it adapted?'"""
    from app.models import AdaptationEvent
    _anchor(session)
    adapt_scope(session, GLOBAL_SCOPE)                # will skip: thin data
    events = session.query(AdaptationEvent).all()
    assert len(events) == 1 and events[0].action == "SKIPPED"
    assert events[0].reason


def test_history_reports_what_is_live_per_regime(session: Session):
    _anchor(session)
    out = adaptation_history(session)
    scopes = {s["scope"]: s for s in out["scopes"]}
    assert set(scopes) == {"global", "risk_on", "neutral", "risk_off"}
    assert scopes["global"]["label"] == "human-global"
    assert scopes["risk_on"]["label"] == "human-global"   # inherited


# ---------- reverting ----------

def test_revert_returns_to_the_human_baseline_in_one_step(session: Session):
    """However many automatic steps have happened, one call undoes all of them."""
    _anchor(session)
    for i, quality in enumerate((30.0, 33.0, 34.0)):
        v = register(session, kind="WEIGHTS", label=f"auto-{i}",
                     params={**ANCHOR, "quality": quality})
        promote(session, v.id, "learner", automated=True)
    assert champion_weights(session).label == "auto-2"

    out = revert_to_anchor(session, "moreshwar")
    assert out["status"] == "OK"
    assert champion_weights(session).label == "human-global"


def test_reverting_when_already_at_the_anchor_is_a_noop(session: Session):
    _anchor(session)
    assert revert_to_anchor(session, "moreshwar")["status"] == "NOOP"


def test_revert_without_an_anchor_says_so(session: Session):
    assert revert_to_anchor(session, "moreshwar")["status"] == "NO_ANCHOR"


def test_a_regime_can_be_reverted_to_the_global_anchor(session: Session):
    """A regime with no anchor of its own still has something to fall back to."""
    _anchor(session)
    v = register(session, kind="WEIGHTS", scope="risk_on", label="auto-ro",
                 params={**ANCHOR, "momentum": 20.0})
    promote(session, v.id, "learner", automated=True)
    out = revert_to_anchor(session, "moreshwar", scope="risk_on")
    assert out["status"] == "OK"
    assert weights_for_regime(session, "RISK_ON").as_dict() == \
        WeightSet.from_dict(ANCHOR).normalised().as_dict()


# ---------- auto-rollback ----------

def test_auto_rollback_never_overrides_a_human_promotion(session: Session):
    """If you promoted it and it is losing, that is yours to reverse."""
    from app.services.circuit_breakers import auto_rollback_if_failing
    _seed_history(session, n=400, driver="quality")
    _anchor(session)
    out = auto_rollback_if_failing(session)
    assert out["reverted"] == []


def test_auto_rollback_reverts_a_failing_automatic_model(session: Session):
    from app.models import ConvictionHistory
    from app.services.circuit_breakers import auto_rollback_if_failing

    _anchor(session)
    auto = register(session, kind="WEIGHTS", label="auto-bad",
                    params={**ANCHOR, "quality": 30.0})
    promote(session, auto.id, "learner", automated=True)

    # Recent history where conviction ranks returns *backwards* — the score has
    # not merely gone quiet, it has inverted. Purely random data would sometimes
    # show a positive IC by chance and make this test flaky rather than strict.
    rng = random.Random(1)
    from app.models import Symbol
    syms = []
    for i in range(5):
        s = Symbol(ticker=f"R{i}", yahoo_symbol=f"R{i}.NS", name=f"R{i}",
                   exchange="NSE", active=True)
        session.add(s)
        syms.append(s)
    session.flush()
    base = date.today() - timedelta(days=5)
    for k in range(150):
        conviction = rng.uniform(20, 90)
        session.add(ConvictionHistory(
            symbol_id=syms[k % 5].id, as_of_date=base - timedelta(days=k // 5),
            conviction=round(conviction, 2), verdict="WATCH", close=100.0,
            fwd_return_10d=round(-(conviction - 55) / 10.0 + rng.gauss(0, 0.5), 4)))
    session.commit()

    out = auto_rollback_if_failing(session)
    assert out["reverted"], out
    assert champion_weights(session).label == "human-global"
