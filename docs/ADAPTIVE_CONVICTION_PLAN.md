# Adaptive Conviction — learning the Alpha Stack's weights from its own results

## The idea

Today the Alpha Stack's weights are **asserted**: technical 25, quality 25, news 18,
momentum 14, ml 7, macro 6, regime 5. They're a reasonable prior, but nothing has ever
checked them against what actually happened. This plan closes that loop:

> Score setups → record the score → observe the outcome → measure which layers
> actually predicted it → **suggest** corrected weights → human approves.

The output is not a black box that trades for you. It's a report that says things like:

> *"News layer: IC 0.01 over 240 samples — no evidence it predicts anything.
> Suggested weight 18 → 11. Quality layer: IC 0.13 (p < 0.01). Suggested 25 → 31."*

---

## Blocking finding: we capture none of this today

`alpha_stack()` computes conviction and the seven-layer breakdown **in memory and throws
it away**. There is no conviction history table and no code path that writes one.

Consequences, in order of importance:

1. **We cannot backfill.** Conviction depends on the *cached news digest*, sentiment
   trend and market regime **as they were on that day**. Those are current-state, not
   versioned. Re-running the scorer over history would score today's news against
   yesterday's prices — a lookahead bug that would produce beautiful, fake results.
2. **The clock starts when Phase 0 ships.** No shortcut exists.
3. **Partial exception:** `news_sentiment_history` (V16) *does* keep daily per-symbol
   sentiment, and `strategy_signals` keeps `as_of_date`. So a limited technical+quality
   backtest is possible later — but not the full composite. Not worth the complexity now.

**Therefore Phase 0 is non-negotiable and must ship first.**

---

## Phase 0 — Record what we score (foundation)

New table `conviction_history`, one row per scored setup per day:

| column | why |
| --- | --- |
| `symbol_id`, `as_of_date` | primary key |
| `conviction`, `verdict`, `risk_multiplier` | the decision made |
| `technical_strength` … `regime_strength` (7 cols) | **the features to learn from** |
| `news_veto`, `has_live_signal`, `atr_pct`, `data_quality` | context/controls |
| `regime_code`, `sector` | for regime- and sector-split analysis |
| `close` | entry reference for computing forward returns |

Written by the existing pre-market scheduler job, for **every** symbol scored — not only
the ones traded. That matters: evaluating only taken trades creates selection bias, and
you'd be measuring your discretion rather than the model.

Effort: one migration, one model, ~30 lines in the scheduler, tests.
**Value on day one: zero. Value in three months: everything.**

---

## Phase 1 — Label the outcomes

A job that, for each `conviction_history` row older than N trading days, computes the
forward return from `ohlcv_daily`:

- `fwd_return_5d`, `fwd_return_10d`, `fwd_return_20d` (% from entry close)
- `mfe_pct` / `mae_pct` — best and worst excursion, so we can tell "right but stopped out"
  from "simply wrong"
- `regime_at_entry` carried forward

Labels are pure price arithmetic — no lookahead risk, and fully recomputable.

---

## Phase 2 — Diagnostics (useful at ~50 samples)

This is where value starts arriving, well before any model is fitted.

**a. Per-layer Information Coefficient.** Spearman rank correlation between each layer's
strength and forward return, with sample size and p-value. In equities an IC of 0.03–0.05
is genuinely useful; 0.10+ is strong. Near zero with a large n means the layer is noise.

**b. Conviction calibration curve.** Bucket by band (<40, 40–55, 55–75, 75+) and show mean
forward return and hit rate per bucket. The question it answers: *do 75+ setups actually
outperform 55–75 ones?* If the curve is flat, the score isn't discriminating and no
reweighting will save it — that's a finding worth having early.

**c. Veto audit.** How did news-vetoed setups actually perform? If they'd have been fine,
the veto is costing money.

---

## Phase 3 — Learn the weights

**Model:** Ridge regression of forward return on the seven layer strengths.
Deliberately linear — it mirrors the existing scoring formula exactly, so the learned
coefficients translate directly into weights you can read and argue with. A gradient-boosted
model would fit better and tell you nothing actionable.

```
fwd_return_10d ≈ β_technical·s_technical + … + β_regime·s_regime
weights ∝ normalise(max(β, 0)) × 100
```

**Guardrails against fooling ourselves** — these are the point of the phase, not decoration:

- **Walk-forward only.** Train months 1–3, test month 4; roll. Never a random split —
  random splits on time series leak the future backwards.
- **Minimum n before any suggestion is shown.** 200 rows, hard gate.
- **Shrink toward the prior:** `suggested = 0.7 × current + 0.3 × learned`. The prior
  encodes trading logic; the data encodes noise plus a little signal. Never jump.
- **Confidence intervals.** If a coefficient's CI spans zero, report "no evidence" and
  leave the weight alone.
- **Regime split.** Fit separately for RISK_ON vs risk-off. If weights differ sharply,
  that's a finding (regime-conditional weighting), not a bug.
- **Negative coefficients are a red flag, not a licence.** If quality scores *negatively*,
  the honest response is to investigate the data, not to invert the layer.

---

## Phase 4 — Suggest, don't apply

A **Model Calibration** panel on the AI & ML page:

- Layer table: current weight, IC, n, p-value, suggested weight, delta
- Calibration curve chart
- One-click "apply suggested weights" writing to config — **human-approved, reversible,
  and version-stamped** so you can attribute a change in results to a change in weights

Auto-applying is explicitly out of scope. A system that silently rewrites its own decision
rule based on a few hundred noisy samples is how you get a model that chases the last month.

---

## Timeline (honest)

| When | State |
| --- | --- |
| Ship Phase 0+1 | Recording. No insight yet. |
| ~4–6 weeks (~100 rows) | Calibration curve and veto audit become readable |
| ~3 months (~250 rows) | Per-layer IC meaningful; first weight suggestions |
| ~6 months | Walk-forward validation has enough folds to be trusted |

With ~10 scored setups a day, ~250 rows/month. Seven parameters need a few hundred rows
minimum before the fit is anything but noise.

---

## What could make this fail (and the mitigation)

| Risk | Mitigation |
| --- | --- |
| Overfitting 7 params to few samples | Ridge + shrinkage + hard n gate + walk-forward |
| Regime dependence — weights learned in a bull market | Regime-split fits; re-check quarterly |
| Selection bias from only scoring traded names | Record **all** scored setups |
| Layer collinearity (technical ↔ momentum both trend) | Report VIF; consider orthogonalising momentum |
| Label noise — 1-day returns are ~all noise | Prefer 10-day horizon as the primary label |
| Chasing the last month | Shrinkage, plus never auto-apply |

---

## Open decisions

1. **Primary horizon** — 5d / 10d / 20d as the label the weights optimise for.
2. **Scope of recording** — every active symbol daily (richest, biggest table), or only
   symbols with a live signal (smaller, but biased toward one technical state)?
3. **Success metric** — maximise forward return, or hit rate, or return/volatility?
4. **Auto-apply ever?** My recommendation is no; suggestion-only, permanently.
