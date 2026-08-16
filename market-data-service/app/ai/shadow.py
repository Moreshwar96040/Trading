"""Shadow evaluation — how would a challenger have scored, on history we already have?

The obvious implementation is a second daily job that scores every symbol under
the shadow weights and writes the result to a new table. We don't do that, and
the reason is worth stating because it saves a schema, a scheduler entry and a
year of waiting:

    conviction is a *linear* function of the layer strengths, and the strengths
    are already persisted in conviction_history.

So a shadow conviction is just Σ(w_shadow × strength) — pure arithmetic over rows
we recorded anyway. That has three consequences, all good:

  * no new table, no new job, nothing extra to keep alive;
  * a challenger registered today can be evaluated on every day of history we
    hold, instead of only on days after it was registered;
  * champion and challenger are compared on *identical* inputs, so any
    difference is attributable to the weights alone — which is the entire point.

The limit, stated plainly: this only works for challengers that change weights.
A challenger that changes how a *layer* is computed produces different
strengths, and those cannot be reconstructed from stored rows — that needs
genuine forward shadow recording. `evaluate_candidate` therefore refuses
anything but a WEIGHTS version rather than quietly returning a wrong number.
"""
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ai.calibration import LAYERS, _load_frame, _spearman
from app.scoring import WeightSet

log = logging.getLogger(__name__)

#: Below this the comparison is entertainment, not evidence.
MIN_SAMPLES = 200
#: Bands used to check that a higher score really does earn more.
BANDS = ((75, 101, "75+"), (55, 75, "55-74"), (40, 55, "40-54"), (0, 40, "<40"))
#: How much better the challenger must be before we call it a win rather than noise.
MEANINGFUL_IC_GAIN = 0.01


@dataclass(frozen=True)
class Comparison:
    n: int
    champion_ic: float | None
    candidate_ic: float | None
    ic_gain: float | None
    rank_agreement: float | None
    champion_bands: list
    candidate_bands: list
    verdict: str
    note: str

    def to_dict(self) -> dict:
        return {"n": self.n, "champion_ic": self.champion_ic,
                "candidate_ic": self.candidate_ic, "ic_gain": self.ic_gain,
                "rank_agreement": self.rank_agreement,
                "champion_bands": self.champion_bands,
                "candidate_bands": self.candidate_bands,
                "verdict": self.verdict, "note": self.note}


def _conviction(row, weights: dict) -> float | None:
    """Replay the weighted sum. Any missing strength makes the row unusable —
    imputing a neutral 0.5 here would flatter whichever weight set leans on the
    missing layer, which is exactly the bias we are trying to detect."""
    total = 0.0
    for layer in LAYERS:
        strength = row.get(f"{layer}_strength")
        if strength is None or strength != strength:      # NaN-safe
            return None
        total += weights[layer] * float(strength)
    return total


def _bands(scores: list, labels: list) -> list:
    out = []
    for low, high, name in BANDS:
        picked = [ret for score, ret in zip(scores, labels) if low <= score < high]
        if not picked:
            out.append({"band": name, "n": 0, "avg_return": None, "hit_rate": None})
            continue
        wins = sum(1 for r in picked if r > 0)
        out.append({"band": name, "n": len(picked),
                    "avg_return": round(sum(picked) / len(picked), 3),
                    "hit_rate": round(wins / len(picked) * 100, 1)})
    return out


def _rank_agreement(a: list, b: list) -> float | None:
    import pandas as pd
    ic = _spearman(pd.Series(a), pd.Series(b))
    return None if ic is None or ic != ic else round(float(ic), 4)


