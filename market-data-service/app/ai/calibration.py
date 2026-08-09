"""Phase 2+3 of adaptive conviction: does the Alpha Stack actually predict anything,
and what would better weights look like?

Two separate questions, deliberately kept apart:

  DIAGNOSTIC (from ~30 rows) - per-layer Information Coefficient, a calibration
      curve by conviction band, and a veto audit. These need no model and answer
      the blunt question: do 75+ setups really beat 55-75 ones?

  WEIGHTS (hard-gated at 200 rows) - a ridge regression of forward return on the
      seven layer strengths, walk-forward validated, shrunk toward the current
      weights. Output is a SUGGESTION. Nothing here ever rewrites the live model.

Why linear: the scoring formula is literally a weighted sum, so ridge coefficients
translate straight back into weights you can read and argue with. A gradient-boosted
model would fit better and tell you nothing actionable.

Why shrinkage: the current weights encode trading logic; a few hundred noisy samples
encode mostly noise. Suggestions move part of the way, never all of it.
"""
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

LAYERS = ["technical", "quality", "news", "momentum", "ml", "macro", "regime"]

#: Enough to look at a calibration curve without fooling ourselves.
MIN_SAMPLES_DIAGNOSTIC = 30
#: Hard gate before any weight suggestion is produced. Seven parameters need
#: a few hundred rows before the fit is anything but noise.
MIN_SAMPLES_WEIGHTS = 200
#: How far a suggestion is allowed to move from the current weights.
LEARNED_SHARE = 0.3
#: |t| above this ~= 95% confidence for a correlation.
T_SIGNIFICANT = 1.96
#: Conviction bands, mirroring the live sizing thresholds.
BANDS = [(0, 40, "<40 stand aside"), (40, 55, "40-55 small"),
         (55, 75, "55-75 normal"), (75, 101, "75+ high")]


def _spearman(a, b) -> float | None:
    """Rank correlation, computed as Pearson on ranks.

    pandas' own method="spearman" reaches for scipy; doing it directly keeps this
    module dependent on nothing but pandas/numpy, which matters because the
    calibration endpoint must never 500 over an optional scientific package.
    """
    pair = a.rank().corr(b.rank())          # default Pearson — no scipy path
    return None if pair is None or pair != pair else float(pair)


def _t_stat(r: float, n: int) -> float | None:
    """t-statistic for a correlation — significance without a scipy dependency."""
    if n < 4 or r is None or abs(r) >= 1.0:
        return None
    import math
    return r * math.sqrt((n - 2) / (1 - r * r))


def _load_frame(session, horizon: str):
    """Labelled conviction rows as a DataFrame."""
    import pandas as pd
    from sqlalchemy import select

    from app.models import ConvictionHistory

    cols = [ConvictionHistory.as_of_date, ConvictionHistory.conviction,
            ConvictionHistory.verdict, ConvictionHistory.news_veto,
            ConvictionHistory.regime_code,
            *[getattr(ConvictionHistory, f"{layer}_strength") for layer in LAYERS],
            getattr(ConvictionHistory, horizon)]
    rows = session.execute(
        select(*cols).where(getattr(ConvictionHistory, horizon).isnot(None))
        .order_by(ConvictionHistory.as_of_date)).all()
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=[
        "as_of_date", "conviction", "verdict", "news_veto", "regime_code",
        *[f"{layer}_strength" for layer in LAYERS], "label"])
    numeric = ["conviction", "label"] + [f"{layer}_strength" for layer in LAYERS]
    for col in numeric:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def _layer_ic(frame) -> list[dict]:
    """Spearman rank correlation of each layer's strength with the forward return.

    Rank correlation, not Pearson: we care whether *higher strength ranks higher
    return*, not whether the relationship is linear. In equities an IC of
    0.03-0.05 is genuinely useful and 0.10+ is strong — the intuition that a
    'good' correlation is 0.7 does not apply here.
    """
    out = []
    for layer in LAYERS:
        col = f"{layer}_strength"
        pair = frame[[col, "label"]].dropna()
        n = len(pair)
        # A layer that never varies (e.g. macro constant all week) has no
        # estimable relationship — say so rather than emitting a spurious 0.
        if n < 10 or pair[col].nunique() < 3:
            out.append({"layer": layer, "ic": None, "n": n, "significant": False,
                        "note": "not enough variation to measure"})
            continue
        ic = _spearman(pair[col], pair["label"])
        ic = None if ic is None or ic != ic else round(float(ic), 4)   # NaN guard
        t = _t_stat(ic, n) if ic is not None else None
        out.append({
            "layer": layer, "ic": ic, "n": n,
            "t_stat": round(t, 2) if t is not None else None,
            "significant": bool(t is not None and abs(t) >= T_SIGNIFICANT),
            "note": None})
    return out


