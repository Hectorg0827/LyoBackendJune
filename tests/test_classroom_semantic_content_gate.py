"""Reject checkable meaning failures and expose a review hook for the rest."""

from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_teaching import (
    AdaptiveTeacher, GuidedState, LearningTask, TaskOption, TeachingContractError,
    TeachingUnavailable, validate_semantic_content,
)
from tests.adaptive_fixtures import ScriptedTeacher, context, plan, probe, task
from tests.export_guided_fixtures import visuals


@pytest.mark.parametrize("bad_label", ["ONE-HALF!!!", "one half"])
def test_equivalent_visible_options_are_rejected(bad_label):
    choice = task("choose").model_dump()
    choice["options"][1]["label"] = bad_label
    with pytest.raises(ValueError, match="distinct visible answers"):
        LearningTask.model_validate(choice)


def test_two_distractors_cannot_claim_the_same_misconception_under_different_punctuation():
    diagnostic = probe().model_dump()
    diagnostic["options"][2]["misconception"] = "More pieces means MORE each"
    with pytest.raises(ValueError, match="distinct misconceptions"):
        LearningTask.model_validate(diagnostic)


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["question"])
async def test_visible_answer_is_repaired_before_the_probe_is_shown(location):
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    valid = ScriptedTeacher()._turn(ctx, state, "diagnose")
    invalid = valid.model_dump()
    answer = valid.task.options[0].label
    if location == "question":
        invalid["task"]["question"] = f"{answer} is bigger. Which piece is bigger?"
    else:
        invalid[location] = f"{answer} is bigger. Which piece is bigger?"
    generate = AsyncMock(side_effect=[
        type(valid).model_validate(invalid), valid,
    ])
    result = await AdaptiveTeacher(generate).turn(ctx, state, "diagnose")
    assert result.task.question == valid.task.question
    assert generate.await_count == 2
    repair = generate.await_args.args[1]["repair"]
    assert "reveals the answer" in repair and answer not in repair


@pytest.mark.parametrize("location", ["board", "visual"])
def test_visual_description_and_open_answer_are_subject_to_the_same_gate(location):
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "transfer")
    if location == "board":
        turn.board_content = turn.task.example_answer
    else:
        turn.visual = visuals()[1].model_copy(update={"description": turn.task.example_answer})
    with pytest.raises(ValueError, match="reveals the answer"):
        validate_semantic_content(turn)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["filler distractor", "mislabelled gap", "fluent wrong teaching"])
async def test_optional_second_judge_can_reject_meaning_the_schema_cannot_prove(failure):
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    move = "orient" if failure == "fluent wrong teaching" else "diagnose"
    candidate = ScriptedTeacher()._turn(ctx, state, move)
    if failure == "filler distractor":
        candidate.task.options[1].label = "The magical pizza is an elephant"
    elif failure == "mislabelled gap":
        candidate.task.options[1].gap = "near_miss"
    else:
        candidate.demonstration[0].speech = "More equal cuts always produce a larger piece."
    generate = AsyncMock(return_value=candidate)
    judge = AsyncMock(return_value=False)
    with pytest.raises(TeachingUnavailable):
        await AdaptiveTeacher(generate, semantic_judge=judge).turn(ctx, state, move)
    assert generate.await_count == judge.await_count == 2
    assert judge.await_args.args[0] == move
    assert judge.await_args.args[1].title == state.unit.title
    assert state.completed == [] and state.outbox == []


def test_a_short_numeric_answer_in_the_scenario_is_data_not_answer_leakage():
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "faded")
    turn.task.example_answer = "4"
    turn.board_content = "Four equal cuts in the first bar and eight in the second."
    validate_semantic_content(turn)


@pytest.mark.parametrize("answer", ["4", "4/8", "4 slices"])
@pytest.mark.parametrize("scenario", [
    "Pizza D has 8 equal slices. Half of the 8 slices: 8 ÷ 2 = 4.",
    "A pizza has 8 equal slices. To cover half the pizza, we shade 4 slices.",
])
def test_faded_half_of_eight_cannot_show_its_missing_numerator(answer, scenario):
    """This exact leaked checkpoint reached the live classroom after retries."""
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "faded")
    turn.task.example_answer = answer
    turn.task.scenario = scenario
    turn.task.question = "Complete 1/2 = ?/8."
    turn.task.response_hint = "Type the missing numerator."
    with pytest.raises(TeachingContractError, match="reveals the answer"):
        validate_semantic_content(turn)


