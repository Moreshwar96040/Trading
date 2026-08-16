"""Autonomous adaptation — the Alpha Stack adjusting its own weights.

This is the module that makes the system self-modifying, so it is the module
where being careful matters most. What it does, once per run, per scope:

    1. refit candidate weights on that scope's labelled history
    2. run every validation gate, plus the autonomy bounds
    3. replay the candidate against the live champion on identical history
    4. promote it — by itself, no human — if and only if all of that passes
    5. record why, in `adaptation_events`, whatever the outcome

The safety properties, and why each exists:

  **Bounded, not free.** A candidate may move any layer at most `MAX_LAYER_DRIFT`
  points from the last *human-approved* anchor, and may not switch a layer off.
  Beyond that it registers as a shadow and waits for you. The learner is allowed
  to want a large change; it cannot make one alone.

  **Anchored, not relative.** Drift is measured from the anchor, never the
  incumbent. Relative bounds ratchet — ten points per promotion, each step legal,
  the total unbounded.

  **Frozen safety rules.** The news veto is not a weight and is not learnable.
  A rule whose value comes from being non-negotiable must not be negotiable.

  **Cooldown.** At most one automatic promotion per scope per `COOLDOWN_DAYS`.
  Without it a noisy week produces a chain of promotions, each individually
  justified, that collectively chase noise.

  **Breakers first.** If the circuit breakers are tripped, adaptation does not
  run at all. Learning from a period the system has already flagged as broken is
  how a bad model teaches itself to be worse.

  **Off by default.** `AUTO_ADAPT_ENABLED=false` unless explicitly turned on.

The honest limitation: none of this makes the learner *right*. It makes the
learner bounded, reversible and legible. Those are different things, and only
the second set is achievable by engineering.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

#: Minimum days between two automatic promotions in the same scope.
COOLDOWN_DAYS = 14
#: A scope needs its own data before it may diverge from global.
MIN_SCOPE_SAMPLES = 200
#: The challenger must beat the champion by at least this much IC on replay.
MIN_REPLAY_EDGE = 0.005


def _record(session: Session, *, scope: str, action: str, reason: str,
            version_id: int | None = None, anchor_id: int | None = None,
            samples: int | None = None, oos_ic: float | None = None,
            champion_ic: float | None = None, max_drift: float | None = None,
            gates: list | None = None, weights: dict | None = None,
            triggered_by: str = "learner") -> None:
    """Every decision leaves a row, including the decisions to do nothing.

    A log that only records changes cannot answer "why has it not adapted?",
    which is the question you will actually ask.
    """
    from app.models import AdaptationEvent
    session.add(AdaptationEvent(
        scope=scope, action=action, reason=reason[:500], version_id=version_id,
        anchor_id=anchor_id, samples=samples, oos_ic=oos_ic,
        champion_ic=champion_ic, max_drift=max_drift, gates_json=gates,
        weights_json=weights, triggered_by=triggered_by))
    session.commit()


def _in_cooldown(session: Session, scope: str,
                 days: int = COOLDOWN_DAYS) -> int | None:
    """Days remaining before this scope may be promoted again, or None."""
    from app.models import AdaptationEvent
    last = session.scalars(
        select(AdaptationEvent)
        .where(AdaptationEvent.scope == scope,
               AdaptationEvent.action == "PROMOTED")
        .order_by(AdaptationEvent.occurred_at.desc()).limit(1)).first()
    if last is None or last.occurred_at is None:
        return None
    # SQLite hands back naive datetimes; Postgres returns aware ones. Normalise
    # rather than assuming, or the cooldown crashes on one backend and not the
    # other — and a crashed cooldown check is a cooldown that isn't enforced.
    occurred = last.occurred_at
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - occurred).days
    remaining = days - elapsed
    return remaining if remaining > 0 else None


def adapt_scope(session: Session, scope: str, horizon: str = "fwd_return_10d",
                *, dry_run: bool = False) -> dict:
    """Attempt one autonomous adaptation for a single scope."""
    from app.ai.calibration import LAYERS, _learn_weights, _load_frame
    from app.ai.gates import (evaluate_all, gate_drift_bounded,
                              gate_frozen_params_untouched, gate_no_sign_flip,
                              gate_oos_improves, gate_sample_size, gate_stability,
                              gate_turnover)
    from app.ai.shadow import compare_weight_sets
    from app.scoring import WeightSet
    from app.services.conviction_service import LAYER_WEIGHTS
    from app.services.model_registry import (GLOBAL_SCOPE, REGIME_TO_SCOPE,
                                             champion_weights, get_anchor,
                                             get_champion, promote, register)

    anchor = get_anchor(session, scope=scope)
    anchor_weights = (WeightSet.from_dict(anchor.params_json).normalised().as_dict()
                      if anchor is not None
                      else {layer: LAYER_WEIGHTS[layer] for layer in LAYERS})

    # A dry run must leave no trace at all — not a version, not a log row. A
    # "preview" that writes is just a slower version of doing the thing.
    def record(**kw):
        if not dry_run:
            _record(session, **kw)

    cooldown = _in_cooldown(session, scope)
    if cooldown:
        reason = (f"In cooldown — {cooldown} more day(s) before {scope} may "
                  "change again. Back-to-back promotions chase noise.")
        record(scope=scope, action="SKIPPED", reason=reason,
               anchor_id=anchor.id if anchor else None)
        return {"scope": scope, "action": "SKIPPED", "reason": reason}

    # Only this scope's own market conditions inform its weights.
    frame = _load_frame(session, horizon)
    if not frame.empty and scope != GLOBAL_SCOPE:
        frame = frame[frame["regime_code"].map(
            lambda code: REGIME_TO_SCOPE.get((code or "").upper(),
                                             GLOBAL_SCOPE)) == scope]

    n = int(len(frame))
    minimum = MIN_SCOPE_SAMPLES if scope != GLOBAL_SCOPE else 200
    if n < minimum:
        reason = (f"{n} labelled setups in {scope} — needs {minimum}. Until then "
                  f"{scope} keeps using the global weights, which is the correct "
                  "answer rather than a limitation.")
        record(scope=scope, action="SKIPPED", reason=reason, samples=n,
               anchor_id=anchor.id if anchor else None)
        return {"scope": scope, "action": "SKIPPED", "reason": reason, "n": n}

    current = champion_weights(session, scope).as_dict()
    fit = _learn_weights(frame, current)
    if fit.get("status") != "OK":
        reason = fit.get("note", "No usable fit.")
        record(scope=scope, action="SKIPPED", reason=reason, samples=n,
               anchor_id=anchor.id if anchor else None)
        return {"scope": scope, "action": "SKIPPED", "reason": reason, "n": n}

    candidate = {row["layer"]: row["suggested"] for row in fit["weights"]}
    coeffs = {row["layer"]: row["coefficient"] for row in fit["weights"]}

    champion = get_champion(session, scope=scope)
    champion_ic = ((champion.metrics_json or {}).get("oos_ic")
                   if champion is not None else None)

    cur_scores, cand_scores = [], []
    for _, row in frame.iterrows():
        cur_scores.append(sum(current[layer] * (row[f"{layer}_strength"] or 0.0)
                              for layer in LAYERS))
        cand_scores.append(sum(candidate[layer] * (row[f"{layer}_strength"] or 0.0)
                               for layer in LAYERS))
    ic_gain = (fit.get("oos_ic") or 0.0) - (champion_ic or 0.0)

    drift_gate = gate_drift_bounded(anchor_weights, candidate)
    gates = [
        gate_sample_size(n, minimum),
        gate_oos_improves(fit.get("oos_ic"), champion_ic),
        gate_turnover(cur_scores, cand_scores, ic_gain),
        gate_no_sign_flip(current, coeffs, n),
        gate_stability(_bootstrap(frame, current)),
        drift_gate,
        gate_frozen_params_untouched(candidate),
    ]
    verdict = evaluate_all(gates)
    max_drift = (drift_gate.detail or {}).get("max_drift")

    base = {"scope": scope, "n": n, "candidate": candidate,
            "oos_ic": fit.get("oos_ic"), "max_drift": max_drift, **verdict}

    if not verdict["passed"]:
        if dry_run:
            return {**base, "action": "WOULD_REJECT", "reason": verdict["summary"]}
        # Still worth registering: a candidate that fails only the drift bound is
        # exactly the change a person might want to approve deliberately.
        version = register(session, kind="WEIGHTS", scope=scope,
                           label=f"rejected-{scope}-n{n}", params=candidate,
                           metrics={"oos_ic": fit.get("oos_ic"), "n": n,
                                    "gates": verdict["gates"]},
                           notes=verdict["summary"], created_by="learner")
        _record(session, scope=scope, action="REJECTED", reason=verdict["summary"],
                version_id=version.id, anchor_id=anchor.id if anchor else None,
                samples=n, oos_ic=fit.get("oos_ic"), champion_ic=champion_ic,
                max_drift=max_drift, gates=verdict["gates"], weights=candidate)
        return {**base, "action": "REJECTED", "version_id": version.id}

    # Gates passed. One more test the gates cannot do: does it actually rank the
    # real history better than what is live right now?
    replay = compare_weight_sets(
        session, champion_weights(session, scope),
        WeightSet.from_dict(candidate).normalised(), horizon=horizon)
    if replay.ic_gain is None or replay.ic_gain < MIN_REPLAY_EDGE:
        reason = (f"Gates passed but replay does not confirm: {replay.note} "
                  "Not promoting on a fit alone.")
        if dry_run:
            return {**base, "action": "WOULD_REJECT", "reason": reason}
        version = register(session, kind="WEIGHTS", scope=scope,
                           label=f"unconfirmed-{scope}-n{n}", params=candidate,
                           metrics={"oos_ic": fit.get("oos_ic"), "n": n,
                                    "replay": replay.to_dict()},
                           notes=reason, created_by="learner")
        _record(session, scope=scope, action="REJECTED", reason=reason,
                version_id=version.id, anchor_id=anchor.id if anchor else None,
                samples=n, oos_ic=fit.get("oos_ic"), champion_ic=replay.champion_ic,
                max_drift=max_drift, gates=verdict["gates"], weights=candidate)
        return {**base, "action": "REJECTED", "reason": reason,
                "version_id": version.id}

    if dry_run:
        return {**base, "action": "WOULD_PROMOTE",
                "replay": replay.to_dict(),
                "reason": "Dry run — everything passed, nothing changed."}

    version = register(session, kind="WEIGHTS", scope=scope,
                       label=f"auto-{scope}-{datetime.now(timezone.utc):%Y%m%d}",
                       params=candidate,
                       metrics={"oos_ic": fit.get("oos_ic"), "n": n,
                                "gates": verdict["gates"],
                                "replay": replay.to_dict()},
                       parent_id=champion.id if champion is not None else None,
                       notes="Promoted autonomously within the approved bounds.",
                       created_by="learner")
    promote(session, version.id, "learner",
            f"autonomous: replay +{replay.ic_gain:.4f} IC, drift {max_drift}pts",
            automated=True)
    reason = (f"Promoted automatically. Replay IC {replay.candidate_ic:+.4f} vs "
              f"{replay.champion_ic:+.4f} on {replay.n} setups; largest layer move "
              f"{max_drift} points from your approved baseline.")
    _record(session, scope=scope, action="PROMOTED", reason=reason,
            version_id=version.id, anchor_id=anchor.id if anchor else None,
            samples=n, oos_ic=fit.get("oos_ic"), champion_ic=replay.champion_ic,
            max_drift=max_drift, gates=verdict["gates"], weights=candidate)
    log.info("Autonomous promotion in %s: %s", scope, reason)
    return {**base, "action": "PROMOTED", "version_id": version.id,
            "reason": reason, "replay": replay.to_dict()}


def _bootstrap(frame, current: dict, rounds: int = 100) -> list:
    from app.ai.calibration import _bootstrap_weights
    return _bootstrap_weights(frame, current, rounds=rounds)


def run_auto_adaptation(session: Session, settings, *,
                        dry_run: bool = False) -> dict:
    """The scheduled entry point: adapt every scope, or explain why not."""
    from app.services.circuit_breakers import evaluate as check_breakers
    from app.services.model_registry import GLOBAL_SCOPE, REGIME_SCOPES

    enabled = bool(getattr(settings, "auto_adapt_enabled", False))
    if not enabled and not dry_run:
        return {"status": "DISABLED",
                "note": ("Set AUTO_ADAPT_ENABLED=true to let the Alpha Stack "
                         "adjust its own weights. Off by default on purpose.")}

    breakers = check_breakers(session)
    if breakers["halted"]:
        reason = (f"Adaptation skipped — {breakers['summary']} Learning from a "
                  "period already flagged as broken teaches the model to be worse.")
        _record(session, scope="global", action="SKIPPED", reason=reason)
        return {"status": "HALTED", "note": reason, "breakers": breakers}

    results = [adapt_scope(session, scope, dry_run=dry_run)
               for scope in (GLOBAL_SCOPE, *REGIME_SCOPES)]
    promoted = [r for r in results if r["action"] in ("PROMOTED", "WOULD_PROMOTE")]
    return {"status": "OK", "dry_run": dry_run, "promoted": len(promoted),
            "scopes": results,
            "note": ("Every outcome, including the decisions to do nothing, is "
                     "recorded in the adaptation log.")}


def adaptation_history(session: Session, limit: int = 50) -> dict:
    """What the system changed about itself, and why."""
    from app.models import AdaptationEvent
    from app.services.model_registry import (GLOBAL_SCOPE, REGIME_SCOPES,
                                             champion_weights, get_anchor,
                                             scope_for_regime)
    from app.services.regime_service import compute_regime

    rows = session.scalars(
        select(AdaptationEvent)
        .order_by(AdaptationEvent.occurred_at.desc()).limit(limit)).all()

    # Which scope is actually governing scores right now — the single most useful
    # fact on this screen, and not inferable from the list of scopes alone.
    try:
        regime = compute_regime(session)
        regime_code = regime.get("regime") if regime.get("status") == "OK" else None
    except Exception:                       # noqa: BLE001 — panel must not fail
        regime_code = None

    scopes = []
    for scope in (GLOBAL_SCOPE, *REGIME_SCOPES):
        live = champion_weights(session, scope)
        anchor = get_anchor(session, scope=scope)
        scopes.append({
            "scope": scope, "label": live.label, "weights": live.as_dict(),
            "version_id": live.version_id,
            "anchor_label": anchor.label if anchor is not None else None,
            "is_anchor": bool(anchor is not None and anchor.id == live.version_id),
            "cooldown_days_left": _in_cooldown(session, scope)})

    return {
        "scopes": scopes,
        "regime_code": regime_code,
        "current_scope": scope_for_regime(regime_code),
        "events": [{"id": e.id, "scope": e.scope, "action": e.action,
                    "reason": e.reason,
                    "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
                    "samples": e.samples,
                    "oos_ic": float(e.oos_ic) if e.oos_ic is not None else None,
                    "max_drift": (float(e.max_drift)
                                  if e.max_drift is not None else None),
                    "weights": e.weights_json, "gates": e.gates_json,
                    "triggered_by": e.triggered_by}
                   for e in rows],
        "note": ("Scopes with no champion of their own use the global weights — "
                 "a regime only diverges once its own data justifies it."),
    }
