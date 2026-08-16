"""Model registry — versioned, auditable decision artefacts.

The rule this module exists to enforce: **nothing changes the live model without
a human and an audit row**. A learner may propose; only a person promotes.

It also solves a quieter problem. The moment weights change, every earlier score
becomes ambiguous unless you recorded which model produced it — you can no longer
separate "the market changed" from "we changed the model". Stamping
`model_version_id` on every score and trade keeps that answerable forever.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.scoring import WeightSet

log = logging.getLogger(__name__)

KIND_WEIGHTS = "WEIGHTS"
STATUSES = ("SHADOW", "CHAMPION", "RETIRED")

#: Used when the registry table is empty (fresh DB, or tests) so scoring always
#: has weights even before the migration seeds a champion.
FALLBACK_LABEL = "baseline-fallback"

#: Weight scopes (V23). 'global' is the fallback for any regime with no champion.
GLOBAL_SCOPE = "global"
REGIME_SCOPES = ("risk_on", "neutral", "risk_off")
SCOPES = (GLOBAL_SCOPE, *REGIME_SCOPES)

#: The five detected regimes collapse to three learning buckets. Five-way splits
#: of seven weights need data we will not have for years.
REGIME_TO_SCOPE = {"RISK_ON": "risk_on", "PULLBACK": "neutral", "CHOP": "neutral",
                   "BEAR_RALLY": "risk_off", "RISK_OFF": "risk_off"}


def scope_for_regime(regime_code: str | None) -> str:
    """Which weight scope governs a given detected regime."""
    return REGIME_TO_SCOPE.get((regime_code or "").upper(), GLOBAL_SCOPE)


def _audit(session: Session, version_id: int, from_status: str | None,
           to_status: str, actor: str, reason: str | None = None) -> None:
    from app.models import ModelVersionAudit
    session.add(ModelVersionAudit(version_id=version_id, from_status=from_status,
                                  to_status=to_status, actor=actor, reason=reason))


def get_champion(session: Session, kind: str = KIND_WEIGHTS,
                 scope: str = GLOBAL_SCOPE):
    """The live model version for a kind and scope, or None."""
    from app.models import ModelVersion
    try:
        return session.scalars(
            select(ModelVersion).where(ModelVersion.kind == kind,
                                       ModelVersion.scope == scope,
                                       ModelVersion.status == "CHAMPION")
            .limit(1)).first()
    except Exception:                       # noqa: BLE001 — table may not exist yet
        log.debug("model_versions unavailable", exc_info=True)
        return None


def get_anchor(session: Session, kind: str = KIND_WEIGHTS,
               scope: str = GLOBAL_SCOPE):
    """The most recent human-approved set for a scope.

    This is what automatic drift is measured against. Measuring against the
    *incumbent* instead would let drift ratchet — each automatic step inside the
    bound, the accumulated distance unbounded — which is precisely the failure
    mode a drift cap exists to prevent.

    Falls back to the global anchor so a brand-new regime scope is still bounded
    by something a person approved, rather than being unbounded by default.
    """
    from app.models import ModelVersion
    try:
        anchor = session.scalars(
            select(ModelVersion).where(ModelVersion.kind == kind,
                                       ModelVersion.scope == scope,
                                       ModelVersion.is_anchor.is_(True))
            .order_by(ModelVersion.id.desc()).limit(1)).first()
        if anchor is None and scope != GLOBAL_SCOPE:
            return get_anchor(session, kind, GLOBAL_SCOPE)
        return anchor
    except Exception:                       # noqa: BLE001
        log.debug("model_versions unavailable", exc_info=True)
        return None


def anchor_weights(session: Session, scope: str = GLOBAL_SCOPE) -> WeightSet:
    """The human-approved baseline for a scope, or the hardcoded defaults."""
    anchor = get_anchor(session, KIND_WEIGHTS, scope)
    if anchor is None:
        return WeightSet(label="baseline-defaults")
    return WeightSet.from_dict(anchor.params_json or {}, version_id=anchor.id,
                               label=anchor.label).normalised()


def champion_weights(session: Session, scope: str = GLOBAL_SCOPE) -> WeightSet:
    """The weight set scoring should use right now, for a given market condition.

    Resolution order: the scope's own champion, then the global champion, then
    the hardcoded defaults. The cascade means a fresh install, an unmigrated
    database and a regime nobody has learned yet all still score rather than
    failing — and a regime only ever diverges from global once it has earned it.
    """
    champion = get_champion(session, KIND_WEIGHTS, scope)
    if champion is None and scope != GLOBAL_SCOPE:
        champion = get_champion(session, KIND_WEIGHTS, GLOBAL_SCOPE)
    if champion is None:
        return WeightSet(label=FALLBACK_LABEL)
    return WeightSet.from_dict(champion.params_json or {},
                               version_id=champion.id,
                               label=champion.label).normalised()


def weights_for_regime(session: Session, regime_code: str | None) -> WeightSet:
    """The weights today's market condition calls for."""
    return champion_weights(session, scope_for_regime(regime_code))


