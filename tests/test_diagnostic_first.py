"""The classroom finds out where the learner is before it explains anything.

Every unit used to open with `orient`: an introduction plus a modelled worked
example, paced by taps, with the learner's first chance to produce a word
arriving several beats later. It opened that way whether the learner had never
met the skill or could already perform it, because nothing ever asked.

That is the shape these tests exist to keep out. A unit now opens with one
short framing line and a real question, and what the learner does with it
decides where the unit actually starts.

The probe is also the one checkpoint a learner cannot fail, so most of what is
pinned here is about what must *not* happen to a wrong one: no reteaching of an
answer they were never given, no mark against the skill, and no zero written
into their record.
"""

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    MAX_CONSECUTIVE_TEACHER_BEATS, DiagnosticTurn, GuidedState, LearningTask, ModelledTurn,
    TeachingBeat, turn_schema,
)
from lyo_app.ai_classroom.sdui_models import (
    ActionIntent, ClassroomMode, CTAButton, InputField, QuizCard, TeacherMessage,
)
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, decline_probe, evaluation,
)


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


async def open_session(teacher=None, **ctx_overrides):
    teacher = teacher or ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(**ctx_overrides)
    scene = await runner.run(ctx, progress, action(welcome=True))
    return teacher, runner, progress, ctx, scene


async def answer_probe(runner, progress, ctx, response="Half, because fewer equal cuts leave more on each piece."):
    pending = state(progress).pending
    intent = (ActionIntent.SUBMIT_ANSWER if pending.task.response_format == "choice"
              else ActionIntent.SUBMIT_TRANSFER)
    return await runner.run(ctx, progress, action(intent, pending.id,
                                                  answer_data={"response": response,
                                                               "selected_option_id": "a"}))


# ── The opening ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_unit_opens_with_a_question_and_no_worked_example():
    _, _, progress, _, opening = await open_session()
    current = state(progress)
    assert current.phase == "diagnose" and current.pending.phase == "diagnose"
    assert current.presentation is None and not current.diagnosed
    # One teacher line, then the floor is the learner's.
    assert len([c for c in opening.components if isinstance(c, TeacherMessage)]) == 1
    assert any(isinstance(c, (InputField, QuizCard)) for c in opening.components)
    # Nothing offers to move on without an answer: a Continue here would make
    # the question optional, which is the monologue with an extra step.
    assert not any(isinstance(c, CTAButton) and c.action_intent == ActionIntent.CONTINUE
                   for c in opening.components)


@pytest.mark.asyncio
async def test_the_probe_asks_for_prior_knowledge_not_for_taught_work():
    teacher, _, _, _, _ = await open_session()
    assert teacher.turn.await_args.args[2] == "diagnose"
    assert turn_schema("diagnose") is DiagnosticTurn


def test_a_probe_may_not_carry_a_lesson_or_grade_taught_work():
    beat = dict(speech="Before I explain anything, show me where you are.",
                board_title="Two pizzas", board_content="One cut in 2, one cut in 3.")
    probe = LearningTask(
        kind="diagnose", response_format="short_answer",
        scenario="Two identical pizzas are cut into 2 and 3 equal pieces.",
        question="Which single piece is bigger, and how can you tell?",
        response_hint="Name the piece and give a reason.",
        criteria=["Identifies the piece from the pizza cut into two"],
        example_answer="The one from the pizza cut in two.")

    assert DiagnosticTurn(**beat, task=probe).task.kind == "diagnose"

    # A probe cannot model a worked example first: that is `orient`, and doing
    # it here would put the answer on the board above the question.
    with pytest.raises(ValueError):
        DiagnosticTurn(**beat, task=probe, demonstration=[TeachingBeat(**{
            **beat, "speech": "First I check the wholes match, then I count the pieces."})])

    # `apply` grades taught work. Nothing has been taught.
    with pytest.raises(ValueError):
        DiagnosticTurn(**beat, task=probe.model_copy(update={"kind": "apply"}))

    # A probe that lectures before asking is the thing it replaced.
    with pytest.raises(ValueError):
        DiagnosticTurn(**{**beat, "speech": " ".join(["Fractions describe equal parts of one whole."] * 8)},
                       task=probe)


# ── What the answer changes ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_learner_who_already_has_the_skill_skips_the_worked_example():
    teacher, runner, progress, ctx, _ = await open_session()
    await answer_probe(runner, progress, ctx)
    current = state(progress)
    assert current.diagnosed and current.phase == "faded"
    # Not "watch me" — they just did it.
    assert teacher.turn.await_args.args[2] == "faded"
    assert current.presentation is None and current.pending.phase == "faded"


