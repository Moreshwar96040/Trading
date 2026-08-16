# Adaptive Alpha — design for a self-learning, explainable trading platform

**Status:** design document. Grounded in the existing codebase (Angular / Spring Boot /
FastAPI / Postgres), not a greenfield fantasy. Every section says what exists today,
what changes, and *why*.

**Design principles** (in priority order — when they conflict, higher wins):

1. **Correctness over cleverness.** A lookahead bug produces beautiful, fake results
   and is the most expensive mistake available in this domain.
2. **Explainable by construction.** The explanation is *derived from* the arithmetic,
   never generated after the fact to justify a number.
3. **Learn from outcomes, deploy by human approval.** No model rewrites its own
   decision rule in production.
4. **Every module independently testable**, with pure decision logic separated from I/O.
5. **Simplicity is a feature.** Complexity must earn its place with evidence.

---

## Part 0 — The three problems with the current design

Before proposing anything, the honest diagnosis of `Alpha Stack v1`:

| Problem | Consequence |
| --- | --- |
| **Weights are asserted, never validated** | 25/25/18/14/7/6/5 is a plausible prior with zero evidence behind it. Already being addressed by the calibration loop. |
| **Conviction conflates two different things** | "This setup is good" and "we are sure it's good" are collapsed into one number, then partially un-collapsed by an ad-hoc data-quality haircut on size. |
| **Layer collinearity is unmeasured** | `technical` and `momentum` are both trend factors. When they agree — which is most of the time — the score double-counts one underlying reason. |

A fourth, latent: **no model versioning**. When weights change, nothing records which
weight-set produced which trade, so attribution silently breaks the first time you
apply a suggestion.

---

## Part 1 — The core conceptual redesign

### 1.1 Split the single number into three

This is the most important change in the document.

| Quantity | Range | Question it answers | Drives |
| --- | --- | --- | --- |
| **Conviction** | 0–100 | *How good is this setup?* (expected edge) | Ranking |
| **Confidence** | 0–1 | *How sure are we of that estimate?* | Position size |
| **Consensus** | 0–1 | *Do the layers agree, or is this an average of a fight?* | Feeds confidence; surfaces conflict |

Today all three are smeared into one score plus a sizing fudge. Separating them is
what makes the system honest:

- Conviction 80 with confidence 0.4 → **a good-looking setup we don't trust**
  (thin data, layers disagreeing, model uncertain). Rank it high, size it small.
- Conviction 60 with confidence 0.9 → **a modest setup we're sure about.**
  Often the better *risk-adjusted* trade, and today's system cannot express that.

**Confidence composition** (each in 0–1, multiplied):

```
confidence = data_completeness × consensus × estimate_precision × regime_support

data_completeness  share of high-signal layers with real (non-neutral) inputs
consensus          1 - normalised dispersion of layer strengths (see 1.2)
estimate_precision narrower weight confidence intervals -> higher; from the learner
regime_support     how much labelled history exists for the CURRENT regime
```

`regime_support` is the guard against the regime-weights trap in §1.3: if we've only
seen 20 RISK_OFF days, confidence in a RISK_OFF-tuned score is *mechanically* low,
and size shrinks automatically. The system becomes cautious exactly where it is ignorant.

### 1.2 Consensus and conflict detection

```
strengths   s_1..s_7 (0..1), weights w_1..w_7
weighted mean   m = Σ w_i s_i / Σ w_i
dispersion      d = sqrt( Σ w_i (s_i - m)^2 / Σ w_i )      # weighted std
consensus       c = 1 - min(1, d / D_max)                   # D_max ~ 0.35, calibrated
```

**Conflict is a first-class output**, not a footnote. A `CONFLICT` flag when a
high-weight layer sits on the opposite side of the mean by more than a threshold, with
the specific pair named:

> *"Fundamentals strong (0.86) but news deteriorating (0.22) — quality trap risk.
> Conviction 71, confidence 0.41."*

