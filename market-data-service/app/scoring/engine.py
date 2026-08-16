"""The scoring engine — a pure function from (inputs, weights) to a Score.

No database, no network, no clock, no imported weights. Every dependency arrives
as an argument, which is precisely what lets the same inputs be scored under a
challenger weight set, replayed from history, or property-tested without seeding
anything.

Behaviour is intentionally identical to the pre-refactor `_score_symbol`; the
existing Alpha Stack test suite acts as the characterisation test for that claim.
"""
from app.scoring.contracts import LAYERS, LayerScore, Score, ScoringInputs, WeightSet

# --- strength model: every layer reports 0..1 where 0.5 means neutral/unknown ---
NEUTRAL = 0.5
SIGNAL_STRENGTH = 0.85          # one fired ENTRY
EXTRA_STRATEGY = 0.075          # each additional agreeing strategy (max 2 counted)
POSTURE_CEILING = 0.70          # posture can never outrank a real signal
POSTURE_MAX = 30.0              # raw posture points, rescaled into the ceiling
REGIME_STRENGTH = {"RISK_ON": 1.0, "PULLBACK": 0.65, "CHOP": 0.35,
                   "BEAR_RALLY": 0.2, "RISK_OFF": 0.0}
MACRO_STRENGTH = {"positive": 1.0, "neutral": 0.5, "mixed": 0.35, "negative": 0.0}
MIN_ML_ACCURACY = 50.0

# --- confidence ---
DISPERSION_MAX = 0.35
CONFLICT_THRESHOLD = 0.30
CONFLICT_MIN_WEIGHT = 14.0
CONFIDENCE_FLOOR = 0.15
DQ_PENALTY = 0.85

# --- sizing ---
VOL_BASELINE_PCT = 2.5
VOL_FACTOR_FLOOR, VOL_FACTOR_CAP = 0.6, 1.4
RISK_MULT_CAP = 1.5


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _risk_multiplier(conviction: float) -> float:
    if conviction >= 75:
        return 1.5
    if conviction >= 55:
        return 1.0
    if conviction >= 40:
        return 0.5
    return 0.0


def _volatility_factor(atr_pct: float | None) -> float:
    """Inverse-vol tilt: two names at equal conviction shouldn't carry equal
    rupee risk if one is twice as volatile. 1.0 when vol is unknown."""
    if atr_pct is None or atr_pct <= 0:
        return 1.0
    return round(max(VOL_FACTOR_FLOOR,
                     min(VOL_FACTOR_CAP, VOL_BASELINE_PCT / atr_pct)), 3)


def _verdict(conviction: float, veto: bool) -> str:
    if veto:
        return "VETOED"
    if conviction >= 75:
        return "HIGH"
    if conviction >= 55:
        return "NORMAL"
    if conviction >= 40:
        return "SMALL"
    return "STAND_ASIDE"


def _technical(inputs: ScoringInputs) -> tuple:
    if inputs.signal_names:
        extra = min(len(inputs.signal_names) - 1, 2)
        strength = SIGNAL_STRENGTH + extra * EXTRA_STRATEGY
        note = ((f"{len(inputs.signal_names)} strategies agree: "
                 if len(inputs.signal_names) > 1 else "ENTRY fired: ")
                + ", ".join(inputs.signal_names))
        return strength, note
    return (inputs.posture_points / POSTURE_MAX) * POSTURE_CEILING, inputs.posture_note


def _consensus(layers: list) -> tuple:
    """Weighted dispersion of layer strengths → (consensus, dispersion).

    A mean hides whether it came from agreement or from a fight; this is what
    tells them apart.
    """
    total_w = sum(layer.weight for layer in layers)
    if not layers or total_w <= 0:
        return 1.0, 0.0
    mean = sum(layer.strength * layer.weight for layer in layers) / total_w
    variance = sum(layer.weight * (layer.strength - mean) ** 2
                   for layer in layers) / total_w
    dispersion = variance ** 0.5
    return round(max(0.0, 1.0 - min(1.0, dispersion / DISPERSION_MAX)), 3), \
        round(dispersion, 4)


def _conflicts(layers: list) -> tuple:
    """High-weight layers pulling hard against the consensus, named explicitly."""
    total_w = sum(layer.weight for layer in layers)
    if not layers or total_w <= 0:
        return ()
    mean = sum(layer.strength * layer.weight for layer in layers) / total_w
    bulls = [x for x in layers if x.weight >= CONFLICT_MIN_WEIGHT
             and x.strength - mean >= CONFLICT_THRESHOLD]
    bears = [x for x in layers if x.weight >= CONFLICT_MIN_WEIGHT
             and mean - x.strength >= CONFLICT_THRESHOLD]
    if not bulls or not bears:
        return ()                       # a one-sided outlier is not a conflict
    bull = max(bulls, key=lambda x: x.strength)
    bear = min(bears, key=lambda x: x.strength)
    return ({"bullish_layer": bull.layer, "bullish_strength": bull.strength,
             "bearish_layer": bear.layer, "bearish_strength": bear.strength,
             "note": (f"{bull.layer} is strong ({bull.strength:.2f}) while "
                      f"{bear.layer} is weak ({bear.strength:.2f}) — "
                      "the layers disagree")},)