@pytest.mark.parametrize(("scenario", "question"), [
    (
        "A pizza is cut into 8 equal slices. To cover half we shade 4 slices. "
        "Step 1: total = 8. Step 2: half of 8 = 4.",
        "Which number completes 1/2 = ?/8?",
    ),
    (
        "Pizza B has 8 equal slices total. Pizza B has 4 shaded slices.",
        r"Complete $\frac{2}{4} = \frac{\text{?}}{8}$.",
    ),
])
def test_numeric_choice_is_not_exempt_from_worked_answer_leakage(scenario, question):
    """Options 2, 4, 8 do not justify announcing 4 in the scenario."""
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "faded")
    turn.task = LearningTask(
        kind="choose", response_format="choice",
        scenario=scenario,
        question=question,
        response_hint="Choose the missing numerator.",
        criteria=["Chooses the number of eighths equal to one half"],
        example_answer="4",
        options=[
            TaskOption(id="a", label="2", correct=False,
                       feedback="Two eighths cover less than half.",
                       misconception="uses the numerator of one half"),
            TaskOption(id="b", label="4", correct=True,
                       feedback="Four eighths are equivalent to one half."),
            TaskOption(id="c", label="8", correct=False,
                       feedback="Eight eighths would cover the whole pizza.",
                       misconception="uses the total number of pieces"),
        ],
    )
    with pytest.raises(TeachingContractError, match="reveals the answer"):
        validate_semantic_content(turn)


@pytest.mark.parametrize("answer", ["4/8", r"\frac{4}{8}"])
def test_latex_numerator_blank_catches_precomputed_answer(answer):
    """The actual classroom printed a LaTeX fraction, not ASCII `?/8`."""
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "faded")
    turn.task.example_answer = answer
    turn.task.scenario = "Pizza D has 8 equal slices. Half of eight: 8 ÷ 2 = 4."
    turn.task.question = r"Complete $\frac{1}{2} = \frac{\text{?}}{8}$."
    turn.task.response_hint = "Type the missing numerator."
    with pytest.raises(TeachingContractError, match="reveals the answer"):
        validate_semantic_content(turn)


def test_latex_numerator_blank_rejects_passively_shaded_answer():
    """`4 shaded slices` is a solved result when the answer is 4/8."""
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "faded")
    turn.task.example_answer = "4/8"
    turn.task.scenario = (
        "Pizza B has 8 equal slices total. To match two of four on Pizza A, "
        "Pizza B has 4 shaded slices."
    )
    turn.task.question = r"Complete $\frac{2}{4} = \frac{\text{?}}{8}$."
    turn.task.response_hint = "Type the missing numerator."
    with pytest.raises(TeachingContractError, match="reveals the answer"):
        validate_semantic_content(turn)


def test_latex_numerator_blank_allows_unsolved_numeric_setup():
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "faded")
    turn.task.example_answer = "4/8"
    turn.task.scenario = "Pizza A has 4 equal slices; Pizza B has 8 equal slices."
    turn.task.question = r"Complete $\frac{2}{4} = \frac{\text{?}}{8}$."
    turn.task.response_hint = "Type the missing numerator."
    validate_semantic_content(turn)


def test_given_numeric_operand_remains_allowed_when_no_result_is_worked_out():
    """Do not ban the digit 4 itself: concrete problems require numeric data."""
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "faded")
    turn.task.example_answer = "4/8"
    turn.task.scenario = (
        "Pizza A has 4 slices, and Pizza D has 8 equal slices. "
        "We want to represent one half of Pizza D."
    )
    turn.task.question = "Complete 1/2 = ?/8."
    turn.task.response_hint = "Type the missing numerator."
    validate_semantic_content(turn)


def test_independent_prompt_requires_a_new_computation_not_a_new_story_wrapper():
    from lyo_app.ai_classroom.teaching_prompt import teaching_prompt

    prompt = teaching_prompt("independent")
    assert "change the actual quantities and missing result" in prompt
    assert "half of eight slices" in prompt