This is the single most useful thing the UI can tell a discretionary trader, and it
falls out of arithmetic you already compute.

### 1.3 Regime-aware weights — and why the obvious approach is a trap

**You asked for regime-aware weights. I recommend a constrained version, and here is
the reasoning.**

Naive approach: fit a separate weight vector per regime. That is 7 weights × 5 regimes
= **35 parameters**, while simultaneously *dividing* your data. At ~250 labelled rows
per month, RISK_OFF might see 20 rows a year. Fitting 7 weights on 20 samples doesn't
produce regime intelligence; it produces noise with a confident label on it — and it
will be most wrong exactly when regimes shift, which is when it matters.

**Recommended: hierarchical (partially pooled) weights.**

```
w_regime = w_global + shrink(n_regime) × (w_regime_raw - w_global)

shrink(n) = n / (n + k)        # k ~ 200; shrink→0 with little data, →1 with lots
```

Each regime's weights start *identical to the global weights* and drift away only in
proportion to the evidence supporting the drift. With 20 RISK_OFF samples, the regime
weights are ~9% of the way toward the raw fit — essentially the global weights, which
is correct. With 800 samples, they're ~80% of the way, and by then the difference is
real.

**Bonus:** the amount a regime's weights have drifted is itself a finding worth
displaying — *"in CHOP, news matters 40% more than baseline (n=430)"* is an insight; a
raw per-regime fit on thin data is a liability.

**Second recommendation: collapse 5 regimes to 3 for weighting purposes**
(risk-on / neutral / risk-off). Five buckets is a resolution your data volume cannot
support for years. Keep 5 for display; use 3 for learning.

### 1.4 Orthogonalise the trend factors

`technical` and `momentum` measure overlapping things. Before learning weights, residualise:

```
momentum_residual = momentum - β·technical      # β from a rolling regression
```

Learn the weight on the *residual*. Interpretation becomes clean: "relative strength,
over and above what the technical layer already told us." Report the **VIF** for all
layers in the calibration UI — anything above ~5 means the weights are unstable and
should be read with suspicion.

---

## Part 2 — Module architecture

Nine modules. Each owns one responsibility, exposes a typed contract, and is testable
with no I/O. **The dependency rule: modules depend on contracts, never on each other's
internals.**

```
                    ┌──────────────────┐
                    │ 1 Feature Store  │  point-in-time correct inputs
                    └────────┬─────────┘
                             ▼
   ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │ 3 Model      │─▶│ 2 Scoring Engine │─▶│ 4 Reasoning      │
   │   Registry   │  │ conviction/conf  │  │   Engine         │
   └──────▲───────┘  └────────┬─────────┘  └──────────────────┘
          │                   ▼
          │          ┌──────────────────┐  ┌──────────────────┐
          │          │ 5 Risk & Sizing  │─▶│ 6 Portfolio      │
          │          └────────┬─────────┘  │   Constructor    │
          │                   ▼            └──────────────────┘
          │          ┌──────────────────┐
          │          │ 7 Execution      │  paper / broker-agnostic
          │          └────────┬─────────┘
          │                   ▼
   ┌──────┴───────┐  ┌──────────────────┐  ┌──────────────────┐
   │ 9 Governance │◀─│ 8 Learning       │◀─│ Outcome Ledger   │
   │   + approval │  │   Pipeline       │  │ (trades + labels)│
   └──────────────┘  └──────────────────┘  └──────────────────┘
```

### Module 1 — Feature Store (point-in-time)

**Responsibility:** given `(symbol, as_of_date)`, return exactly the features that
were knowable on that date. Nothing else in the system may read raw tables for scoring.

**Why this module exists and matters most:** you already discovered that conviction
history cannot be backfilled, because news digests and regime are current-state. That
is a symptom of not having a point-in-time layer. Without one, every future backtest
of the *composite* score is silently invalid.

**Contract:** `get_features(symbol_id, as_of) -> FeatureVector` — immutable, versioned,
with a `feature_set_version` stamp on every row it emits.

