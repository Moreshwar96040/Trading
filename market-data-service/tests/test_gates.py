"""Validation gates.

Every gate must be independently triggerable — if a rejection cannot be traced
to one named gate, "the model was rejected" is not an explanation, it is a
shrug. So each test fails exactly one gate and asserts the summary names it.
"""
from app.ai.gates import (MAX_TURNOVER, MIN_SAMPLES, SIGN_FLIP_MIN_SAMPLES,
                          evaluate_all, gate_no_sign_flip, gate_oos_improves,
                          gate_sample_size, gate_stability, gate_turnover)

LAYERS = ("technical", "quality", "news", "momentum", "ml", "macro", "regime")
BASE = {"technical": 25.0, "quality": 25.0, "news": 18.0, "momentum": 14.0,
        "ml": 7.0, "macro": 6.0, "regime": 5.0}


# ---------- sample size ----------

def test_sample_size_blocks_thin_data():
    r = gate_sample_size(MIN_SAMPLES - 1)
    assert not r.passed and "need" in r.reason


def test_sample_size_passes_at_the_boundary():
    assert gate_sample_size(MIN_SAMPLES).passed


# ---------- out-of-sample IC ----------

def test_oos_blocks_when_no_folds_could_be_scored():
    """No OOS number at all is a failure, not a pass by default."""
    assert not gate_oos_improves(None, 0.02).passed


def test_oos_requires_beating_the_incumbent():
    assert not gate_oos_improves(0.01, 0.03).passed
    assert gate_oos_improves(0.04, 0.03).passed


def test_oos_with_no_champion_only_needs_to_be_positive():
    assert gate_oos_improves(0.02, None).passed
    assert not gate_oos_improves(-0.01, None).passed


# ---------- turnover ----------

def test_turnover_blocks_churn_that_the_ic_gain_cannot_pay_for():
    current = list(range(60))
    reversed_scores = list(reversed(current))       # ~200% churn
    r = gate_turnover(current, reversed_scores, ic_gain=0.001)
    assert not r.passed and r.detail["turnover"] > MAX_TURNOVER


def test_large_ic_gain_buys_the_right_to_churn():
    current = list(range(60))
    r = gate_turnover(current, list(reversed(current)), ic_gain=0.25)
    assert r.passed


def test_identical_rankings_are_zero_turnover():
    scores = [3.0, 1.0, 2.0, 5.0, 4.0] * 10
    r = gate_turnover(scores, scores, ic_gain=0.0)
    assert r.passed and abs(r.detail["turnover"]) < 1e-9


# ---------- sign flip ----------

def test_sign_flip_blocked_on_thin_data():
    candidate = {**BASE, "news": -3.0}
    r = gate_no_sign_flip(BASE, candidate, n=300)
    assert not r.passed and r.detail["flipped"] == ["news"]


def test_sign_flip_allowed_once_the_evidence_is_deep():
    candidate = {**BASE, "news": -3.0}
    assert gate_no_sign_flip(BASE, candidate, n=SIGN_FLIP_MIN_SAMPLES).passed


def test_shrinking_a_weight_is_not_a_sign_flip():
    assert gate_no_sign_flip(BASE, {**BASE, "news": 1.0}, n=250).passed


# ---------- stability ----------

def test_stability_blocks_a_fit_that_lurches_under_resampling():
    unstable = [{**BASE, "quality": 5.0 + 40.0 * (i % 2)} for i in range(40)]
    r = gate_stability(unstable)
    assert not r.passed and r.detail["worst_layer"] == "quality"


def test_stability_passes_when_resamples_agree():
    steady = [{**BASE, "quality": 25.0 + 0.2 * (i % 3)} for i in range(40)]
    assert gate_stability(steady).passed


def test_a_small_layer_wobbling_does_not_veto_the_whole_fit():
    """The 5-point regime layer swinging +/-1.5 points has a huge CV and changes
    almost nothing. Judging on the ratio alone would let the least important
    layer block every promotion forever."""
    jittery = [{**BASE, "regime": 3.5 + 3.0 * (i % 2)} for i in range(40)]
    r = gate_stability(jittery)
    assert r.passed, r.reason


def test_a_large_layer_moving_the_same_absolute_amount_still_fails():
    """Same points of movement, but on a weight that actually drives the score —
    and now proportionally erratic enough to matter."""
    swinging = [{**BASE, "quality": 20.0 + 12.0 * (i % 2)} for i in range(40)]
    assert not gate_stability(swinging).passed


def test_stability_abstains_rather_than_guessing_on_few_resamples():
    """Too few bootstraps is 'cannot judge', not 'unstable' — a gate that fails
    on missing evidence would block every early candidate for the wrong reason."""
    assert gate_stability([BASE, BASE]).passed


# ---------- combination ----------

def test_one_failure_sinks_the_candidate_and_is_named():
    out = evaluate_all([gate_sample_size(1000),
                        gate_oos_improves(0.05, 0.01),
                        gate_sample_size(3)])
    assert not out["passed"]
    assert "sample_size" in out["failed"]
    assert out["summary"].startswith("rejected: failed")


def test_all_pass_reads_as_challenger_ready():
    out = evaluate_all([gate_sample_size(1000), gate_oos_improves(0.05, 0.01)])
    assert out["passed"] and out["failed"] == []
    assert "challenger" in out["summary"]