def register(session: Session, *, kind: str, label: str, params: dict,
             metrics: dict | None = None, parent_id: int | None = None,
             notes: str | None = None, created_by: str = "system",
             scope: str = GLOBAL_SCOPE):
    """Add a new version as SHADOW. Never promotes, and never sets an anchor —
    an anchor represents a human decision and cannot be created by registration."""
    from app.models import ModelVersion
    version = ModelVersion(kind=kind, label=label, params_json=params,
                           metrics_json=metrics, status="SHADOW", scope=scope,
                           is_anchor=False,
                           parent_id=parent_id, notes=notes, created_by=created_by)
    session.add(version)
    session.flush()
    _audit(session, version.id, None, "SHADOW", created_by, "registered")
    session.commit()
    log.info("Registered %s version %s (%s, scope=%s) as SHADOW",
             kind, version.id, label, scope)
    return version


#: Actors whose promotions are automatic. Anything else is treated as a person,
#: and a person's promotion re-anchors the drift budget.
AUTOMATED_ACTORS = frozenset({"learner", "system", "migration", "auto-rollback"})


def promote(session: Session, version_id: int, approved_by: str,
            reason: str | None = None, *, automated: bool | None = None) -> dict:
    """Make a SHADOW version the CHAMPION for its scope, retiring the incumbent.

    `approved_by` is mandatory. When the actor is a person the promoted set
    becomes the new anchor — the baseline all subsequent automatic drift is
    measured from. Automatic promotions deliberately do NOT re-anchor, because
    an anchor that moves with every automatic step is not a bound at all.
    """
    from app.models import ModelVersion

    version = session.get(ModelVersion, version_id)
    if version is None:
        return {"status": "NOT_FOUND", "note": f"No model version {version_id}."}
    if version.status == "RETIRED":
        return {"status": "REJECTED",
                "note": "Retired versions are immutable — register a new one instead."}
    if version.status == "CHAMPION":
        return {"status": "NOOP", "note": f"{version.label} is already champion."}

    scope = version.scope or GLOBAL_SCOPE
    incumbent = get_champion(session, version.kind, scope)
    if incumbent is not None:
        incumbent.status = "RETIRED"
        _audit(session, incumbent.id, "CHAMPION", "RETIRED", approved_by,
               f"superseded by {version.label}")
        session.merge(incumbent)

    if automated is None:
        automated = approved_by.strip().lower() in AUTOMATED_ACTORS

    version.status = "CHAMPION"
    version.promoted_at = datetime.now(timezone.utc)
    version.promoted_by = approved_by
    if not automated:
        version.is_anchor = True            # a person signed for this one
    _audit(session, version.id, "SHADOW", "CHAMPION", approved_by, reason)
    session.merge(version)
    session.commit()
    log.info("Promoted %s -> CHAMPION (scope=%s) by %s%s", version.label, scope,
             approved_by, "" if automated else " [new anchor]")
    return {"status": "OK", "champion": version.label, "version_id": version.id,
            "scope": scope, "anchored": not automated,
            "retired": incumbent.label if incumbent is not None else None}


def rollback(session: Session, actor: str, reason: str | None = None,
             scope: str = GLOBAL_SCOPE) -> dict:
    """Restore the most recently retired version in a scope.

    Promotion must be reversible in one step; a change you cannot undo quickly is
    a change you will hesitate to make, and hesitation is how stale models survive.
    """
    from app.models import ModelVersion

    champion = get_champion(session, KIND_WEIGHTS, scope)
    previous = session.scalars(
        select(ModelVersion).where(ModelVersion.kind == KIND_WEIGHTS,
                                   ModelVersion.scope == scope,
                                   ModelVersion.status == "RETIRED")
        .order_by(ModelVersion.promoted_at.desc().nulls_last(),
                  ModelVersion.id.desc()).limit(1)).first()
    if previous is None:
        return {"status": "NOTHING_TO_ROLL_BACK", "scope": scope}

    if champion is not None:
        champion.status = "RETIRED"
        _audit(session, champion.id, "CHAMPION", "RETIRED", actor,
               reason or "rolled back")
        session.merge(champion)
    previous.status = "CHAMPION"
    previous.promoted_at = datetime.now(timezone.utc)
    previous.promoted_by = actor
    _audit(session, previous.id, "RETIRED", "CHAMPION", actor,
           reason or "rollback")
    session.merge(previous)
    session.commit()
    return {"status": "OK", "champion": previous.label, "scope": scope}