**Testing:** the critical test is a **lookahead assertion**: for a set of dates, verify
`get_features(s, T)` is byte-identical whether called on day T or replayed a year later.
Any drift is a leak.

**Verdict on existing code:** `screener_snapshot` is overwritten daily (no history), so
today only `ohlcv_daily`, `news_sentiment_history` and `strategy_signals` are
point-in-time. Making snapshots append-only is the single highest-value schema change
available.

### Module 2 — Scoring Engine

**Responsibility:** `FeatureVector + WeightSet -> Score{conviction, confidence, consensus, layers[], flags[]}`.

**Design:** a pure function. No DB, no network, no clock. Weights are *injected*, not
imported — which is what makes champion/challenger and backtesting possible at all.

**Testing:** property-based. Invariants that must always hold:
- conviction ∈ [0,100]; confidence ∈ [0,1]
- all-neutral inputs → conviction ≈ 50, confidence low
- monotonicity: raising any layer's strength, others fixed, never lowers conviction
- veto ⇒ size 0, regardless of every other input

**Change from today:** current scoring reaches into the session for fundamentals, news,
RS. That coupling is why it can't be replayed. Invert it: the caller assembles the
FeatureVector.

### Module 3 — Model Registry

**Responsibility:** every artefact that affects a decision is versioned and immutable:
weight sets, ML models, feature-set versions, regime definitions, thresholds.

**Schema sketch:** `model_versions(id, kind, params_json, created_at, created_by,
status ∈ {SHADOW, CHAMPION, RETIRED}, parent_id, metrics_json)`.

**Why:** without it, the first time you apply a weight suggestion, all prior attribution
becomes uninterpretable — you can no longer tell whether performance changed because the
market changed or because you changed the model. Every trade and every score row must
carry `model_version_id`.

**Testing:** a champion is unique per kind; retired versions are immutable; every
recorded score resolves to an existing version.

### Module 4 — AI Reasoning Engine

**Responsibility:** turn a Score into a human explanation — and be strict about what
"explanation" means.

**Two tiers, deliberately:**

- **Tier 1 — deterministic rationale (always).** Generated from the arithmetic:
  top contributors, top detractors, conflicts, confidence drivers, the veto reason.
  Free, instant, reproducible, and **cannot hallucinate** because it is a rendering
  of the numbers.
- **Tier 2 — LLM narration (optional, cached).** Takes the Tier-1 structured rationale
  as *input* and writes prose. Cached by fingerprint, never on the scoring path.

**The critical rule:** the LLM narrates an explanation that already exists; it never
*invents* one. An LLM handed a score and asked "why?" produces plausible rationalisation —
the most dangerous artefact this system could ship, because it is confident, fluent, and
unfalsifiable.

**Testing:** Tier 1 is pure → golden-file tests. Tier 2 gets a contract test: every
claim in the narration must reference a layer present in the structured input (checkable
by keyword extraction).

### Module 5 — Risk & Sizing

**Responsibility:** `Score + AccountState -> SizedOrder{qty, stop, target, reasons[]}`.

