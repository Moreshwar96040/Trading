"""Shadow evaluation — replaying a challenger over history we already recorded."""
import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.ai.shadow import (compare_weight_sets, evaluate_candidate, shadow_board)
from app.scoring import LAYERS, WeightSet

QUALITY_HEAVY = WeightSet(technical=10, quality=60, news=10, momentum=10,
                          ml=4, macro=3, regime=3, label="quality-heavy")


def _seed(session: Session, n: int = 400, *, driver: str = "quality",
          seed: int = 11) -> None:
    """History where one layer alone explains the forward return."""
    from app.models import ConvictionHistory, Symbol

    rng = random.Random(seed)
    symbols = []
    for i in range(20):
        s = Symbol(ticker=f"S{i:03d}", yahoo_symbol=f"S{i:03d}.NS",
                   name=f"S{i}", exchange="NSE", active=True)
        session.add(s)
        symbols.append(s)
    session.flush()

    start = date(2024, 1, 1)
    for k in range(n):
        strengths = {layer: rng.random() for layer in LAYERS}
        label = (strengths[driver] - 0.5) * 10.0 + rng.gauss(0, 1.0)
        session.add(ConvictionHistory(
            symbol_id=symbols[k % len(symbols)].id,
            as_of_date=start + timedelta(days=k // len(symbols)),
            conviction=50.0, verdict="WATCH", close=100.0,
            fwd_return_10d=round(label, 4),
            **{f"{layer}_strength": round(v, 4) for layer, v in strengths.items()}))
        session.flush()
    session.commit()


# ---------- replay mechanics ----------

def test_nothing_to_replay_is_said_plainly(session: Session):
    c = compare_weight_sets(session, WeightSet(), QUALITY_HEAVY)
    assert c.verdict == "NO_DATA" and c.n == 0


def test_a_thin_history_refuses_to_call_a_winner(session: Session):
    _seed(session, n=50)
    c = compare_weight_sets(session, WeightSet(), QUALITY_HEAVY)
    assert c.verdict == "INSUFFICIENT"


def test_the_weight_set_that_matches_reality_wins(session: Session):
    """Quality drives the label, so quality-heavy weights must rank better."""
    _seed(session, driver="quality")
    c = compare_weight_sets(session, WeightSet(), QUALITY_HEAVY)
    assert c.verdict == "CHALLENGER_AHEAD"
    assert c.candidate_ic > c.champion_ic


def test_the_champion_wins_when_the_challenger_is_wrong(session: Session):
    """Same data, a challenger that leans on a layer with no signal."""
    _seed(session, driver="quality")
    macro_heavy = WeightSet(technical=5, quality=5, news=5, momentum=5,
                            ml=5, macro=70, regime=5, label="macro-heavy")
    c = compare_weight_sets(session, WeightSet(), macro_heavy)
    assert c.verdict == "CHAMPION_AHEAD"


def test_identical_weights_are_a_tie_with_perfect_agreement(session: Session):
    _seed(session)
    c = compare_weight_sets(session, WeightSet(), WeightSet())
    assert c.verdict == "TIE"
    assert abs(c.rank_agreement - 1.0) < 1e-6
    assert c.ic_gain == 0.0


def test_both_sides_see_exactly_the_same_rows(session: Session):
    """A row missing one strength is dropped from BOTH sides — otherwise the
    comparison silently favours whichever set leans on the missing layer."""
    from app.models import ConvictionHistory
    _seed(session)
    row = session.query(ConvictionHistory).first()
    row.quality_strength = None
    session.commit()

    full = compare_weight_sets(session, WeightSet(), WeightSet())
    assert full.n == session.query(ConvictionHistory).count() - 1


def test_bands_are_reported_for_both_sides(session: Session):
    _seed(session)
    c = compare_weight_sets(session, WeightSet(), QUALITY_HEAVY)
    assert len(c.champion_bands) == len(c.candidate_bands) == 4
    assert sum(b["n"] for b in c.champion_bands) == c.n


# ---------- registry integration ----------

def test_an_unknown_version_is_reported_not_crashed(session: Session):
    assert evaluate_candidate(session, 9999)["status"] == "NOT_FOUND"


def test_a_non_weight_version_is_refused_with_the_reason(session: Session):
    """Replay is only valid for weight changes — anything else needs forward
    shadow recording, and pretending otherwise would return a wrong number."""
    from app.services.model_registry import register
    v = register(session, kind="ML_MODEL", label="new-features", params={"a": 1})
    out = evaluate_candidate(session, v.id)
    assert out["status"] == "UNSUPPORTED" and "forward shadow" in out["note"]


def test_the_live_champion_is_not_compared_to_itself(session: Session):
    from app.services.model_registry import promote, register
    v = register(session, kind="WEIGHTS", label="live", params=WeightSet().as_dict())
    promote(session, v.id, "moreshwar")
    assert evaluate_candidate(session, v.id)["status"] == "IS_CHAMPION"


def test_the_board_lists_shadows_and_counts_the_promotable(session: Session):
    from app.services.model_registry import promote, register
    _seed(session, driver="quality")
    live = register(session, kind="WEIGHTS", label="live",
                    params=WeightSet().as_dict())
    promote(session, live.id, "moreshwar")
    register(session, kind="WEIGHTS", label="quality-heavy",
             params=QUALITY_HEAVY.as_dict())

    board = shadow_board(session)
    assert board["champion"]["label"] == "live"
    assert len(board["shadows"]) == 1
    assert board["promotable"] == 1
    assert board["shadows"][0]["verdict"] == "CHALLENGER_AHEAD"


def test_being_ahead_does_not_promote_anything(session: Session):
    """The whole safety property: replay informs, humans decide."""
    from app.models import ModelVersion
    from app.services.model_registry import register
    _seed(session, driver="quality")
    register(session, kind="WEIGHTS", label="challenger",
             params=QUALITY_HEAVY.as_dict())
    shadow_board(session)
    assert all(v.status == "SHADOW" for v in session.query(ModelVersion).all())