def score(inputs: ScoringInputs, weights: WeightSet | None = None) -> Score:
    """Score one setup. Pure: same inputs always give the same Score."""
    w = (weights or WeightSet()).as_dict()
    layers: list = []

    def add(layer: str, strength: float, note: str, **extra) -> None:
        strength = _clamp01(strength)
        weight = w[layer]
        layers.append(LayerScore(layer=layer, strength=round(strength, 3),
                                 weight=weight, points=round(weight * strength, 1),
                                 note=note, extra=extra))

    tech_strength, tech_note = _technical(inputs)
    add("technical", tech_strength, tech_note)

    if inputs.quality_score is not None:
        add("quality", inputs.quality_score / 100.0,
            f"Business quality {inputs.quality_score}/100 "
            f"(grade {inputs.quality_grade})")
    else:
        add("quality", NEUTRAL,
            "No fundamentals stored — neutral (refresh them for a real read)")

    add("news",
        NEUTRAL if inputs.news_score_out_of_10 is None
        else inputs.news_score_out_of_10 / 10.0,
        inputs.news_note or "No news digest yet — neutral",
        score_out_of_10=inputs.news_score_out_of_10)

    if inputs.rs_rank is not None:
        add("momentum", inputs.rs_rank / 100.0,
            f"Relative strength {inputs.rs_rank:.0f}/100 vs the universe"
            + (" — a leader" if inputs.rs_rank >= 80
               else " — a laggard" if inputs.rs_rank <= 20 else ""))
    else:
        add("momentum", NEUTRAL, "Not enough universe data for an RS rank")

    ml_voted = (inputs.ml_accuracy is not None
                and inputs.ml_accuracy >= MIN_ML_ACCURACY
                and inputs.ml_direction in ("UP", "DOWN"))
    add("ml",
        (1.0 if inputs.ml_direction == "UP" else 0.0) if ml_voted else NEUTRAL,
        (f"Model says {inputs.ml_direction} ({inputs.ml_accuracy:.0f}% test accuracy)"
         if ml_voted else "Model neutral or below coin-flip — no vote"))

    add("macro", MACRO_STRENGTH.get(inputs.macro_sentiment or "", NEUTRAL),
        (f"Market-wide news tone reads {inputs.macro_sentiment}"
         if inputs.macro_sentiment else "No macro digest yet — refresh market news"))

    add("regime", REGIME_STRENGTH.get(inputs.regime_code or "", NEUTRAL),
        f"Market regime: {inputs.regime_label}")

    conviction = max(0.0, min(100.0, sum(layer.points for layer in layers)))

    # --- confidence: how sure we are, distinct from how good it looks ---
    consensus, dispersion = _consensus(layers)
    conflicts = _conflicts(layers)
    missing = []
    data_quality = 1.0
    if inputs.quality_score is None:
        data_quality *= DQ_PENALTY
        missing.append("fundamentals")
    if inputs.news_score_out_of_10 is None:
        data_quality *= DQ_PENALTY
        missing.append("news")
    data_quality = round(data_quality, 3)
    confidence = round(max(CONFIDENCE_FLOOR,
                           data_quality * consensus * inputs.regime_support), 3)

    # --- sizing ---
    vol_factor = _volatility_factor(inputs.atr_pct)
    base_mult = _risk_multiplier(conviction)
    mult = 0.0 if inputs.news_veto else round(
        min(RISK_MULT_CAP, base_mult * vol_factor * confidence), 2)

    bits = [f"{base_mult:g}× base"]
    if inputs.atr_pct is not None and vol_factor != 1.0:
        bits.append(f"vol ×{vol_factor:g} (ATR {inputs.atr_pct:g}%"
                    + (", calm" if vol_factor > 1 else ", volatile") + ")")
    bits.append(f"confidence ×{confidence:g}")
    if missing:
        bits.append(f"missing {', '.join(missing)}")
    if consensus < 0.6:
        bits.append(f"layers disagree (consensus {consensus:g})")
    size_note = (" · ".join(bits) + f" → {mult:g}× size") if base_mult else \
        "Conviction too low to size"

    return Score(
        conviction=round(conviction), confidence=confidence, consensus=consensus,
        dispersion=dispersion, verdict=_verdict(conviction, inputs.news_veto),
        news_veto=inputs.news_veto, risk_multiplier=mult, layers=tuple(layers),
        conflicts=conflicts, data_quality=data_quality, vol_factor=vol_factor,
        regime_support=inputs.regime_support, size_note=size_note,
        weights_version_id=(weights or WeightSet()).version_id)
