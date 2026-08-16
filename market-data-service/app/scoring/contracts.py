"""Typed contracts for the scoring engine.

Everything here is a frozen dataclass with no behaviour and no I/O. The point is
that a score becomes a *function of its declared inputs* rather than a function of
whatever the database happened to contain at the moment it ran.

That property is what makes three things possible, none of which work today:
  - champion/challenger: score the same inputs under two weight sets
  - honest backtests: replay a historical FeatureVector without a live DB
  - property testing: assert invariants without seeding a database
"""
from dataclasses import dataclass, field

#: The seven layers, in canonical order. Anything iterating layers uses this.
LAYERS = ("technical", "quality", "news", "momentum", "ml", "macro", "regime")


@dataclass(frozen=True)
class WeightSet:
    """Layer weights, injected rather than imported.

    `version_id` ties a score back to the registry row that produced it — without
    it, attribution silently breaks the first time weights change.
    """
    technical: float = 25.0
    quality: float = 25.0
    news: float = 18.0
    momentum: float = 14.0
    ml: float = 7.0
    macro: float = 6.0
    regime: float = 5.0
    version_id: int | None = None
    label: str = "default"

    def as_dict(self) -> dict:
        return {layer: getattr(self, layer) for layer in LAYERS}

    @property
    def total(self) -> float:
        return sum(self.as_dict().values())

    def normalised(self) -> "WeightSet":
        """Rescale to sum to 100 — conviction is only a percentage if they do."""
        total = self.total
        if total <= 0:
            return WeightSet(version_id=self.version_id, label=self.label)
        factor = 100.0 / total
        return WeightSet(**{layer: round(v * factor, 4)
                            for layer, v in self.as_dict().items()},
                         version_id=self.version_id, label=self.label)

    @classmethod
    def from_dict(cls, data: dict, version_id: int | None = None,
                  label: str = "custom") -> "WeightSet":
        return cls(**{layer: float(data.get(layer, 0.0)) for layer in LAYERS},
                   version_id=version_id, label=label)


@dataclass(frozen=True)
class ScoringInputs:
    """Everything the engine needs, already resolved. No session, no lookups.

    Assembled by the caller (which may read a DB or replay a historical
    FeatureVector) — the engine itself never learns where these came from.
    """
    ticker: str
    name: str = ""
    sector: str | None = None
    close: float | None = None

    # technical: either fired signals, or a posture read already computed
    signal_names: tuple = ()
    posture_points: float = 0.0          # 0..POSTURE_MAX
    posture_note: str = ""

    # the remaining layers, pre-resolved to their raw readings
    quality_score: float | None = None   # 0..100
    quality_grade: str | None = None
    news_score_out_of_10: float | None = None
    news_note: str = ""
    news_veto: bool = False
    news_sentiment: str | None = None
    rs_rank: float | None = None         # 0..100
    ml_direction: str | None = None      # UP | DOWN | FLAT
    ml_accuracy: float | None = None     # 0..100
    macro_sentiment: str | None = None
    regime_code: str | None = None
    regime_label: str = "unknown"

    # sizing / confidence context
    atr_pct: float | None = None
    regime_support: float = 0.5          # 0..1, from labelled history


@dataclass(frozen=True)
class LayerScore:
    layer: str
    strength: float
    weight: float
    points: float
    note: str
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Wire shape kept identical to the pre-refactor payload so the UI and
        the conviction recorder are unaffected."""
        return {"layer": self.layer, "points": self.points, "max": self.weight,
                "strength": self.strength, "note": self.note, **self.extra}


@dataclass(frozen=True)
class Score:
    """The complete, explainable result of one scoring run."""
    conviction: float
    confidence: float
    consensus: float
    dispersion: float
    verdict: str
    news_veto: bool
    risk_multiplier: float
    layers: tuple = ()
    conflicts: tuple = ()
    data_quality: float = 1.0
    vol_factor: float = 1.0
    regime_support: float = 0.5
    size_note: str = ""
    weights_version_id: int | None = None

    def layer_dicts(self) -> list:
        return [layer.to_dict() for layer in self.layers]