def _calibration_curve(frame) -> list[dict]:
    """Mean forward return and hit rate per conviction band.

    The headline sanity check: if this curve is flat, the score is not
    discriminating and no reweighting will fix it.
    """
    out = []
    for low, high, label in BANDS:
        bucket = frame[(frame["conviction"] >= low) & (frame["conviction"] < high)]
        n = len(bucket)
        if not n:
            out.append({"band": label, "n": 0, "avg_return": None, "hit_rate": None})
            continue
        out.append({
            "band": label, "n": n,
            "avg_return": round(float(bucket["label"].mean()), 3),
            "median_return": round(float(bucket["label"].median()), 3),
            "hit_rate": round(float((bucket["label"] > 0).mean() * 100.0), 1)})
    return out


def _veto_audit(frame) -> dict:
    """Did news-vetoed setups actually deserve it? A veto that blocks winners
    is a cost, not a safety feature."""
    vetoed = frame[frame["news_veto"] == True]        # noqa: E712 — pandas mask
    rest = frame[frame["news_veto"] != True]          # noqa: E712
    if not len(vetoed):
        return {"n": 0, "note": "No vetoed setups in this window."}
    v_mean = float(vetoed["label"].mean())
    r_mean = float(rest["label"].mean()) if len(rest) else None
    verdict = ("veto is protecting you" if r_mean is not None and v_mean < r_mean
               else "vetoed setups did NOT underperform — the veto may be costing you")
    return {"n": len(vetoed), "avg_return_vetoed": round(v_mean, 3),
            "avg_return_other": round(r_mean, 3) if r_mean is not None else None,
            "verdict": verdict}


RIDGE_ALPHA = 1.0


def _ridge_fit(x, y, alpha: float = RIDGE_ALPHA):
    """Closed-form ridge: beta = (XtX + aI)^-1 Xt y, on mean-centred data.

    Deliberately numpy rather than sklearn — seven features do not justify the
    dependency, and the closed form is exact, not iterative.
    """
    import numpy as np
    x_mean, y_mean = x.mean(axis=0), y.mean()
    xc, yc = x - x_mean, y - y_mean
    gram = xc.T @ xc + alpha * np.eye(xc.shape[1])
    beta = np.linalg.solve(gram, xc.T @ yc)
    return beta, x_mean, y_mean


def _ridge_predict(beta, x_mean, y_mean, x):
    return (x - x_mean) @ beta + y_mean