def revert_to_anchor(session: Session, actor: str, scope: str = GLOBAL_SCOPE,
                     reason: str | None = None) -> dict:
    """Discard everything automatic and return to the last human-approved set.

    Distinct from `rollback`, which steps back one version. This is the panic
    button: however many automatic promotions have happened, one call puts the
    scope back to weights a person signed for. Under full autonomy this is the
    control that matters most, so it must be one step and never fail silently.
    """
    from app.models import ModelVersion

    anchor = get_anchor(session, KIND_WEIGHTS, scope)
    if anchor is None:
        return {"status": "NO_ANCHOR", "scope": scope,
                "note": "No human-approved set exists for this scope yet."}

    champion = get_champion(session, KIND_WEIGHTS, scope)
    if champion is not None and champion.id == anchor.id:
        return {"status": "NOOP", "scope": scope,
                "note": f"{anchor.label} is already live — nothing to revert."}

    if champion is not None:
        champion.status = "RETIRED"
        _audit(session, champion.id, "CHAMPION", "RETIRED", actor,
               reason or "reverted to anchor")
        session.merge(champion)

    # The anchor may itself be RETIRED after automatic promotions superseded it.
    anchor_scope = anchor.scope or GLOBAL_SCOPE
    if anchor_scope != scope:
        # The global anchor was borrowed for a regime with none of its own; copy
        # it into this scope rather than moving it out of global.
        anchor = ModelVersion(
            kind=KIND_WEIGHTS, label=f"{anchor.label}@{scope}",
            params_json=anchor.params_json, metrics_json=anchor.metrics_json,
            status="SHADOW", scope=scope, is_anchor=True, parent_id=anchor.id,
            notes="Copy of the global anchor, re-anchored for this regime.",
            created_by=actor)
        session.add(anchor)
        session.flush()

    previous_status = anchor.status
    anchor.status = "CHAMPION"
    anchor.promoted_at = datetime.now(timezone.utc)
    anchor.promoted_by = actor
    anchor.is_anchor = True
    _audit(session, anchor.id, previous_status, "CHAMPION", actor,
           reason or "reverted to human-approved baseline")
    session.merge(anchor)
    session.commit()
    log.info("Reverted scope=%s to anchor %s by %s", scope, anchor.label, actor)
    return {"status": "OK", "scope": scope, "champion": anchor.label,
            "version_id": anchor.id}


def list_versions(session: Session, kind: str = KIND_WEIGHTS) -> dict:
    """Everything registered, newest first — the governance view."""
    from app.models import ModelVersion
    try:
        rows = session.scalars(
            select(ModelVersion).where(ModelVersion.kind == kind)
            .order_by(ModelVersion.id.desc())).all()
    except Exception:                       # noqa: BLE001
        return {"kind": kind, "versions": [], "note": "Registry not migrated yet."}
    return {
        "kind": kind,
        "champion_id": next((r.id for r in rows
                             if r.status == "CHAMPION"
                             and (r.scope or GLOBAL_SCOPE) == GLOBAL_SCOPE), None),
        "champions_by_scope": {
            (r.scope or GLOBAL_SCOPE): {"id": r.id, "label": r.label,
                                        "params": r.params_json,
                                        "promoted_by": r.promoted_by,
                                        "is_anchor": bool(r.is_anchor)}
            for r in rows if r.status == "CHAMPION"},
        "versions": [{"id": r.id, "label": r.label, "status": r.status,
                      "scope": r.scope or GLOBAL_SCOPE,
                      "is_anchor": bool(r.is_anchor),
                      "params": r.params_json, "metrics": r.metrics_json,
                      "notes": r.notes, "created_by": r.created_by,
                      "created_at": r.created_at.isoformat() if r.created_at else None,
                      "promoted_at": (r.promoted_at.isoformat()
                                      if r.promoted_at else None),
                      "promoted_by": r.promoted_by}
                     for r in rows],
    }