@pytest.mark.asyncio
async def test_leaked_faded_result_is_rejected_then_reauthored_before_display():
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    valid = ScriptedTeacher()._turn(ctx, state, "faded")
    leaked = valid.model_copy(deep=True)
    leaked.task.example_answer = "4/8"
    leaked.task.scenario = "Pizza D has 8 equal slices. Half of eight: 8 ÷ 2 = 4."
    leaked.task.question = "Complete 1/2 = ?/8."
    leaked.task.response_hint = "Type the missing numerator."
    generate = AsyncMock(side_effect=[leaked, valid])

    result = await AdaptiveTeacher(generate).turn(ctx, state, "faded")

    assert generate.await_count == 2
    assert result.task.scenario == valid.task.scenario
    assert "reveals the answer" in generate.await_args.args[1]["repair"]


def test_a_short_numeric_answer_may_not_be_stated_by_the_teacher_before_answering():
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "guided")
    turn.task.options[0].label = "24"
    turn.task.options[1].label = "16"
    turn.task.example_answer = "24"
    turn.task.scenario = "Compare 3/8 and 5/12 by using a common denominator."
    turn.board_content = "The least common denominator is 24."
    with pytest.raises(TeachingContractError, match="short answer"):
        validate_semantic_content(turn)


def test_a_short_fraction_answer_may_not_be_stated_by_the_teacher_before_answering():
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    turn = ScriptedTeacher()._turn(ctx, state, "guided")
    turn.task.options[0].label = "3/4"
    turn.task.options[1].label = "2/5"
    turn.task.example_answer = "3/4"
    turn.task.scenario = "Compare 2/5 and 3/4."
    turn.board_content = "After conversion, 3/4 is larger."
    with pytest.raises(TeachingContractError, match="short answer"):
        validate_semantic_content(turn)


# ─── The hint is shown, so the hint is checked ───────────────────────────────

def test_the_response_hint_may_not_work_the_answer_out():
    """`response_hint` reaches the learner twice and was not being checked.

    `InputField` appends it to the question *and* uses it as the placeholder,
    so a hint that states the answer gives it away exactly as the board would.
    Every other visible field was already covered; this one was missed because
    it reads like internal guidance and is not.
    """
    open_task = task("apply").model_dump()
    open_task["response_hint"] = f"Say {open_task['example_answer']}"
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "guided")
    bad = turn.model_copy(update={"task": LearningTask.model_validate(open_task)})
    with pytest.raises(TeachingContractError, match="reveals the answer"):
        validate_semantic_content(bad)


def test_a_hint_that_only_says_how_to_answer_is_still_fine():
    """The check must not make hints useless — it targets the answer, not help."""
    open_task = task("apply").model_dump()
    open_task["response_hint"] = "Name the larger piece and say why."
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "guided")
    validate_semantic_content(turn.model_copy(
        update={"task": LearningTask.model_validate(open_task)}))


def test_oversized_hint_is_shortened_without_reauthoring_question_or_answer_key():
    original = task("apply").model_dump()
    original["response_hint"] = (
        "Explain which pizza slice is larger and describe your comparison "
        "using one complete sentence with clear reasoning and a simple example "
        "that shows how equal portions of the same whole change in size."
    )
    parsed = LearningTask.model_validate(original)
    assert 5 <= len(parsed.response_hint) <= 100
    assert parsed.response_hint.endswith("sentence")
    assert parsed.question == original["question"]
    assert parsed.criteria == original["criteria"]
    assert parsed.example_answer == original["example_answer"]
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "guided")
    validate_semantic_content(turn.model_copy(update={"task": parsed}))


# ─── Filler options ─────────────────────────────────────────────────────────

def test_two_options_cannot_share_one_piece_of_feedback():
    """Identical feedback is the signature of an option nobody authored.

    A learner who taps a filler distractor is answered with text written about
    a different option — which reads as a teacher who did not look at what
    they chose, and teaches them nothing about their actual mistake.
    """
    choice = task("choose").model_dump()
    choice["options"][1]["feedback"] = choice["options"][0]["feedback"]
    with pytest.raises(ValueError, match="feedback about that option"):
        LearningTask.model_validate(choice)


def test_punctuation_does_not_disguise_duplicated_feedback():
    choice = task("choose").model_dump()
    choice["options"][1]["feedback"] = choice["options"][0]["feedback"].upper() + "!!"
    with pytest.raises(ValueError, match="feedback about that option"):
        LearningTask.model_validate(choice)


def test_a_misconception_that_only_restates_the_option_diagnoses_nothing():
    """The reteaching reads this field. Restating the wrong answer gives it nothing."""
    diagnostic = probe().model_dump()
    label = diagnostic["options"][2]["label"]
    diagnostic["options"][2]["misconception"] = f"They said {label}"
    with pytest.raises(ValueError, match="not repeat the option"):
        LearningTask.model_validate(diagnostic)


