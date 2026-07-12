"""Confluence scoring for AI Trade Ideas (Phase D)."""
from app.ai.ideas import IdeaInputs, score_idea


def test_all_bullish_evidence_stacks():
    score, reasons = score_idea(IdeaInputs(
        predicted_return_pct=1.2, direction="UP", test_accuracy=60.0,
        entry_signals=["Ichimoku Breakout"], regime="STRONG_UPTREND",
        roe_pct=22.0, pe_trailing=18.0))
    assert score > 6
    assert len(reasons) == 5


def test_down_prediction_and_downtrend_subtract():
    score, _ = score_idea(IdeaInputs(
        predicted_return_pct=-0.8, direction="DOWN", test_accuracy=60.0,
        regime="DOWNTREND"))
    assert score < 0


def test_weak_model_gets_no_vote():
    weak, _ = score_idea(IdeaInputs(direction="UP", predicted_return_pct=1.0,
                                    test_accuracy=45.0))          # below coin flip
    assert weak == 0.0


def test_higher_accuracy_weighs_more():
    lo, _ = score_idea(IdeaInputs(direction="UP", predicted_return_pct=1.0, test_accuracy=52.0))
    hi, _ = score_idea(IdeaInputs(direction="UP", predicted_return_pct=1.0, test_accuracy=72.0))
    assert hi > lo > 0


def test_entry_signals_capped_at_two():
    many = score_idea(IdeaInputs(entry_signals=["a", "b", "c", "d"]))[0]
    two = score_idea(IdeaInputs(entry_signals=["a", "b"]))[0]
    assert many == two == 4.0


def test_exit_signal_penalizes():
    score, reasons = score_idea(IdeaInputs(entry_signals=["a"], exit_signals=["b"]))
    assert score == 0.0
    assert any("EXIT" in r for r in reasons)
