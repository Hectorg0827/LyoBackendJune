"""Activity-first staging policy: never trade away grading or teaching evidence."""

from lyo_app.ai_classroom.teaching_prompt import teaching_prompt


def test_orientation_opens_with_actionable_example_not_introduction():
    prompt = teaching_prompt("orient")
    assert "FIRST beat must expose a concrete worked setup immediately" in prompt
    assert "Do not require the learner to listen to every line of narration" in prompt
    assert "modelled steps still" in prompt


def test_mobile_visual_policy_uses_manipulation_without_claiming_mastery():
    prompt = teaching_prompt("guided")
    assert "make the first useful action obvious" in prompt
    assert "Manipulation is exploratory, never a grade" in prompt
    assert "server-owned learner task" in prompt
    assert "one small meaningful decision" in prompt


def test_diagnostic_stays_learner_safe_and_fast():
    prompt = teaching_prompt("diagnose")
    assert "one tap" in prompt
    assert "Teach NOTHING yet" in prompt
    assert "must test ONLY what this learner has been taught." not in prompt


def test_backend_evidence_requirements_remain_intact():
    for move in ("guided", "faded", "independent", "transfer"):
        prompt = teaching_prompt(move)
        assert "must test ONLY what this learner has been taught." in prompt
        assert "Never repeat a previous question" in prompt