@pytest.mark.parametrize("restatement", [
    "They said {label}",
    "{label} is wrong",
    "The learner chose {label} instead",
    "{label}",
])
def test_every_shape_of_restatement_is_caught(restatement):
    diagnostic = probe().model_dump()
    label = diagnostic["options"][2]["label"]
    diagnostic["options"][2]["misconception"] = restatement.format(label=label)
    with pytest.raises(ValueError, match="not repeat the option"):
        LearningTask.model_validate(diagnostic)


@pytest.mark.parametrize("terse", [
    "Counts pieces, ignores size",
    "Inverts numerator and denominator",
    "Adds denominators",          # two words, and a complete diagnosis
    "Cuenta las piezas",          # and it must not be an English-only gate
])
def test_a_terse_but_real_diagnosis_is_accepted(terse):
    """The test is substance, not length, and it was length in the first cut.

    A word count would have rejected "Adds denominators" — a complete
    diagnosis — while accepting "They said 14 rolls", which is none. It would
    also have pushed the generator toward padding this field to clear a bar,
    which is the opposite of what the field is for.
    """
    diagnostic = probe().model_dump()
    diagnostic["options"][2]["misconception"] = terse
    assert LearningTask.model_validate(diagnostic).options[2].misconception == terse


def test_ordinary_practice_may_still_leave_a_misconception_unset():
    """Only probes are required to diagnose; practice options may not need to."""
    choice = task("choose").model_dump()
    for option in choice["options"]:
        option["misconception"] = None
        option["gap"] = None
    assert LearningTask.model_validate(choice).options


@pytest.mark.asyncio
async def test_a_semantically_rejected_opening_probe_escalates_before_second_authoring():
    """An opening that fails semantic review must not waste its last try repeating."""
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    candidate = ScriptedTeacher()._turn(ctx, state, "diagnose")
    inputs = []

    async def generate(prompt_text, payload, schema):
        inputs.append(dict(payload))
        return candidate

    judge = AsyncMock(side_effect=[False, True])
    result = await AdaptiveTeacher(generate, semantic_judge=judge).turn(ctx, state, "diagnose")

    assert result.task is not None
    assert len(inputs) == 2
    assert not inputs[0].get("_escalate")
    assert inputs[1]["_escalate"] is True
    assert "distractors credible" in inputs[1]["repair"]
    assert judge.await_count == 2
    assert state.completed == [] and state.outbox == []


@pytest.mark.parametrize("question", [
    "Write the shaded fraction (e.g., 7/10).",
    "Escribe la fracción sombreada, por ejemplo 7/10.",
    "The correct answer is 7/10. What fraction is shaded?",
])
def test_a_short_answer_example_in_a_graded_question_is_never_shown(question):
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "transfer")
    turn.task.example_answer = "7/10"
    turn.task.question = question
    with pytest.raises(TeachingContractError, match="reveals the answer"):
        validate_semantic_content(turn)


def test_a_fraction_in_problem_data_is_not_in_itself_answer_leakage():
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "transfer")
    turn.task.example_answer = "7/10"
    turn.task.scenario = "A recipe lists 7/10 cup of liquid as an ingredient."
    turn.task.question = "What fraction of the amount remains after using half?"
    validate_semantic_content(turn)


def test_unresolved_misconceptions_are_saved_in_guided_state():
    state = GuidedState(owner="42", plan=plan(1), unresolved_misconceptions=["Mixed up the numerator"])
    restored = GuidedState.model_validate_json(state.model_dump_json())
    assert restored.unresolved_misconceptions == ["Mixed up the numerator"]


@pytest.mark.parametrize("location", ["title", "entry"])
def test_a_visual_title_or_label_cannot_reveal_a_short_answer(location):
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "transfer")
    turn.task.example_answer = "7/10"
    visual = visuals()[1]
    if location == "title":
        visual.title = "Correct answer: 7/10"
    else:
        visual.entries[0].label = "Solution 7/10"
    turn.visual = visual
    with pytest.raises(TeachingContractError, match="short answer|reveals the answer"):
        validate_semantic_content(turn)


