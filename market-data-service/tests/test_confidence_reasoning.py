"""Confidence, consensus, conflict detection and the Tier-1 rationale.

The central claim being tested: conviction and confidence are DIFFERENT things.
Two setups can score identically and deserve different sizing because one is
well-evidenced and the other is a coin-flip dressed as an average.
"""
from app.ai.reasoning import build_rationale
from app.services.conviction_service import (CONFIDENCE_FLOOR, LAYER_WEIGHTS,
                                             _conflicts, _consensus)


def _bd(**strengths) -> list[dict]:
    """Breakdown rows with explicit per-layer strengths (default neutral)."""
    out = []
    for layer, weight in LAYER_WEIGHTS.items():
        s = strengths.get(layer, 0.5)
        out.append({"layer": layer, "strength": s, "max": weight,
                    "points": round(weight * s, 1), "note": ""})
    return out


# ---------- consensus ----------

def test_unanimous_layers_give_full_consensus():
    consensus, dispersion = _consensus(_bd(**{k: 0.7 for k in LAYER_WEIGHTS}))
    assert consensus == 1.0 and dispersion == 0.0


def test_split_layers_collapse_consensus():
    """Half the layers scream buy, half scream sell. The mean looks moderate —
    consensus must reveal that it is an average of a fight."""
    split = {"technical": 1.0, "quality": 1.0, "news": 0.0,
             "momentum": 0.0, "ml": 1.0, "macro": 0.0, "regime": 1.0}
    consensus, dispersion = _consensus(_bd(**split))
    assert consensus < 0.1 and dispersion > 0.3


def test_mild_spread_gives_partial_consensus():
    consensus, _ = _consensus(_bd(technical=0.65, quality=0.55, news=0.45))
    assert 0.5 < consensus < 1.0


# ---------- conflict detection ----------

def test_conflict_named_when_high_weight_layers_oppose():
    """The quality-trap case: fundamentals strong, news falling apart."""
    conflicts = _conflicts(_bd(quality=0.95, technical=0.9, news=0.05, momentum=0.1))
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["bullish_layer"] in {"quality", "technical"}
    assert c["bearish_layer"] in {"news", "momentum"}
    assert "disagree" in c["note"]


def test_one_sided_outlier_is_not_a_conflict():
    """Everything strong with one merely-average layer is agreement, not conflict."""
    assert _conflicts(_bd(technical=0.9, quality=0.85, news=0.8, momentum=0.55)) == []


def test_low_weight_layers_cannot_raise_a_conflict():
    """A disagreeing 5-point regime layer is noise, not a warning."""
    assert _conflicts(_bd(technical=0.9, quality=0.9, news=0.85, regime=0.0)) == []


# ---------- rationale ----------

def _setup(**kw) -> dict:
    base = {"ticker": "TCS", "conviction": 70.0, "confidence": 0.8, "verdict": "NORMAL",
            "consensus": 0.9, "data_quality": 1.0, "regime_support": 0.8,
            "news_veto": False, "conflicts": [], "breakdown": _bd()}
    base.update(kw)
    return base


def test_rationale_names_the_biggest_driver():
    r = build_rationale(_setup(breakdown=_bd(quality=1.0, technical=0.95)))
    assert r.drivers
    assert any("business quality" in d or "technical timing" in d for d in r.drivers)


def test_rationale_names_detractors_separately():
    r = build_rationale(_setup(breakdown=_bd(news=0.0, momentum=0.05)))
    assert r.detractors
    assert any("news sentiment" in d for d in r.detractors)


def test_neutral_layers_are_not_reported_as_drivers():
    """A neutral 25-point layer contributes points but zero information — naming
    it would make every explanation say 'technical timing' regardless."""
    r = build_rationale(_setup(breakdown=_bd()))
    assert r.drivers == [] and r.detractors == []


def test_veto_dominates_the_headline_and_action():
    r = build_rationale(_setup(conviction=88.0, news_veto=True,
                               breakdown=_bd(news=0.0, quality=0.95)))
    assert r.veto_reason is not None
    assert "blocked" in r.headline
    assert "Do not open" in r.action_hint


def test_high_conviction_low_confidence_is_called_out():
    """The exact case the old single score could not express."""
    r = build_rationale(_setup(conviction=82.0, confidence=0.3, consensus=0.4,
                               data_quality=0.72, regime_support=0.2))
    assert "size below what the score suggests" in r.action_hint
    assert any("disagree" in n for n in r.confidence_notes)
    assert any("incomplete" in n for n in r.confidence_notes)
    assert any("regime" in n for n in r.confidence_notes)


def test_modest_but_well_evidenced_reads_as_normal():
    r = build_rationale(_setup(conviction=60.0, confidence=0.85))
    assert "normal-sized" in r.action_hint


def test_below_bar_stands_aside():
    assert "stand aside" in build_rationale(_setup(conviction=25.0)).action_hint


def test_conflict_appears_in_headline():
    r = build_rationale(_setup(conflicts=[{"note": "quality strong while news is weak"}]))
    assert "conflict" in r.headline and r.conflicts


def test_rationale_is_serialisable_and_immutable():
    import dataclasses
    r = build_rationale(_setup())
    assert isinstance(r.to_dict(), dict) and r.to_dict()["headline"]
    try:
        r.headline = "x"
        raise AssertionError("Rationale should be frozen")
    except dataclasses.FrozenInstanceError:
        pass


# ---------- the invariant that matters most ----------

def test_confidence_never_zeroes_a_position_only_the_veto_does():
    """Uncertainty shrinks size; it must not silently become a veto. Zeroing is
    the news gate's job, and it should be the only thing that does it."""
    assert CONFIDENCE_FLOOR > 0
    worst = _bd(technical=1.0, quality=0.0, news=1.0, momentum=0.0,
                ml=1.0, macro=0.0, regime=1.0)
    consensus, _ = _consensus(worst)
    confidence = max(CONFIDENCE_FLOOR, 0.72 * consensus * 0.1)
    assert confidence >= CONFIDENCE_FLOOR