@pytest.mark.asyncio
async def test_a_partial_answer_starts_at_guided_practice_rather_than_from_zero():
    teacher, runner, progress, ctx, _ = await open_session()
    teacher.evaluate.return_value = evaluation(
        "partial", feedback="Half is right; the reason is what is missing.",
        follow_up="Why does cutting the same pizza fewer times make a bigger piece?")
    await answer_probe(runner, progress, ctx, "Half")
    assert state(progress).phase == "guided"
    assert teacher.turn.await_args.args[2] == "guided"
    # The probe is not re-asked as a follow-up: it has already told us what it
    # was asked to tell us, and its job is not to be got right.
    assert state(progress).pending.phase == "guided"


@pytest.mark.asyncio
async def test_a_wrong_answer_teaches_from_the_start_and_is_not_a_setback():
    teacher, runner, progress, ctx, _ = await open_session()
    teacher.evaluate.return_value = evaluation(
        "incorrect", feedback="More equal cuts make each piece smaller, not bigger.",
        misconception="more_pieces_means_more_each")
    await answer_probe(runner, progress, ctx, "A third, because three is more than two.")
    current = state(progress)
    assert current.phase == "orient" and teacher.turn.await_args.args[2] == "orient"
    # None of the things a failed *practice* answer would cause.
    assert current.support_attempts == 0
    assert current.skipped == [] and current.completed == []
    assert not current.return_to_checkpoint

    # The teaching turn is given the learner's own words and the named
    # misconception, so the explanation can address what they actually said.
    assert teacher.turn.await_args.args[3] == "A third, because three is more than two."
    assert "smaller" in state(progress).last_feedback


@pytest.mark.asyncio
async def test_declining_the_probe_teaches_without_marking_the_skill_for_review():
    _, runner, progress, ctx, _ = await open_session()
    await decline_probe(runner, progress, ctx)
    current = state(progress)
    assert current.diagnosed and current.phase == "orient"
    # Skipping *practice* files the unit for later. Passing on "can you already
    # do this?" is an answer, and the learner has asked to be taught it now.
    assert current.skipped == [] and not current.unit_done and not current.path_done
    assert current.presentation is not None


@pytest.mark.asyncio
async def test_asking_for_help_on_the_probe_teaches_instead_of_hinting():
    teacher, runner, progress, ctx, _ = await open_session()
    probe_id = state(progress).pending.id
    await runner.run(ctx, progress, action(ActionIntent.REQUEST_HINT, probe_id))
    current = state(progress)
    assert current.diagnosed and teacher.turn.await_args.args[2] == "orient"
    # A hint would hand over the answer; returning afterwards would then grade
    # the learner on an answer we gave them.
    assert not current.return_to_checkpoint
    teacher.evaluate.assert_not_awaited()
    assert current.outbox == []


@pytest.mark.asyncio
async def test_a_real_question_during_the_probe_is_answered_and_the_probe_survives():
    teacher, runner, progress, ctx, _ = await open_session()
    probe_id = state(progress).pending.id
    await runner.run(ctx, progress, action(ActionIntent.ASK_QUESTION, probe_id,
                                          message="What does 'equal pieces' mean?"))
    current = state(progress)
    assert teacher.turn.await_args.args[2] == "answer_question"
    assert current.return_to_checkpoint and not current.diagnosed
    teacher.evaluate.assert_not_awaited()


# ── What the probe may not claim ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_correct_probe_records_performance_before_instruction_not_transfer():
    _, runner, progress, ctx, _ = await open_session()
    await answer_probe(runner, progress, ctx)
    evidence = state(progress).outbox
    assert len(evidence) == 1
    # Doing it unaided before being taught is the strongest thing this engine
    # can record — and it is not transfer, which is defined relative to
    # something taught. Nothing was.
    assert evidence[0]["evidence_type"] == "explanation"
    assert evidence[0]["correct"] is True
    # Unaided: no hint damping, because no help was available to take.
    assert evidence[0]["hints_used"] == 0 and evidence[0]["hint_level"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["incorrect", "clarify"])
