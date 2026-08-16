"""Hierarchical regime weights and the gated proposal pipeline.

The property that matters most here is that nothing gets promoted. A learner
that can promote itself is a learner that can lose money without anyone
agreeing to it, so `propose_weights` may only ever create SHADOW versions.
"""
import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.ai.calibration import LAYERS, learn_regime_weights, propose_weights

REGIMES = ("RISK_ON", "PULLBACK", "CHOP", "BEAR_RALLY", "RISK_OFF")


def _seed(session: Session, n: int = 400, *, signal_layer: str = "quality",
          seed: int = 7) -> None:
    """Synthetic labelled history where one layer genuinely predicts returns.

    The label is built from that layer plus noise, so a working learner should
    lift its weight; the others are pure noise and should not survive.
    """
    from app.models import ConvictionHistory, Symbol

    rng = random.Random(seed)
    symbols = []
    for i in range(20):
        s = Symbol(ticker=f"T{i:03d}", yahoo_symbol=f"T{i:03d}.NS",
                   name=f"Test {i}", exchange="NSE", sector="IT", active=True)
        session.add(s)
        symbols.append(s)
    session.flush()

    start = date(2024, 1, 1)
    for k in range(n):
        sym = symbols[k % len(symbols)]
        strengths = {layer: rng.random() for layer in LAYERS}
        label = (strengths[signal_layer] - 0.5) * 8.0 + rng.gauss(0, 1.5)
        session.add(ConvictionHistory(
            symbol_id=sym.id, as_of_date=start + timedelta(days=k),
            conviction=50.0, verdict="WATCH", news_veto=False,
            has_live_signal=False, close=100.0,
            regime_code=REGIMES[k % len(REGIMES)],
            fwd_return_10d=round(label, 4),
            **{f"{layer}_strength": round(v, 4) for layer, v in strengths.items()}))
    session.commit()


# ---------- hierarchical regime weights ----------

def test_regime_weights_collect_quietly_before_there_is_data(session: Session):
    out = learn_regime_weights(session)
    assert out["status"] == "COLLECTING" and out["n"] == 0


def test_regime_weights_always_sum_to_one_hundred(session: Session):
    _seed(session)
    out = learn_regime_weights(session)
    assert out["status"] == "OK"
    for bucket in out["buckets"]:
        total = sum(w["weight"] for w in bucket["weights"])
        assert abs(total - 100.0) < 0.5, bucket["bucket"]


def test_five_regimes_collapse_to_three_buckets(session: Session):
    """Five-way splits on a few hundred rows are noise wearing a label."""
    _seed(session)
    out = learn_regime_weights(session)
    assert {b["bucket"] for b in out["buckets"]} <= {"risk_on", "neutral", "risk_off"}


def test_shrinkage_keeps_thin_regimes_close_to_global(session: Session):
    """The whole point of partial pooling: little evidence, little drift."""
    _seed(session)
    out = learn_regime_weights(session)
    for bucket in out["buckets"]:
        drift = max(abs(w["drift"]) for w in bucket["weights"])
        # shrink = n/(n+200); with a few hundred rows per bucket the pull toward
        # the raw fit is partial by construction, so drift stays modest.
        assert drift < 25.0, (bucket["bucket"], bucket["shrink"], drift)
        assert 0.0 <= bucket["shrink"] <= 1.0


def test_bigger_buckets_are_allowed_to_drift_further(session: Session):
    _seed(session)
    out = learn_regime_weights(session)
    by_n = sorted(out["buckets"], key=lambda b: b["n"])
    assert by_n[0]["shrink"] <= by_n[-1]["shrink"]


# ---------- gated proposal ----------

def test_proposal_rejected_before_the_sample_is_large_enough(session: Session):
    out = propose_weights(session)
    assert out["status"] == "REJECTED"
    assert "sample_size" in out["failed"]
    assert "registered_version_id" not in out


def test_proposal_never_promotes_itself(session: Session):
    """Passing the gates earns the right to be watched, not to trade."""
    from app.models import ModelVersion
    from app.services.model_registry import get_champion

    _seed(session)
    out = propose_weights(session)
    assert get_champion(session, "WEIGHTS") is None
    for version in session.query(ModelVersion).all():
        assert version.status == "SHADOW"
    assert out["status"] in {"PASSED", "REJECTED"}


def test_a_passing_proposal_is_registered_as_shadow(session: Session):
    from app.models import ModelVersion

    _seed(session)
    out = propose_weights(session)
    if out["status"] != "PASSED":
        # A rejection is a legitimate outcome, but it must name its gate.
        assert out["failed"], out
        return
    version = session.get(ModelVersion, out["registered_version_id"])
    assert version.status == "SHADOW" and version.created_by == "learner"
    assert abs(sum(version.params_json.values()) - 100.0) < 0.5


def test_every_gate_is_reported_even_on_success(session: Session):
    """A proposal that only shows failures is not auditable."""
    _seed(session)
    out = propose_weights(session)
    names = {g["gate"] for g in out["gates"]}
    assert "sample_size" in names
    assert all("reason" in g and g["reason"] for g in out["gates"])


def test_register_shadow_false_leaves_the_registry_untouched(session: Session):
    from app.models import ModelVersion

    _seed(session)
    propose_weights(session, register_shadow=False)
    assert session.query(ModelVersion).count() == 0


def test_the_predictive_layer_gains_weight(session: Session):
    """Sanity check that the learner learns: the layer that actually drives the
    label should end up weighted above its noise-only peers."""
    _seed(session, n=600, signal_layer="quality")
    out = propose_weights(session, register_shadow=False)
    candidate = out.get("candidate")
    assert candidate is not None
    assert candidate["quality"] > candidate["macro"]