def test_a_fraction_visual_cannot_draw_the_answer_to_an_open_question():
    turn = ScriptedTeacher()._turn(context(), GuidedState(owner="42", plan=plan()), "transfer")
    turn.task.example_answer = "7/10"
    turn.visual = visuals()[0].model_copy(update={"parts": 10, "value": 7})
    with pytest.raises(TeachingContractError, match="visual reveals the answer"):
        validate_semantic_content(turn)

def test_graded_checkpoint_hides_authored_answer_and_remembered_visual():
    """A worked board from the previous step must not assist a fresh check."""
    from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
    from lyo_app.ai_classroom.adaptive_teaching import PendingTask

    ctx = context()
    model = GuidedState(owner="42", plan=plan(1), phase="independent")
    model.board_memory = [{
        "title": "Worked solution",
        "content": "The correct answer is one half; divide into fewer pieces.",
        "visual": None,
    }]
    model.pending = PendingTask(
        task=task(), phase="independent",
        speech="You have mastered this!",
        board_title="Answer: one half",
        board_content="Here is the complete solution to the current question.",
        assisted=False,
    )
    scene = AdaptiveSession(ScriptedTeacher()).checkpoint(ctx, model)
    shown = " ".join(
        str(getattr(component, "text", "") or "")
        + " " + str(getattr(component, "title", "") or "")
        + " " + str(getattr(component, "content", "") or "")
        for component in scene.components
    ).lower()
    assert "answer: one half" not in shown
    assert "worked solution" not in shown
    assert "you have mastered" not in shown
    assert "which single piece is larger" in shown


def test_independent_success_on_one_target_does_not_erase_another_misconception():
    from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
    from lyo_app.ai_classroom.adaptive_teaching import LearningPlan, LearningUnit, PendingTask

    unit = LearningUnit(
        title="Compare and convert fractions",
        objective="Use equivalent fractions to compare two given ratios.",
        material="Compare equal fractions first, then convert values using common denominators.",
        practice_targets=["Compare fraction sizes", "Convert to an equivalent fraction"],
    )
    model = GuidedState(owner="42", plan=LearningPlan(units=[unit]),
                        phase="independent", target_index=0,
                        faded_targets=[0, 1],
                        guided_targets=[0, 1],
                        unresolved_misconceptions=["target 2: adds denominators"])
    pending = PendingTask(
        task=task().model_copy(update={"target_index": 0}),
        speech="Try it", board_title="Compare", board_content="Work through this.",
        phase="independent", assisted=False,
    )
    assert AdaptiveSession.after_success(model, pending) is False
    assert not model.independent_application
    assert model.completed == []
    assert model.target_index == 1

@pytest.mark.asyncio
async def test_grader_sends_relevant_recent_teaching_only():
    """Large prior transcripts must not slow an otherwise short grading call."""
    from lyo_app.ai_classroom.adaptive_teaching import PendingTask, Evaluation

    fake = AsyncMock(return_value=Evaluation(
        verdict="clarify", confidence=1, question_clear=False,
        feedback="The wording needs a clearer question.",
    ))
    teacher = AdaptiveTeacher(fake)
    pending = PendingTask(
        task=task(), phase="independent", speech="Try it",
        board_title="Compare", board_content="Make your comparison.",
        taught_steps=[f"Teaching beat {index}" for index in range(15)],
    )
    await teacher.evaluate(context(), pending, "The half is larger.")
    payload = fake.await_args.args[1]
    assert payload["taught"] == ["Teaching beat 12", "Teaching beat 13", "Teaching beat 14"]


@pytest.mark.asyncio
async def test_graded_teacher_introduction_is_neutral_even_when_model_leaks_solution():
    """Answer-bearing narration must not require another expensive authoring call."""
    ctx, state = context(), GuidedState(owner="42", plan=plan(1))
    candidate = ScriptedTeacher()._turn(ctx, state, "guided")
    answer = next(option.label for option in candidate.task.options if option.correct)
    candidate.speech = f"The answer is {answer}; listen carefully."
    candidate.board_title = f"Solution: {answer}"
    candidate.board_content = f"The correct answer is {answer}."
    candidate.visual = visuals()[1]
    generate = AsyncMock(return_value=candidate)

    result = await AdaptiveTeacher(generate).turn(ctx, state, "guided")

    assert generate.await_count == 1
    assert result.speech == "Try this question in your own words."
    assert result.board_title == "Your question"
    assert result.board_content == result.task.scenario
    assert result.visual is None