def _learn_weights(frame, current: dict) -> dict:
    """Ridge fit of forward return on layer strengths -> suggested weights.

    Validated walk-forward (train on the past, test on the future) because a
    random split on time series leaks the future backwards and produces
    flattering, meaningless accuracy.
    """
    import numpy as np
    import pandas as pd

    feature_cols = [f"{layer}_strength" for layer in LAYERS]
    data = frame[feature_cols + ["label"]].dropna()
    n = len(data)
    if n < MIN_SAMPLES_WEIGHTS:
        return {"status": "INSUFFICIENT", "n": n, "needed": MIN_SAMPLES_WEIGHTS}

    x = data[feature_cols].to_numpy(dtype=float)
    y = data["label"].to_numpy(dtype=float)

    # ---- walk-forward out-of-sample check (4 chronological folds) ----
    folds, oos_pred, oos_true = 4, [], []
    edges = [int(n * i / folds) for i in range(folds + 1)]
    for i in range(1, folds):
        train_end, test_end = edges[i], edges[i + 1]
        if train_end < 20 or test_end - train_end < 5:
            continue
        try:
            beta, xm, ym = _ridge_fit(x[:train_end], y[:train_end])
        except np.linalg.LinAlgError:          # degenerate fold — skip it
            continue
        oos_pred.extend(_ridge_predict(beta, xm, ym, x[train_end:test_end]))
        oos_true.extend(y[train_end:test_end])

    oos_ic = None
    if len(oos_pred) >= 20:
        ic = _spearman(pd.Series(oos_pred), pd.Series(oos_true))
        oos_ic = None if ic != ic else round(float(ic), 4)

    # ---- fit on everything for the suggestion itself ----
    try:
        final_beta, _, _ = _ridge_fit(x, y)
    except np.linalg.LinAlgError:
        return {"status": "NO_SIGNAL", "n": n, "oos_ic": oos_ic,
                "note": "Layer strengths are collinear — cannot separate their effects."}
    coefs = {layer: float(c) for layer, c in zip(LAYERS, final_beta)}

    # Negative coefficient = that layer scored *against* returns. We clip to zero
    # rather than inverting the layer: inverting on a few hundred noisy samples is
    # how you end up trading the opposite of a sound thesis.
    positive = {layer: max(0.0, c) for layer, c in coefs.items()}
    total = sum(positive.values())
    if total <= 0:
        return {"status": "NO_SIGNAL", "n": n, "oos_ic": oos_ic,
                "note": "No layer showed a positive relationship — weights unchanged."}

    learned = {layer: v / total * 100.0 for layer, v in positive.items()}
    suggested = {layer: round((1 - LEARNED_SHARE) * current[layer]
                              + LEARNED_SHARE * learned[layer], 1)
                 for layer in LAYERS}
    # renormalise so the suggestion still sums to 100
    scale = 100.0 / sum(suggested.values())
    suggested = {layer: round(v * scale, 1) for layer, v in suggested.items()}

    return {
        "status": "OK", "n": n, "oos_ic": oos_ic,
        "shrinkage": LEARNED_SHARE,
        "weights": [{"layer": layer, "current": current[layer],
                     "learned_raw": round(learned[layer], 1),
                     "suggested": suggested[layer],
                     "delta": round(suggested[layer] - current[layer], 1),
                     "coefficient": round(coefs[layer], 4)}
                    for layer in LAYERS],
    }


# --- Hierarchical regime weights -------------------------------------------
#: Five regimes divided by our data volume is a resolution we cannot support for
#: years, so learning collapses them to three. Display keeps all five.
REGIME_BUCKET = {"RISK_ON": "risk_on", "PULLBACK": "neutral", "CHOP": "neutral",
                 "BEAR_RALLY": "risk_off", "RISK_OFF": "risk_off"}
#: Shrinkage constant. With n samples a regime moves n/(n+k) of the way from the
#: global weights toward its own fit — so 20 samples barely move, 800 mostly do.
REGIME_SHRINK_K = 200