**Formula (evolution of today's):**

```
risk_budget = equity × risk_per_trade_pct
size_raw    = risk_budget / (entry - stop)          # classic risk-based sizing
size        = size_raw × f(conviction) × confidence × vol_adjust
```

**Change:** confidence enters as a **first-class multiplier** rather than today's
`data_quality` hack. Same intent, principled implementation.

**Add — asymmetric loss awareness.** A missed winner and a taken loser are not equally
costly to a retail account. Make the conviction→size curve configurable and *convex*
(slow at the bottom, steep at the top) rather than the current step function, which
creates cliff behaviour at exactly 55.0 and 75.0.

**Testing:** pure. Property tests — size never exceeds max-position%, never negative,
zero when vetoed, monotone in confidence.

### Module 6 — Portfolio Constructor

**Responsibility:** convert *N independent scores* into *one coherent book*.

**Honest scope control:** you asked for "portfolio optimization". For a single-user book
of ~8 positions, **mean-variance optimisation is the wrong tool** — it demands a
covariance matrix you can't estimate reliably from 8 names, and is notoriously unstable
(tiny input changes, wildly different allocations). It would add a lot of machinery and
make the book *less* predictable.

**Recommended instead — constraint-based construction:**
- sector cap (e.g. ≤35% of risk in one sector)
- pairwise correlation cap (reject a candidate with >0.8 rolling correlation to a holding)
- total open risk cap ("if every stop hits, I lose X%")
- correlation-adjusted conviction: penalise a name that duplicates existing exposure

This gets ~80% of diversification benefit with ~10% of the complexity and stays
explainable — "rejected: 0.86 correlated with your existing TCS position" is actionable;
"the optimiser preferred a different corner of the efficient frontier" is not.

**Testing:** pure given (candidates, holdings, correlation matrix). Deterministic, easily
property-tested.

### Module 7 — Execution

**Responsibility:** place and reconcile orders behind an interface, so paper / broker /
simulated are interchangeable.

**Contract:** `ExecutionVenue.place(order) -> Fill | Rejection`, plus `reconcile()`.

**Rule that must not be relaxed:** live venues stay **read-only** unless a human
explicitly enables trading, per-venue, with an audit record. Today's Upstox and MT5
integrations have no order functions at all — keep that property.

**Testing:** a `FakeVenue` with scriptable fills/rejections/partials. No test may reach a
real endpoint.

### Module 8 — Learning Pipeline

**Responsibility:** turn the outcome ledger into *candidate* model versions.

**Stages:** label → diagnose → fit → validate → register as SHADOW.

**Validation gates — a candidate is only registered if it passes all:**
1. n ≥ minimum (200 global; regime fits use shrinkage instead of a hard gate)
2. walk-forward out-of-sample IC > champion's, on the same folds
3. turnover penalty: if new weights churn >30% of the ranking for <10% IC gain, reject —
   churn costs real money in spreads and slippage
4. no coefficient flips sign without n ≥ 500 (sign flips on thin data are noise)
5. stability: bootstrap the fit 100× — if suggested weights vary more than ±20%, reject

**Never auto-promote.** SHADOW → CHAMPION is a human decision (Module 9).

**Testing:** synthetic data with a *planted* signal must be recovered; **pure noise must
produce no significant layers** (you already have this test — it is the most important
one in the suite); each gate must be independently triggerable.

### Module 9 — Governance & Approval

**Responsibility:** the human control plane.

- **Shadow mode:** challenger scores every setup alongside the champion; both are
  recorded; neither trades. After N weeks you compare *realised* attribution, not just IC.
- **Approval UI:** side-by-side champion vs challenger — weight deltas, OOS IC,
  turnover, stability, and the trades where they would have disagreed most.
- **One-click promote + instant rollback**, both audited.
- **Circuit breakers** (automatic, no approval needed to *stop*):
  drawdown > X% → size multiplier 0; data staleness > N days → refuse to score;
  regime flip → revert to global weights until regime support rebuilds.

**Testing:** promotion/rollback state machine; breakers fire on synthetic conditions.

---

## Part 3 — What I recommend *against* building

A principal engineer's job includes deleting scope. Each of these would cost weeks and
likely make the system worse:

| Not recommended | Why |
| --- | --- |
| Deep learning on price series | You have ~2 years × a few hundred symbols. DL needs orders of magnitude more, and destroys explainability — your stated top principle. |
| Mean-variance / Black-Litterman | Unstable at 8 positions; covariance unestimable; opaque. Constraint-based construction dominates here. |
| Reinforcement learning for sizing | Needs millions of episodes. You'll have hundreds of trades a year. |
| Sentiment from full article text | Marginal gain over headlines, large cost/latency increase. Headlines carry most of the signal. |
| Intraday / tick data | Different problem, different infrastructure. Don't mix horizons in one system. |
| Auto-promoting models | Violates your own principle, and chases the last month. |

---

## Part 4 — Phased roadmap (mapped to what exists)

| Phase | Work | Depends on | Status today |
| --- | --- | --- | --- |
| **A** | Point-in-time feature store; make snapshots append-only | — | **Not started — highest value** |
| **B** | Split scoring into pure function; inject weights | A | Partially (scoring exists, coupled) |
| **C** | Model registry + version stamping on every score/trade | B | Not started |
| **D** | Confidence + consensus + conflict detection | B | Not started |
| **E** | Deterministic rationale (Tier 1) | D | Not started |
| **F** | Outcome ledger + labelling | — | **Done** (`conviction_history`) |
| **G** | Diagnostics: IC, calibration curve, veto audit | F | **Done** |
| **H** | Global weight learning + validation gates | F, C | Partially (learner done, gates partial) |
| **I** | Hierarchical regime weights | H | Not started |
| **J** | Shadow mode + approval UI | C, H | Not started |
| **K** | Portfolio constraints | D | Not started |
| **L** | Orthogonalisation + VIF reporting | H | Not started |

**Recommended order: A → B → D → E → C → H → J → I → K.**

Rationale: A and B are enabling refactors — everything downstream is unreliable without
them. D and E deliver *visible user value early* (confidence and conflict warnings are
useful on day one, with no data accumulation required). Regime weights (I) come late
deliberately: they need the most data and carry the most overfitting risk.

---

## Part 5 — Per-module implementation prompts

Use these one at a time. Each is self-contained.

### Prompt A — Feature Store

> Implement a point-in-time feature store for the trading platform. Contract:
> `get_features(symbol_id, as_of_date) -> FeatureVector` returning only data knowable on
> that date, stamped with `feature_set_version`. Make `screener_snapshot` append-only
> (migration + backfill strategy) so historical indicator values survive. Nothing on the
> scoring path may read raw tables directly. Deliver: migration, repository, contract
> dataclass, and a **lookahead test** proving `get_features(s, T)` is identical when
> computed on day T versus replayed later. Explain any case where point-in-time
> reconstruction is impossible and how you degrade.

### Prompt B — Scoring Engine (pure)

> Refactor conviction scoring into a pure function:
> `score(features: FeatureVector, weights: WeightSet) -> Score`. No DB, network or clock
> access. Weights injected, never imported. `Score` carries conviction (0–100), per-layer
> contributions, and the raw strengths. Preserve current behaviour exactly — prove it with
> a characterisation test comparing old vs new output on 50 fixtures. Add property tests:
> range invariants, all-neutral → ~50, monotonicity per layer, veto ⇒ size 0.

### Prompt C — Model Registry

> Implement model versioning. Table `model_versions(id, kind, params_json, status ∈
> {SHADOW, CHAMPION, RETIRED}, parent_id, metrics_json, created_at, created_by)`.
> Stamp `model_version_id` on every `conviction_history` row and every autopilot trade.
> Enforce: exactly one CHAMPION per kind; retired versions immutable. Provide
> `get_champion(kind)` and `promote(version_id, approved_by)` with an audit trail.
> Include a migration that creates a version row for the current hardcoded weights and
> backfills existing rows to it.

### Prompt D — Confidence & Consensus

> Extend the scoring engine to emit **confidence** (0–1) and **consensus** (0–1) alongside
> conviction. confidence = data_completeness × consensus × estimate_precision ×
> regime_support. consensus = 1 − weighted dispersion of layer strengths, normalised.
> Emit a `CONFLICT` flag naming the specific opposing layers when a high-weight layer sits
> more than a threshold from the weighted mean. Replace the `data_quality` sizing hack with
> confidence as a first-class multiplier. Property tests: unanimous layers → consensus ≈ 1;
> a 50/50 split → consensus near 0; missing inputs reduce confidence but not conviction.

### Prompt E — Reasoning Engine (Tier 1 + Tier 2)

> Build a two-tier explanation engine. **Tier 1**: deterministic, from the Score alone —
> top 2 contributors, top 2 detractors, conflicts, confidence drivers, veto reason, as a
> structured `Rationale` object. Pure; golden-file tested. **Tier 2**: an LLM that takes
> the Tier-1 `Rationale` as input and writes prose — cached by fingerprint, never on the
> scoring path, and it may not introduce any layer not present in the input. Add a
> contract test enforcing that.

### Prompt F — Learning Pipeline with validation gates

> Extend the calibration learner into a gated pipeline producing SHADOW model versions.
> Gates: (1) n ≥ 200, (2) walk-forward OOS IC beats champion on identical folds,
> (3) turnover penalty — reject >30% ranking churn for <10% IC gain, (4) no coefficient
> sign flip below n=500, (5) bootstrap stability within ±20% over 100 resamples. Each gate
> independently testable and independently reportable ("rejected: failed stability").
> Never auto-promote.

### Prompt G — Hierarchical regime weights

> Implement partially-pooled regime weights:
> `w_regime = w_global + (n/(n+k)) × (w_regime_raw − w_global)`, k≈200. Collapse the five
> regimes to three (risk-on / neutral / risk-off) for learning; keep five for display.
> Expose `regime_support` (labelled sample count for the current regime) so the scoring
> engine can feed it into confidence. Tests: with n=0 regime weights equal global exactly;
> as n grows they approach the raw fit; regime weights always sum to 100.

### Prompt H — Portfolio Constructor

> Implement constraint-based portfolio construction (explicitly **not** mean-variance).
> Given candidates, current holdings and a rolling correlation matrix, apply: sector risk
> cap, pairwise correlation cap, total open-risk cap, and correlation-adjusted conviction.
> Return accepted candidates each with a human-readable reason for acceptance or rejection
> ("rejected: 0.86 correlated with TCS"). Pure function; property-tested.

### Prompt I — Governance, shadow mode, circuit breakers

> Implement shadow evaluation: the challenger scores every setup alongside the champion,
> both recorded, neither traded. Build an approval UI comparing weight deltas, OOS IC,
> turnover, stability, and the top-10 disagreements. One-click promote and rollback, both
> audited. Add circuit breakers that need no approval to *stop*: drawdown limit → size 0;
> data staleness → refuse to score; regime flip → revert to global weights until support
> rebuilds.

---

## Part 6 — How to know it's working

Track these, not just P&L:

| Metric | Target | Why |
| --- | --- | --- |
| Conviction IC (10d) | > 0.03 sustained | Does the score predict at all? |
| Calibration monotonicity | 75+ band > 55–75 > 40–55 | Do higher scores earn more? |
| Confidence separation | High-confidence trades beat low-confidence | Is confidence meaningful? |
| Champion vs shadow | Champion ≥ shadow after promotion | Are promotions improvements? |
| Explanation faithfulness | 100% of narration claims traceable to layers | Is it explaining or rationalising? |
| Turnover | < 30% ranking change per reweight | Are we churning value away? |

**The honest failure condition:** if after 6 months conviction IC sits at ~0.00 and the
calibration curve is flat, the correct conclusion is that *the layers don't predict* —
and no amount of reweighting, regime conditioning or extra ML will rescue it. The system
should be capable of telling you that clearly. A platform that can't return a negative
verdict about itself isn't a measurement instrument; it's a persuasion machine.

---

## Part 7 — Implementation status (as built)

Every phase in Part 4 is now implemented. What follows is what actually shipped,
including the places where the build deviated from this document — those
deviations are the interesting part.

### Phase 1 — Conviction, confidence, consensus, explanation

| Piece | Where |
| --- | --- |
| Confidence = completeness x consensus x regime support | `app/scoring/engine.py` |
| Consensus from weighted layer dispersion | `app/services/conviction_service.py` |
| Conflict detection between materially-weighted layers | `app/scoring/engine.py` |
| Deterministic reasoning (Tier 1) | `app/ai/reasoning.py` |

### Phase 2 — Pure scoring engine + model registry

| Piece | Where |
| --- | --- |
| Typed contracts (`ScoringInputs`, `WeightSet`, `LayerScore`, `Score`) | `app/scoring/contracts.py` |
| Pure `score(inputs, weights)` — no DB, no clock, no network | `app/scoring/engine.py` |
| Model registry, one champion per kind (DB-enforced) | `app/services/model_registry.py`, migration V22 |
| Point-in-time feature store | `app/features/store.py` |

### Phase 3 — Validation gates + hierarchical regime weights

| Piece | Where |
| --- | --- |
| Five gates: sample size, OOS IC, turnover, sign flip, bootstrap stability | `app/ai/gates.py` |
| Partially-pooled regime weights, `w = w_global + n/(n+200)(w_raw - w_global)` | `app/ai/calibration.py::learn_regime_weights` |
| Gated proposal that registers SHADOW only | `app/ai/calibration.py::propose_weights` |
| `POST /internal/conviction/propose`, `GET /internal/conviction/regime-weights` | `app/api/routes.py` |

**Deviation:** the design implies five regimes each get their own weights. Learning
collapses them to three buckets (risk-on / neutral / risk-off) because seven weights
across five regimes divides thin data five ways to estimate 35 parameters. Display
still shows all five.

### Phase 4 — Shadow mode, governance, circuit breakers, portfolio construction

| Piece | Where |
| --- | --- |
| Shadow evaluation by replay | `app/ai/shadow.py` |
| Circuit breakers (drawdown, loss streak, IC collapse, stale data, dead labels) | `app/services/circuit_breakers.py` |
| Constraint-based portfolio constructor | `app/services/portfolio_constructor.py` |
| Promotion / rollback UI with mandatory attribution | `frontend/.../ai-page.component.ts` |

**The significant deviation — shadow mode by replay, not by recording.**

Prompt I specifies that the challenger scores every setup alongside the champion each
day, with both recorded. We do not do that, and the reason is worth stating: conviction
is a *linear* function of the layer strengths, and the strengths are already persisted
in `conviction_history`. A shadow conviction is therefore just a weighted sum over rows
we recorded anyway.

Three consequences, all improvements:

* no second table, no second daily job, nothing extra to keep alive;
* a challenger registered today is evaluated on **all** history, not only on days
  after registration — which turns a six-month wait into an immediate answer;
* champion and challenger see byte-identical inputs, so any difference is
  attributable to the weights alone.

The limit is real and is enforced rather than assumed: replay is only valid for
challengers that change *weights*. A challenger that changes how a layer is
*computed* produces different strengths, and those cannot be reconstructed.
`evaluate_candidate` refuses any non-`WEIGHTS` version with an explicit reason
instead of quietly returning a wrong number.

**Circuit breakers halt entries, never liquidate.** Forced selling on a metric turns
a bad week into a bad year; open positions keep their stops and exit on their own
terms. Reset is manual — an auto-resetting breaker just lets the same failure
repeat on a timer.

**The portfolio constructor is greedy under hard caps, not optimised.** A
mean-variance optimiser needs expected returns and a covariance matrix, both
estimated from the same short, noisy history, and it then concentrates precisely
where the estimation error is largest. Greedy selection under sector, correlation,
per-name and total-risk caps is worse in theory and considerably better at this
data scale. Risk is budgeted by distance-to-stop, not by slot count, so a quiet
stock and a volatile one no longer count the same.

### Test coverage

402 Python tests. The learning-pipeline suites are:
`test_gates.py` (16), `test_weight_proposal.py` (11), `test_shadow.py` (12),
`test_circuit_breakers.py` (19), `test_portfolio_constructor.py` (19),
plus `test_scoring_engine.py`, `test_calibration.py` and `test_feature_store.py`.

Each gate and each breaker is independently triggerable — a rejection that cannot be
traced to one named check is not an explanation.

### What is still deliberately absent

* **No automatic promotion.** Passing every gate and winning the replay earns a
  challenger the right to be *watched*. Going live needs a named human, and it is
  recorded in `model_version_audit`.
* **No live trading.** The autopilot is paper-only; there is no live code path.
* **No forward shadow recording** for non-weight challengers — needed before the
  first challenger that changes a layer's computation.

---

## Part 8 — Phase 5: autonomous, regime-conditional adaptation

The Alpha Stack now adjusts its own weights, and chooses them by market
condition. This is the capability the original brief asked for, and it was the
one thing genuinely missing after Phase 4.

### What changed

| Piece | Where |
| --- | --- |
| Regime-scoped weight registry (one champion per scope) | migration V23, `model_registry.py` |
| Live scoring picks weights by today's regime | `conviction_service.py::alpha_stack` |
| Drift guard bounded to the human anchor | `app/ai/gates.py::gate_drift_bounded` |
| Frozen safety parameters | `app/ai/gates.py::gate_frozen_params_untouched` |
| Autonomous adaptation loop | `app/services/auto_adapt.py` |
| Auto-rollback of a failing automatic model | `circuit_breakers.py::auto_rollback_if_failing` |
| Weekly scheduler job (Sunday 06:00) | `scheduler.py::_run_adaptation_job` |
| Self-adjustment UI + change log | `frontend/.../ai-page.component.ts` |

### How a change happens now

1. Weekly, per scope (global, risk_on, neutral, risk_off).
2. Circuit breakers must be clear — no learning from a period already flagged broken.
3. Refit on that scope's own labelled history (>= 200 rows).
4. Seven gates: sample size, OOS IC, turnover, sign flip, stability, **drift
   bound**, **frozen params**.
5. Shadow replay must beat the live champion by >= 0.005 IC on identical history.
6. Promote — automatically, no human — and log why.
7. Daily, auto-rollback reverts a learner-promoted champion whose rolling IC has
   collapsed, back to the last human-approved set.

### The bound that matters most: anchoring

Drift is measured from the last **human-approved** weight set, never from the
incumbent. This is the difference between a bound and the appearance of one.
Against the incumbent, ten automatic promotions of +9 points each are each
individually legal and collectively land 90 points from anything anyone reviewed.
Against the anchor, the *total* is capped. Automatic promotions deliberately do
not re-anchor; only a human promotion does.

Concretely: no layer may move more than 10 points from your baseline, none may
fall below 2 points, and the news veto is not a weight and is not learnable — a
rule whose value comes from being non-negotiable must not be negotiable.

### A real bug this phase surfaced

The stability gate originally judged each layer by coefficient of variation
alone. On seven layers where several carry little weight, the smallest, noisiest
layer always has a huge CV — so the gate would have blocked essentially every
promotion in production. That is not caution; it is paralysis wearing caution's
clothes, and it would have looked like "the system never adapts" rather than like
a bug.

Fixed by requiring instability to be both proportional *and* material: a layer
fails only if its CV exceeds 20% **and** it moves more than 4 weight points.
A 5-point layer wobbling +/-1.5 points no longer vetoes a good fit; a 25-point
layer swinging +/-12 still does.

### What is still true

* **Paper only.** No live trading path exists.
* **Off by default.** `AUTO_ADAPT_ENABLED=false`.
* **Every outcome is logged**, including the decisions to do nothing — otherwise
  "why hasn't it adapted?" is unanswerable.
* **One-step revert.** However many automatic changes have accumulated,
  `revert_to_anchor` returns a scope to your weights in a single call.
* **Your promotions are never overridden.** Auto-rollback only reverts models the
  learner promoted. If you promoted something and it is losing, reversing it is
  your call.

### The honest limitation

None of this makes the learner *correct*. It makes it bounded, reversible and
legible. Those are achievable by engineering; correctness is decided by whether
the seven layers predict anything, which only real forward data can answer. If
the conviction IC sits near zero after six months, the right conclusion is that
the layers do not predict — and no amount of adaptive reweighting will rescue that.
