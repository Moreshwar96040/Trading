"""Tier-1 reasoning: explanations DERIVED from the arithmetic, never invented.

The distinction this module enforces is the difference between an explanation and
a rationalisation. Handing a score to an LLM and asking "why?" produces fluent,
confident prose that describes reasoning the system never did — unfalsifiable and
actively harmful in a trading context.

So the rationale is computed from the same numbers that produced the score:
contributions, dispersion, conflicts, confidence terms, the veto. It is free,
instant, reproducible, and it cannot say anything the arithmetic does not support.

Tier 2 (optional LLM prose) takes THIS object as its input and may not introduce
a layer that is not present here — that constraint is what keeps the narration
honest.
"""
from dataclasses import asdict, dataclass, field

LAYER_LABEL = {
    "technical": "technical timing",
    "quality": "business quality",
    "news": "news sentiment",
    "momentum": "relative strength",
    "ml": "the ML model",
    "macro": "market-wide news",
    "regime": "the market regime",
}

#: A layer must move the needle by at least this many points to be worth naming.
MATERIAL_POINTS = 1.5


@dataclass(frozen=True)
class Rationale:
    """Structured, machine-checkable explanation of one score."""
    headline: str
    verdict: str
    conviction: float
    confidence: float
    drivers: list = field(default_factory=list)
    detractors: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    confidence_notes: list = field(default_factory=list)
    veto_reason: str | None = None
    action_hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _contribution(layer: dict) -> float:
    """Points above (or below) a neutral 0.5 reading — the layer's real influence.

    Using raw points would rank every layer by its weight rather than by what it
    actually said; a neutral 25-point layer contributes 12.5 points but zero
    information.
    """
    strength = layer.get("strength")
    if strength is None:
        return 0.0
    return (strength - 0.5) * layer.get("max", 0.0)


def _phrase(layer: dict, positive: bool) -> str:
    label = LAYER_LABEL.get(layer["layer"], layer["layer"])
    delta = abs(_contribution(layer))
    direction = "adds" if positive else "costs"
    return f"{label} {direction} {delta:.1f} pts ({layer['points']:g}/{layer['max']:g})"


def build_rationale(setup: dict) -> Rationale:
    """Turn a scored setup into a structured explanation. Pure — no I/O, no clock."""
    breakdown = setup.get("breakdown") or []
    conviction = float(setup.get("conviction", 0))
    confidence = float(setup.get("confidence", 1.0))
    verdict = setup.get("verdict", "")
    ticker = setup.get("ticker", "This stock")

    ranked = sorted(breakdown, key=_contribution, reverse=True)
    drivers = [_phrase(b, True) for b in ranked
               if _contribution(b) >= MATERIAL_POINTS][:2]
    detractors = [_phrase(b, False) for b in reversed(ranked)
                  if _contribution(b) <= -MATERIAL_POINTS][:2]

    conflicts = [c.get("note", "") for c in setup.get("conflicts") or []]

    # --- why confidence is where it is ---
    notes = []
    consensus = setup.get("consensus")
    if consensus is not None and consensus < 0.6:
        notes.append(f"layers disagree (consensus {consensus:g})")
    data_quality = setup.get("data_quality")
    if data_quality is not None and data_quality < 1.0:
        notes.append(f"incomplete inputs (data {data_quality:g})")
    support = setup.get("regime_support")
    if support is not None and support < 0.4:
        notes.append(f"little history in this regime (support {support:g})")

    # --- veto is stated plainly and separately: it overrides the score ---
    veto_reason = None
    if setup.get("news_veto"):
        news_layer = next((b for b in breakdown if b["layer"] == "news"), None)
        veto_reason = (news_layer or {}).get("note") or "negative news"

    # --- headline: the one sentence a human reads first ---
    if veto_reason:
        headline = (f"{ticker} is blocked by the news gate despite scoring "
                    f"{conviction:.0f}/100.")
    elif conflicts:
        headline = (f"{ticker} scores {conviction:.0f}/100 but the layers conflict — "
                    f"confidence {confidence:.2f}.")
    elif confidence < 0.5:
        headline = (f"{ticker} scores {conviction:.0f}/100 on thin evidence "
                    f"(confidence {confidence:.2f}).")
    elif drivers:
        headline = (f"{ticker} scores {conviction:.0f}/100, led by "
                    f"{LAYER_LABEL.get(ranked[0]['layer'], ranked[0]['layer'])}.")
    else:
        headline = f"{ticker} scores {conviction:.0f}/100 with no standout layer."

    # --- action hint: separates "good but unproven" from "modest but solid" ---
    if veto_reason:
        hint = "Do not open. The news gate overrides the score."
    elif conviction >= 75 and confidence >= 0.7:
        hint = "Strong and well evidenced — size up within your risk rules."
    elif conviction >= 75:
        hint = "Attractive but poorly evidenced — size below what the score suggests."
    elif conviction >= 55 and confidence >= 0.7:
        hint = "Solid and well evidenced — a normal-sized position."
    elif conviction >= 55:
        hint = "Borderline. The score is adequate but the evidence is not."
    else:
        hint = "Below the bar — stand aside."

    return Rationale(headline=headline, verdict=verdict, conviction=conviction,
                     confidence=confidence, drivers=drivers, detractors=detractors,
                     conflicts=conflicts, confidence_notes=notes,
                     veto_reason=veto_reason, action_hint=hint)