def learn_regime_weights(session, horizon: str = "fwd_return_10d") -> dict:
    """Partially-pooled weights per regime bucket.

    Fitting each regime independently would be 7 weights x 5 regimes = 35
    parameters while *dividing* the data — noise wearing a confident label, and
    most wrong exactly when regimes shift. Instead each bucket starts identical
    to the global fit and drifts only in proportion to its own evidence.
    """
    from app.services.conviction_service import LAYER_WEIGHTS

    frame = _load_frame(session, horizon)
    if frame.empty:
        return {"status": "COLLECTING", "n": 0, "buckets": []}

    current = {layer: LAYER_WEIGHTS[layer] for layer in LAYERS}
    global_fit = _learn_weights(frame, current)
    if global_fit.get("status") != "OK":
        return {"status": global_fit.get("status", "INSUFFICIENT"),
                "n": int(len(frame)),
                "note": "Global weights must be learnable before regime splits."}
    global_weights = {row["layer"]: row["suggested"] for row in global_fit["weights"]}

    frame = frame.copy()
    frame["bucket"] = frame["regime_code"].map(
        lambda code: REGIME_BUCKET.get(code or "", "neutral"))

    buckets = []
    for bucket, group in frame.groupby("bucket"):
        n = int(len(group))
        raw = _learn_weights(group, current)
        shrink = round(n / (n + REGIME_SHRINK_K), 3)
        if raw.get("status") != "OK":
            # Not enough data for its own fit — that is fine, and the honest
            # answer is simply the global weights.
            buckets.append({"bucket": bucket, "n": n, "shrink": shrink,
                            "status": "USING_GLOBAL",
                            "weights": [{"layer": layer, "weight": global_weights[layer],
                                         "drift": 0.0} for layer in LAYERS]})
            continue
        raw_weights = {row["layer"]: row["suggested"] for row in raw["weights"]}
        pooled = {layer: global_weights[layer]
                  + shrink * (raw_weights[layer] - global_weights[layer])
                  for layer in LAYERS}
        scale = 100.0 / sum(pooled.values())
        pooled = {layer: round(v * scale, 1) for layer, v in pooled.items()}
        buckets.append({
            "bucket": bucket, "n": n, "shrink": shrink, "status": "OK",
            "weights": [{"layer": layer, "weight": pooled[layer],
                         "drift": round(pooled[layer] - global_weights[layer], 1)}
                        for layer in LAYERS]})

    return {"status": "OK", "horizon": horizon, "n": int(len(frame)),
            "shrink_k": REGIME_SHRINK_K,
            "global_weights": global_weights, "buckets": buckets,
            "note": ("Each regime starts at the global weights and drifts only in "
                     "proportion to its own evidence — with little data the drift "
                     "is near zero by construction.")}


def _bootstrap_weights(frame, current: dict, rounds: int = 100) -> list:
    """Refit on resampled data to see whether the weights hold still."""
    import numpy as np
    rng = np.random.default_rng(12345)          # seeded: stability must be reproducible
    feature_cols = [f"{layer}_strength" for layer in LAYERS]
    data = frame[feature_cols + ["label"]].dropna()
    n = len(data)
    if n < MIN_SAMPLES_WEIGHTS:
        return []
    out = []
    for _ in range(rounds):
        idx = rng.integers(0, n, n)
        sample = data.iloc[idx]
        fit = _learn_weights(sample, current)
        if fit.get("status") == "OK":
            out.append({row["layer"]: row["suggested"] for row in fit["weights"]})
    return out