async def test_a_probe_the_learner_could_not_do_writes_no_evidence_at_all(verdict):
    teacher, runner, progress, ctx, _ = await open_session()
    teacher.evaluate.return_value = evaluation(
        verdict, feedback="More equal cuts make each piece smaller.",
        misconception="more_pieces_means_more_each")
    await answer_probe(runner, progress, ctx, "A third.")
    # Not a zero. "Measured at zero on a skill never taught" is a claim about
    # the learner that asking before teaching cannot support, and the record
    # keeps "not started" and "attempted and got nothing" apart on purpose.
    assert state(progress).outbox == []


@pytest.mark.asyncio
async def test_a_probe_can_never_complete_a_unit_however_good_the_answer():
    _, runner, progress, ctx, _ = await open_session()
    await answer_probe(runner, progress, ctx)
    current = state(progress)
    assert current.completed == [] and not current.independent_application
    assert not current.unit_done and not current.path_done
    # The completion gate still wants an unaided independent application.
    assert current.faded_targets == [] and current.guided_targets == []


@pytest.mark.asyncio
async def test_one_probe_per_unit():
    teacher, runner, progress, ctx, _ = await open_session()
    await answer_probe(runner, progress, ctx)
    assert state(progress).diagnosed
    for _ in range(4):
        pending = state(progress).pending
        if pending is None or state(progress).unit_done:
            break
        await answer_probe(runner, progress, ctx)
        await advance_to_task(runner, progress, ctx)
    moves = [call.args[2] for call in teacher.turn.await_args_list]
    assert moves.count("diagnose") == 1, moves


@pytest.mark.asyncio
async def test_a_learner_who_asked_for_a_challenge_is_not_probed_first():
    # Asking for challenge or review mode is already a statement about prior
    # knowledge. Probing it would be asking a question the learner answered by
    # choosing the mode.
    for mode in (ClassroomMode.CHALLENGE, ClassroomMode.REVIEW):
        teacher, _, progress, _, _ = await open_session(classroom_mode=mode)
        assert state(progress).phase == "independent"
        assert teacher.turn.await_args.args[2] == "independent"


# ── The monologue ceiling ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_teacher_never_runs_more_than_the_ceiling_of_beats_in_a_row():
    """Count teacher beats between the learner's own turns, over a whole unit.

    A tap on Continue is not participation, so pacing a prepared lecture behind
    taps does not make it a conversation. This walks a real session and counts.
    """
    teacher, runner, progress, ctx, _ = await open_session()
    beats_in_a_row, worst = 0, 0

    async def learner_turn(trigger_action):
        nonlocal beats_in_a_row, worst
        await runner.run(ctx, progress, trigger_action)
        beats_in_a_row = 0

    async def tap_continue():
        nonlocal beats_in_a_row, worst
        await runner.run(ctx, progress, action(component_id=state(progress).step_id))
        beats_in_a_row += 1
        worst = max(worst, beats_in_a_row)

    # The opening probe is one teacher beat, then a question.
    beats_in_a_row = worst = 1
    pending = state(progress).pending
    await learner_turn(action(ActionIntent.SKIP_QUESTION, pending.id))
    # Declining lands on the first beat of the modelled example.
    beats_in_a_row = worst = max(worst, 1)

    for _ in range(8):
        current = state(progress)
        if current.unit_done or current.path_done:
            break
        if current.presentation is not None:
            await tap_continue()
            continue
        if current.pending is not None:
            await learner_turn(action(
                ActionIntent.SUBMIT_ANSWER if current.pending.task.response_format == "choice"
                else ActionIntent.SUBMIT_TRANSFER, current.pending.id,
                answer_data={"selected_option_id": "a", "response": "Half: fewer equal cuts."}))
            continue
        break

    # The literal is deliberate: asserting against the constant alone would
    # pass for any value the constant were raised to, which is the one change
    # this test exists to notice.
    assert 0 < worst <= 4, worst
    assert MAX_CONSECUTIVE_TEACHER_BEATS == 4


def test_authoring_cannot_exceed_the_beat_ceiling():
    """The ceiling is enforced where the beats are authored, not just measured.

    A modelled example is its opening line plus its steps, so the schema bounds
    the list at one less than the ceiling. The model reads that bound out of the
    JSON schema it is given, and the contract check rejects it either way.
    """
    beat = dict(speech="I check the wholes match before comparing any pieces.",
                board_title="Step one", board_content="Two identical pizzas, side by side.")
    steps = [TeachingBeat(**beat) for _ in range(MAX_CONSECUTIVE_TEACHER_BEATS)]
    with pytest.raises(ValueError):
        ModelledTurn(**beat, demonstration=steps)
    assert ModelledTurn(**beat, demonstration=steps[:-1]).demonstration == steps[:-1]