def compare_weight_sets(session: Session, champion: WeightSet, candidate: WeightSet,
                        horizon: str = "fwd_return_10d") -> Comparison:
    """Replay both weight sets over the same labelled history."""
    import pandas as pd

    frame = _load_frame(session, horizon)
    if frame.empty:
        return Comparison(0, None, None, None, None, [], [], "NO_DATA",
                          "No labelled history yet — nothing to replay.")

    champ_w, cand_w = champion.as_dict(), candidate.as_dict()
    champ_scores, cand_scores, labels = [], [], []
    for _, raw in frame.iterrows():
        row = raw.to_dict()
        label = row.get("label")
        if label is None or label != label:
            continue
        c = _conviction(row, champ_w)
        k = _conviction(row, cand_w)
        if c is None or k is None:
            continue                       # incomplete row — excluded from BOTH sides
        champ_scores.append(c)
        cand_scores.append(k)
        labels.append(float(label))

    n = len(labels)
    if n < MIN_SAMPLES:
        return Comparison(n, None, None, None, None, [], [], "INSUFFICIENT",
                          f"{n} comparable rows — need {MIN_SAMPLES} before a "
                          "difference in IC means anything.")

    champ_ic = _rank_agreement(champ_scores, labels)
    cand_ic = _rank_agreement(cand_scores, labels)
    agreement = _rank_agreement(champ_scores, cand_scores)
    gain = (None if champ_ic is None or cand_ic is None
            else round(cand_ic - champ_ic, 4))

    if gain is None:
        verdict, note = "UNCLEAR", "Could not compute IC for one of the two sets."
    elif gain > MEANINGFUL_IC_GAIN:
        verdict = "CHALLENGER_AHEAD"
        note = (f"Challenger ranks history {gain:+.4f} IC better on {n} setups. "
                "Worth promoting only if it also passed the validation gates.")
    elif gain < -MEANINGFUL_IC_GAIN:
        verdict = "CHAMPION_AHEAD"
        note = f"Champion is still better by {abs(gain):.4f} IC. Keep it."
    else:
        verdict = "TIE"
        note = ("The two rank history almost identically — the change is not worth "
                "the turnover it would cost.")

    return Comparison(n, champ_ic, cand_ic, gain, agreement,
                      _bands(champ_scores, labels), _bands(cand_scores, labels),
                      verdict, note)


def evaluate_candidate(session: Session, version_id: int,
                       horizon: str = "fwd_return_10d") -> dict:
    """Compare one registered version against the live champion."""
    from app.models import ModelVersion
    from app.services.model_registry import champion_weights, get_champion

    version = session.get(ModelVersion, version_id)
    if version is None:
        return {"status": "NOT_FOUND", "version_id": version_id}
    if version.kind != "WEIGHTS":
        return {"status": "UNSUPPORTED", "version_id": version_id,
                "note": ("Only weight changes can be replayed on stored history. "
                         f"'{version.kind}' changes how strengths are computed, so "
                         "it needs forward shadow recording, not a replay.")}

    champion = get_champion(session)
    if champion is not None and champion.id == version_id:
        return {"status": "IS_CHAMPION", "version_id": version_id,
                "note": "This version is already live — nothing to compare it to."}

    candidate = WeightSet.from_dict(version.params_json, version_id=version.id,
                                    label=version.label).normalised()
    comparison = compare_weight_sets(session, champion_weights(session), candidate,
                                     horizon=horizon)
    return {"status": "OK", "version_id": version.id, "label": version.label,
            "version_status": version.status, "horizon": horizon,
            "champion_label": champion.label if champion is not None else "baseline",
            "candidate_weights": candidate.as_dict(),
            **comparison.to_dict()}


def shadow_board(session: Session, horizon: str = "fwd_return_10d") -> dict:
    """Every shadow version, replayed and ranked — the promotion decision screen."""
    from app.models import ModelVersion
    from app.services.model_registry import get_champion

    shadows = session.query(ModelVersion).filter(
        ModelVersion.kind == "WEIGHTS",
        ModelVersion.status == "SHADOW").order_by(ModelVersion.id.desc()).all()
    champion = get_champion(session)
    rows = [evaluate_candidate(session, v.id, horizon=horizon) for v in shadows]
    ahead = [r for r in rows if r.get("verdict") == "CHALLENGER_AHEAD"]
    return {"champion": {"id": champion.id, "label": champion.label}
                        if champion is not None else None,
            "horizon": horizon, "shadows": rows,
            "promotable": len(ahead),
            "note": ("Being ahead here is necessary but not sufficient — promotion "
                     "is a human decision, and it is reversible.")}