def propose_weights(session, horizon: str = "fwd_return_10d",
                    register_shadow: bool = True) -> dict:
    """Fit candidate weights, run every validation gate, and register a SHADOW
    version only if all of them pass.

    Never promotes. Passing the gates earns a candidate the right to be *watched*,
    not the right to trade.
    """
    from app.ai.gates import (evaluate_all, gate_no_sign_flip, gate_oos_improves,
                              gate_sample_size, gate_stability, gate_turnover)
    from app.services.conviction_service import LAYER_WEIGHTS
    from app.services.model_registry import get_champion, register

    frame = _load_frame(session, horizon)
    n = int(len(frame))
    current = {layer: LAYER_WEIGHTS[layer] for layer in LAYERS}

    size_gate = gate_sample_size(n)
    if not size_gate.passed:
        return {"status": "REJECTED", "n": n,
                **evaluate_all([size_gate])}

    fit = _learn_weights(frame, current)
    if fit.get("status") != "OK":
        return {"status": "REJECTED", "n": n,
                "note": fit.get("note", "No usable fit."),
                "gates": [size_gate.to_dict()]}

    candidate = {row["layer"]: row["suggested"] for row in fit["weights"]}
    coeffs = {row["layer"]: row["coefficient"] for row in fit["weights"]}

    # Champion's recorded OOS IC, if we have one to beat.
    champion = get_champion(session)
    champion_ic = ((champion.metrics_json or {}).get("oos_ic")
                   if champion is not None else None)

    # Ranking churn: score every row under both weight sets and compare order.
    cur_scores, cand_scores = [], []
    for _, row in frame.iterrows():
        cur_scores.append(sum(current[layer] * (row[f"{layer}_strength"] or 0.0)
                              for layer in LAYERS))
        cand_scores.append(sum(candidate[layer] * (row[f"{layer}_strength"] or 0.0)
                               for layer in LAYERS))
    ic_gain = (fit.get("oos_ic") or 0.0) - (champion_ic or 0.0)

    gates = [
        size_gate,
        gate_oos_improves(fit.get("oos_ic"), champion_ic),
        gate_turnover(cur_scores, cand_scores, ic_gain),
        gate_no_sign_flip(current, coeffs, n),
        gate_stability(_bootstrap_weights(frame, current)),
    ]
    verdict = evaluate_all(gates)

    result = {"status": "PASSED" if verdict["passed"] else "REJECTED",
              "n": n, "horizon": horizon, "candidate": candidate,
              "oos_ic": fit.get("oos_ic"), "champion_oos_ic": champion_ic,
              **verdict}

    if verdict["passed"] and register_shadow:
        version = register(
            session, kind="WEIGHTS",
            label=f"learned-{horizon}-n{n}", params=candidate,
            metrics={"oos_ic": fit.get("oos_ic"), "n": n,
                     "gates": verdict["gates"]},
            parent_id=champion.id if champion is not None else None,
            notes="Auto-proposed by the learner; awaiting human promotion.",
            created_by="learner")
        result["registered_version_id"] = version.id
        result["note"] = ("Registered as SHADOW. It will be scored alongside the "
                          "champion but will not trade until a human promotes it.")
    return result


def calibration_report(session, horizon: str = "fwd_return_10d") -> dict:
    """The whole Phase 2+3 read, safe to call from day one."""
    from app.services.conviction_service import LAYER_WEIGHTS

    frame = _load_frame(session, horizon)
    n = len(frame)
    if n < MIN_SAMPLES_DIAGNOSTIC:
        return {"status": "COLLECTING", "n": n, "needed": MIN_SAMPLES_DIAGNOSTIC,
                "horizon": horizon,
                "note": (f"{n} labelled setups so far; diagnostics unlock at "
                         f"{MIN_SAMPLES_DIAGNOSTIC} and weight suggestions at "
                         f"{MIN_SAMPLES_WEIGHTS}. History cannot be backfilled, so this "
                         "fills in day by day once the recorder runs.")}

    current = {layer: LAYER_WEIGHTS[layer] for layer in LAYERS}
    # Undefined when conviction doesn't vary across the window — report None
    # rather than crashing or inventing a zero.
    overall_ic = _spearman(frame["conviction"], frame["label"])
    return {
        "status": "OK",
        "horizon": horizon,
        "n": n,
        "date_from": str(frame["as_of_date"].min()),
        "date_to": str(frame["as_of_date"].max()),
        "layer_ic": _layer_ic(frame),
        "calibration": _calibration_curve(frame),
        "veto_audit": _veto_audit(frame),
        "conviction_ic": round(overall_ic, 4) if overall_ic is not None else None,
        "weights": _learn_weights(frame, current),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
