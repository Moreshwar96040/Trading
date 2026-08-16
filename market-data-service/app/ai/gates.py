"""Validation gates — what a candidate weight set must survive to become a challenger.

Fitting weights is easy; knowing whether the fit is real is the hard part, and it
is where a learning system either earns its keep or quietly destroys capital. Each
gate below blocks one specific way of fooling yourself:

    SAMPLE_SIZE   seven weights fitted on a hundred rows is noise with a label
    OOS_IC        an in-sample improvement that does not survive walk-forward
                  validation is curve-fitting, not learning
    TURNOVER      weights that reshuffle the whole ranking for a sliver of IC
                  cost more in spreads and slippage than the edge is worth
    SIGN_FLIP     a layer's coefficient reversing sign on thin data is almost
                  always noise — and acting on it means trading the opposite of
                  a thesis you had good reason to hold
    STABILITY     if resampling the same data gives materially different weights,
                  the fit is describing this particular sample, not the market

Every gate is a pure function returning a verdict with a human-readable reason,
so a rejection can always be explained rather than just reported.
"""
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

MIN_SAMPLES = 200
#: Below this, a coefficient reversing sign is treated as noise, not a finding.
SIGN_FLIP_MIN_SAMPLES = 500
#: Ranking churn above this needs a proportionate IC gain to justify itself.
MAX_TURNOVER = 0.30
MIN_IC_GAIN_FOR_CHURN = 0.10
#: Bootstrap: a weight varying more than this across resamples is unstable.
MAX_WEIGHT_CV = 0.20
#: ...but only if it moves a material number of points. A 5-point layer wobbling
#: by 2 points has a 40% CV and changes almost nothing about the ranking, whereas
#: a 25-point layer moving 2 points is genuinely steady. Judging on the ratio
#: alone would let the smallest, noisiest layer veto every promotion — which is
#: not caution, it is paralysis wearing caution's clothes.
MIN_MATERIAL_SD = 4.0
BOOTSTRAP_ROUNDS = 100


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    reason: str
    detail: dict | None = None

    def to_dict(self) -> dict:
        return {"gate": self.name, "passed": self.passed, "reason": self.reason,
                **({"detail": self.detail} if self.detail else {})}


def gate_sample_size(n: int, minimum: int = MIN_SAMPLES) -> GateResult:
    ok = n >= minimum
    return GateResult("sample_size", ok,
                      f"{n} labelled setups"
                      + ("" if ok else f" — need {minimum} before seven weights "
                                       "can be fitted to anything but noise"))


def gate_oos_improves(candidate_ic: float | None,
                      champion_ic: float | None) -> GateResult:
    """The candidate must beat the incumbent out-of-sample, on the same folds."""
    if candidate_ic is None:
        return GateResult("oos_ic", False,
                          "no out-of-sample IC could be computed (too few folds)")
    if champion_ic is None:
        return GateResult("oos_ic", candidate_ic > 0,
                          f"candidate OOS IC {candidate_ic:+.4f}; no champion "
                          "baseline recorded yet",
                          {"candidate": candidate_ic})
    ok = candidate_ic > champion_ic
    return GateResult("oos_ic", ok,
                      f"candidate {candidate_ic:+.4f} vs champion {champion_ic:+.4f}"
                      + ("" if ok else " — no out-of-sample improvement"),
                      {"candidate": candidate_ic, "champion": champion_ic})


