"""The pure scoring engine and the model registry.

These tests need no database for the engine itself — that is the point of the
refactor. If a test here required a session, the function would not be pure and
champion/challenger scoring would be impossible.
"""
from sqlalchemy.orm import Session

from app.scoring import LAYERS, ScoringInputs, WeightSet, score


def _inputs(**kw) -> ScoringInputs:
    base = {"ticker": "TCS", "name": "TCS Ltd", "close": 100.0,
            "regime_support": 1.0}
    base.update(kw)
    return ScoringInputs(**base)


# ---------- purity ----------

def test_engine_is_deterministic():
    """Same inputs, same score — always. No clock, no DB, no randomness."""
    i = _inputs(quality_score=70, news_score_out_of_10=6.0, rs_rank=80)
    a, b = score(i), score(i)
    assert a == b


def test_weights_are_injected_not_imported():
    """The same setup must score differently under a different weight set —
    otherwise champion/challenger is impossible."""
    i = _inputs(quality_score=95, news_score_out_of_10=2.0)
    quality_heavy = WeightSet(technical=10, quality=60, news=10, momentum=10,
                              ml=4, macro=3, regime=3, label="quality-heavy")
    news_heavy = WeightSet(technical=10, quality=10, news=60, momentum=10,
                           ml=4, macro=3, regime=3, label="news-heavy")
    assert score(i, quality_heavy).conviction > score(i, news_heavy).conviction


# ---------- invariants ----------

def test_conviction_and_confidence_stay_in_range():
    for kwargs in ({}, {"quality_score": 0, "news_score_out_of_10": 0.0, "rs_rank": 0},
                   {"quality_score": 100, "news_score_out_of_10": 10.0,
                    "rs_rank": 100, "ml_direction": "UP", "ml_accuracy": 90,
                    "macro_sentiment": "positive", "regime_code": "RISK_ON",
                    "signal_names": ("a", "b", "c")}):
        s = score(_inputs(**kwargs))
        assert 0 <= s.conviction <= 100
        assert 0 <= s.confidence <= 1
        assert 0 <= s.consensus <= 1


def test_all_neutral_inputs_land_near_fifty():
    """Knowing nothing must not read as bearish — absence of evidence is not
    evidence of weakness."""
    s = score(_inputs(posture_points=15.0))     # mid posture, everything else unknown
    assert 40 <= s.conviction <= 60


def test_monotonic_in_each_layer():
    """Raising any single layer, others fixed, can never lower conviction."""
    base = {"quality_score": 50, "news_score_out_of_10": 5.0, "rs_rank": 50,
            "posture_points": 15.0}
    low = score(_inputs(**base)).conviction
    for better in ({"quality_score": 90}, {"news_score_out_of_10": 9.0},
                   {"rs_rank": 95}, {"macro_sentiment": "positive"},
                   {"regime_code": "RISK_ON"},
                   {"ml_direction": "UP", "ml_accuracy": 80}):
        assert score(_inputs(**{**base, **better})).conviction >= low, better


def test_no_layer_can_exceed_its_weight():
    s = score(_inputs(quality_score=100, news_score_out_of_10=10.0, rs_rank=100,
                      signal_names=("a", "b", "c"), ml_direction="UP",
                      ml_accuracy=99, macro_sentiment="positive",
                      regime_code="RISK_ON"))
    for layer in s.layers:
        assert 0 <= layer.points <= layer.weight + 1e-9


def test_veto_forces_zero_size_whatever_the_score():
    s = score(_inputs(quality_score=100, news_score_out_of_10=10.0, rs_rank=100,
                      signal_names=("a",), news_veto=True))
    assert s.risk_multiplier == 0.0 and s.verdict == "VETOED"
    assert s.conviction > 50           # the score itself is untouched by the veto


def test_posture_never_outranks_a_real_signal():
    posture = score(_inputs(posture_points=30.0))          # best possible posture
    signal = score(_inputs(signal_names=("Golden Cross",)))
    tech = {layer.layer: layer.points for layer in posture.layers}["technical"]
    tech_sig = {layer.layer: layer.points for layer in signal.layers}["technical"]
    assert tech_sig > tech


# ---------- weight set ----------

def test_weights_normalise_to_one_hundred():
    w = WeightSet(technical=50, quality=50, news=50, momentum=50,
                  ml=50, macro=50, regime=50).normalised()
    assert abs(w.total - 100.0) < 0.01


def test_weightset_roundtrips_through_dict():
    w = WeightSet(version_id=7, label="v7")
    assert WeightSet.from_dict(w.as_dict(), version_id=7).as_dict() == w.as_dict()
    assert set(w.as_dict()) == set(LAYERS)


# ---------- registry ----------

def test_registry_falls_back_when_empty(session: Session):
    """A fresh database must still score rather than crash."""
    from app.services.model_registry import champion_weights
    w = champion_weights(session)
    assert abs(w.total - 100.0) < 0.01


def test_register_creates_shadow_not_champion(session: Session):
    from app.services.model_registry import get_champion, register
    v = register(session, kind="WEIGHTS", label="challenger-1",
                 params=WeightSet().as_dict(), created_by="tester")
    assert v.status == "SHADOW"
    assert get_champion(session, "WEIGHTS") is None    # promotion is separate


def test_promote_retires_the_incumbent_and_audits(session: Session):
    from app.models import ModelVersionAudit
    from app.services.model_registry import champion_weights, promote, register
    first = register(session, kind="WEIGHTS", label="v1",
                     params=WeightSet().as_dict())
    promote(session, first.id, "moreshwar", "initial")
    second = register(session, kind="WEIGHTS", label="v2",
                      params=WeightSet(quality=40, technical=10).as_dict())
    out = promote(session, second.id, "moreshwar", "better OOS IC")

    assert out["status"] == "OK" and out["retired"] == "v1"
    assert champion_weights(session).version_id == second.id
    actors = {a.actor for a in session.query(ModelVersionAudit).all()}
    assert actors == {"system", "moreshwar"}


def test_retired_versions_are_immutable(session: Session):
    from app.services.model_registry import promote, register
    a = register(session, kind="WEIGHTS", label="a", params=WeightSet().as_dict())
    b = register(session, kind="WEIGHTS", label="b", params=WeightSet().as_dict())
    promote(session, a.id, "u")
    promote(session, b.id, "u")                 # retires a
    assert promote(session, a.id, "u")["status"] == "REJECTED"


def test_rollback_restores_the_previous_champion(session: Session):
    from app.services.model_registry import (champion_weights, promote, register,
                                             rollback)
    a = register(session, kind="WEIGHTS", label="a", params=WeightSet().as_dict())
    b = register(session, kind="WEIGHTS", label="b",
                 params=WeightSet(quality=40, technical=10).as_dict())
    promote(session, a.id, "u")
    promote(session, b.id, "u")
    assert rollback(session, "u", "regret")["champion"] == "a"
    assert champion_weights(session).version_id == a.id


def test_champion_weights_are_normalised_before_use(session: Session):
    """A registered set that doesn't sum to 100 must not silently break the
    'conviction is a percentage' contract."""
    from app.services.model_registry import champion_weights, promote, register
    v = register(session, kind="WEIGHTS", label="unnormalised",
                 params={layer: 10.0 for layer in LAYERS})   # sums to 70
    promote(session, v.id, "u")
    assert abs(champion_weights(session).total - 100.0) < 0.01