def _rank(values: list) -> list:
    """Ordinal ranks (ties share the average rank) — no scipy needed."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _rank_correlation(a: list, b: list) -> float | None:
    ra, rb = _rank(a), _rank(b)
    n = len(ra)
    if n < 3:
        return None
    mean_a, mean_b = sum(ra) / n, sum(rb) / n
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb))
    den = (sum((x - mean_a) ** 2 for x in ra) ** 0.5
           * sum((y - mean_b) ** 2 for y in rb) ** 0.5)
    return None if den == 0 else num / den


def gate_turnover(current_scores: list, candidate_scores: list,
                  ic_gain: float) -> GateResult:
    """Churn must be paid for. Reordering the whole book for a sliver of IC
    hands the difference to the spread."""
    corr = _rank_correlation(current_scores, candidate_scores)
    if corr is None:
        return GateResult("turnover", True, "too few names to measure churn")
    turnover = round(1.0 - corr, 4)
    ok = turnover <= MAX_TURNOVER or ic_gain >= MIN_IC_GAIN_FOR_CHURN
    return GateResult("turnover", ok,
                      f"{turnover:.0%} ranking churn for {ic_gain:+.4f} IC gain"
                      + ("" if ok else " — too much churn for too little edge"),
                      {"turnover": turnover, "ic_gain": ic_gain})


def gate_no_sign_flip(current: dict, candidate: dict, n: int) -> GateResult:
    """A layer flipping from helping to hurting is a big claim; demand big data."""
    flips = [layer for layer in current
             if current.get(layer, 0) > 0 and candidate.get(layer, 0) <= 0]
    if not flips:
        return GateResult("sign_flip", True, "no layer reversed direction")
    ok = n >= SIGN_FLIP_MIN_SAMPLES
    return GateResult("sign_flip", ok,
                      f"{', '.join(flips)} reversed direction on {n} samples"
                      + ("" if ok else f" — needs {SIGN_FLIP_MIN_SAMPLES}+ to be "
                                       "believable"),
                      {"flipped": flips})


def gate_stability(bootstrap_weights: list,
                   max_cv: float = MAX_WEIGHT_CV,
                   min_sd: float = MIN_MATERIAL_SD) -> GateResult:
    """Resample the same data; the fit should barely move. If it lurches, it is
    describing this sample rather than the market.

    A layer counts as unstable only when it is *both* proportionally erratic and
    moving a material number of weight points. Either test alone gives the wrong
    answer: the ratio alone condemns every small layer, and the absolute figure
    alone excuses a large one drifting steadily.
    """
    if len(bootstrap_weights) < 10:
        return GateResult("stability", True, "not enough resamples to judge")

    unstable, worst_layer, worst_sd, worst_cv = [], None, 0.0, 0.0
    for layer in bootstrap_weights[0]:
        values = [w[layer] for w in bootstrap_weights]
        mean = sum(values) / len(values)
        sd = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
        cv = sd / mean if mean > 0.5 else 0.0
        if sd > worst_sd:
            worst_layer, worst_sd, worst_cv = layer, sd, cv
        if cv > max_cv and sd > min_sd:
            unstable.append(f"{layer} ±{sd:.1f}pts ({cv:.0%})")

    ok = not unstable
    return GateResult("stability", ok,
                      (f"most variable layer {worst_layer} moves ±{worst_sd:.1f} "
                       f"points across {len(bootstrap_weights)} resamples"
                       if ok else
                       f"the fit is not stable: {', '.join(unstable)}"),
                      {"worst_layer": worst_layer, "sd": round(worst_sd, 3),
                       "cv": round(worst_cv, 4), "unstable": unstable})


# --- Autonomy bounds (V23) --------------------------------------------------
#: Maximum a single layer may move from the human-approved anchor, in points.
MAX_LAYER_DRIFT = 10.0
#: No layer may be switched off entirely by an automatic change. A layer falling
#: to zero is a change of thesis, and a change of thesis needs a person.
MIN_LAYER_WEIGHT = 2.0

#: Parameters the learner may never touch. The news veto is a *safety rule*, not
#: a weight: it exists to keep us out of names with something badly wrong, and
#: its value comes precisely from not being negotiable when the data has a good
#: quarter. `_veto_audit` still reports whether it is costing us — but reporting
#: is a human's input, not the learner's lever.
FROZEN_PARAMS = frozenset({"news_veto", "news_veto_threshold", "veto",
                           "veto_threshold", "min_conviction", "risk_mult_cap"})


def gate_drift_bounded(anchor: dict, candidate: dict,
                       max_drift: float = MAX_LAYER_DRIFT,
                       min_weight: float = MIN_LAYER_WEIGHT) -> GateResult:
    """Keep an automatic change recognisably the model a human approved.

    Measured against the anchor rather than the incumbent, deliberately. Against
    the incumbent, drift ratchets: every automatic step passes a 10-point bound
    while the accumulated distance from anything anyone reviewed grows without
    limit. Against the anchor, the total is what is bounded.

    Exceeding the bound is not an error — it registers as a shadow and waits for
    a person. The learner is allowed to *want* a big change; it just cannot make
    one by itself.
    """
    breaches, drifts = [], {}
    for layer, anchor_weight in anchor.items():
        new = candidate.get(layer)
        if new is None:
            continue
        drift = new - anchor_weight
        drifts[layer] = round(drift, 2)
        if abs(drift) > max_drift:
            breaches.append(f"{layer} {drift:+.1f}")
        elif new < min_weight:
            breaches.append(f"{layer} down to {new:.1f}")

    worst = max((abs(d) for d in drifts.values()), default=0.0)
    ok = not breaches
    return GateResult("drift_bounded", ok,
                      (f"largest move {worst:.1f} points from the approved baseline"
                       if ok else
                       f"exceeds the autonomy bound: {', '.join(breaches)} "
                       f"(limit {max_drift:.0f} points, floor {min_weight:.0f})"),
                      {"max_drift": round(worst, 2), "drifts": drifts,
                       "limit": max_drift, "breaches": breaches})


def gate_frozen_params_untouched(candidate: dict) -> GateResult:
    """A candidate may only contain layer weights — never a safety parameter.

    This is a structural check rather than a statistical one: if a future change
    ever routes a veto threshold through the learner, this fails loudly instead
    of letting a safety rule quietly become a fitted parameter.
    """
    touched = sorted(set(candidate) & FROZEN_PARAMS)
    return GateResult("frozen_params", not touched,
                      "no safety parameter in the candidate" if not touched else
                      f"candidate tries to change frozen safety rules: "
                      f"{', '.join(touched)}",
                      {"touched": touched} if touched else None)


def evaluate_all(gates: list) -> dict:
    """Combine gate verdicts. A candidate passes only if every gate passes."""
    passed = all(g.passed for g in gates)
    failed = [g.name for g in gates if not g.passed]
    return {"passed": passed, "failed": failed,
            "gates": [g.to_dict() for g in gates],
            "summary": ("all gates passed — safe to register as a challenger"
                        if passed else f"rejected: failed {', '.join(failed)}")}
