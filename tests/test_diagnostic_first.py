"""The classroom finds out where the learner is before it explains anything.

Every unit used to open with `orient`: an introduction plus a modelled worked
example, paced by taps, with the learner's first chance to produce a word
arriving several beats later. It opened that way whether the learner had never
met the skill or could already perform it, because nothing ever asked.

That is the shape these tests exist to keep out. A unit now opens with one
short framing line and one real question, and what the learner does with it
decides where the unit actually starts.

The question is multiple choice, and the routing it drives is deliberately
cautious about that. Four options cannot tell knowing something apart from
picking it, so the tap sets a *ceiling* — the furthest this unit may
fast-forward to — and the unit starts one rung below it. What the tap is good
at is being cheap to answer: a learner who has never met the skill can still
choose, where a blank box in front of an unfamiliar skill reads as a test.

The probe is also the one checkpoint a learner cannot fail, so much of what is
pinned here is about what must *not* happen to a wrong one: no reteaching of an
answer they were never given, no mark against the skill, no zero written into
their record, and no rung awarded for a lucky tap.
"""

from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import (
    MAX_CONSECUTIVE_TEACHER_BEATS, AdaptiveTeacher, DiagnosticTurn, FocusedModelledTurn,
    GuidedState, LearningTask, ModelledTurn, TaskOption, TeachingBeat, turn_schema,
)
from lyo_app.ai_classroom.sdui_models import (
    ActionIntent, ClassroomMode, CTAButton, InputField, QuizCard, TeacherMessage,
)
from tests.adaptive_fixtures import (
    ScriptedTeacher, action, advance_to_task, context, decline_probe, plan, probe,
)


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


async def open_session(teacher=None, **ctx_overrides):
    teacher = teacher or ScriptedTeacher()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(**ctx_overrides)
    scene = await runner.run(ctx, progress, action(welcome=True))
    return teacher, runner, progress, ctx, scene


async def tap(runner, progress, ctx, option="a"):
    """Tap one of the current checkpoint's options. The default is the right one.

    In `probe()` the options are, in order: the correct answer, a fundamental
    misconception, a near miss, and "I'm not sure yet".
    """
    pending = state(progress).pending
    return await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending.id,
                                                  answer_data={"selected_option_id": option}))


async def answer_open(runner, progress, ctx,
                      response="Half, because fewer equal cuts leave more on each piece."):
    pending = state(progress).pending
    return await runner.run(ctx, progress, action(ActionIntent.SUBMIT_TRANSFER, pending.id,
                                                  answer_data={"response": response}))


async def answer_checkpoint(runner, progress, ctx, option="a"):
    """Answer whatever the current checkpoint is, in whichever shape it asks."""
    await advance_to_task(runner, progress, ctx)
    if state(progress).pending.task.response_format == "choice":
        return await tap(runner, progress, ctx, option)
    return await answer_open(runner, progress, ctx)


def open_probe():
    """A probe from a session saved before the opening question became a tap."""
    return LearningTask(
        kind="diagnose", response_format="short_answer",
        scenario="Two identical pizzas are cut into 2 and 3 equal pieces.",
        question="Which single piece is bigger, and how can you tell?",
        response_hint="Name the piece and give a reason.",
        criteria=["Identifies the piece from the pizza cut into two",
                  "Explains why fewer equal cuts make a bigger piece"],
        example_answer="The one from the pizza cut in two.")


# ── The opening ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_unit_opens_with_one_tap_and_no_worked_example():
    _, _, progress, _, opening = await open_session()
    current = state(progress)
    assert current.phase == "diagnose" and current.pending.phase == "diagnose"
    assert current.presentation is None and not current.diagnosed
    assert current.diagnostic_ceiling is None
    # One teacher line, then the floor is the learner's.
    assert len([c for c in opening.components if isinstance(c, TeacherMessage)]) == 1
    # One tap, with somewhere to say "not sure yet". A blank box in front of a
    # skill nobody has taught yet is where a learner leaves.
    card = next(c for c in opening.components if isinstance(c, QuizCard))
    assert len(card.options) == 4
    assert not any(isinstance(c, InputField) for c in opening.components)
    # Nothing offers to move on without an answer: a Continue here would make
    # the question optional, which is the monologue with an extra step.
    assert not any(isinstance(c, CTAButton) and c.action_intent == ActionIntent.CONTINUE
                   for c in opening.components)


@pytest.mark.asyncio
async def test_the_probe_asks_for_prior_knowledge_not_for_taught_work():
    teacher, _, _, _, _ = await open_session()
    assert teacher.turn.await_args.args[2] == "diagnose"
    assert turn_schema("diagnose") is DiagnosticTurn


@pytest.mark.asyncio
async def test_neither_the_key_nor_the_diagnosis_travels_with_the_question():
    _, _, progress, _, opening = await open_session()
    card = next(c for c in opening.components if isinstance(c, QuizCard))
    # Clients colour a tap instantly from the option's own correctness during
    # ordinary practice. Here that would put the answer key on the device while
    # the learner is still deciding.
    assert all(option.is_correct is None for option in card.options)
    assert all(option.feedback_correct is None and option.feedback_incorrect is None
               for option in card.options)
    # Each distractor names the misconception it reveals and how far it leaves
    # the learner from the skill. That is a judgement about the learner, made
    # for the next teaching turn, and it must not travel with the question they
    # are still answering.
    assert all(option.misconception_tag is None and option.remediation_hint is None
               for option in card.options)
    wire = opening.model_dump_json()
    for private in ("more_pieces_means_more_each", "equal_wholes_means_equal_pieces",
                    "near_miss", "fundamental", "abstains", "criteria", "example_answer"):
        assert private not in wire, private


def test_a_probe_may_not_carry_a_lesson_or_grade_taught_work():
    beat = dict(speech="Before I explain anything, show me where you are.",
                board_title="Two pizzas", board_content="One cut in 2, one cut in 3.")
    question = probe()

    assert DiagnosticTurn(**beat, task=question).task.kind == "diagnose"

    # A probe cannot model a worked example first: that is `orient`, and doing
    # it here would put the answer on the board above the question.
    with pytest.raises(ValueError):
        DiagnosticTurn(**beat, task=question, demonstration=[TeachingBeat(**{
            **beat, "speech": "First I check the wholes match, then I count the pieces."})])

    # `apply` grades taught work. Nothing has been taught.
    with pytest.raises(ValueError):
        DiagnosticTurn(**beat, task=question.model_copy(update={"kind": "apply"}))

    # A probe that lectures before asking is the thing it replaced.
    with pytest.raises(ValueError):
        DiagnosticTurn(**{**beat, "speech": " ".join(["Fractions describe equal parts of one whole."] * 8)},
                       task=question)


def test_a_probe_without_a_way_to_decline_or_a_named_gap_is_not_a_probe():
    """What makes the opening tap worth asking is what its options carry.

    Four plausible options and nothing else would tell the unit only whether
    the learner guessed right. These are the parts that make the answer
    *diagnostic*: somewhere to decline, and distractors that say what tapping
    them reveals and how far it leaves the learner from the skill.
    """
    beat = dict(speech="Before I explain anything, show me where you are.",
                board_title="Two pizzas", board_content="One cut in 2, one cut in 3.")
    question = probe()
    options = question.options
    without_options = question.model_dump(exclude={"options"})

    # A typed answer, before anything has been taught, costs more than it returns.
    with pytest.raises(ValueError):
        DiagnosticTurn(**beat, task=open_probe())

    # No way to say "not sure yet": a learner who does not know has to guess,
    # and a guess that lands would start the unit above where they are.
    with pytest.raises(ValueError):
        DiagnosticTurn(**beat, task=LearningTask(**without_options, options=[
            *options[:3], options[3].model_copy(update={"abstains": False, "label": "None of these"})]))

    # Three options is not the shape, and neither is two abstentions.
    with pytest.raises(ValueError):
        DiagnosticTurn(**beat, task=LearningTask(**without_options, options=options[:3]))
    with pytest.raises(ValueError):
        LearningTask(**without_options, options=[
            options[0], options[1].model_copy(update={"abstains": True, "misconception": None, "gap": None}),
            *options[2:]])

    # A distractor that does not say what tapping it reveals, or how far that
    # leaves the learner from the skill, cannot route the teaching that follows.
    for update in ({"misconception": None}, {"gap": None}):
        with pytest.raises(ValueError):
            DiagnosticTurn(**beat, task=LearningTask(**without_options, options=[
                options[0], options[1].model_copy(update=update), *options[2:]]))


def test_the_correct_option_is_not_a_misconception_and_declining_is_not_one_either():
    with pytest.raises(ValueError):
        TaskOption(id="a", label="One half", correct=True, feedback="Fewer equal pieces are larger.",
                   misconception="more_pieces_means_more_each", gap="near_miss")
    with pytest.raises(ValueError):
        TaskOption(id="d", label="I'm not sure yet", correct=False, abstains=True,
                   feedback="Declining to guess.", misconception="cannot_compare", gap="fundamental")


# ── Where the tap starts the unit ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_right_option_skips_the_example_and_starts_supported_practice():
    teacher, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "a")
    current = state(progress)
    assert current.diagnosed
    # Not "watch me": they just picked it out. But not independent practice
    # either — one tap in four is not a demonstration of anything, so the
    # ceiling holds the claim and guided practice is where it gets tested.
    assert current.phase == "guided" and current.pending.phase == "guided"
    assert current.diagnostic_ceiling == "independent"
    assert teacher.turn.await_args.args[2] == "guided"
    assert current.presentation is None


@pytest.mark.asyncio
async def test_a_near_miss_is_taught_the_one_step_it_turns_on():
    teacher, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "c")
    current = state(progress)
    assert current.phase == "orient" and current.diagnostic_ceiling == "faded"
    assert teacher.turn.await_args.args[2] == "orient"
    # The learner has the idea and slipped on one step, so they get that step.
    # The whole derivation would spend their patience on the part they just
    # showed they have.
    assert len(current.presentation.demonstration) == 1
    assert current.diagnostic_misconception == "equal_wholes_means_equal_pieces"


@pytest.mark.asyncio
async def test_a_fundamental_misconception_gets_the_whole_example_aimed_at_it():
    teacher, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "b")
    current = state(progress)
    assert current.phase == "orient" and current.diagnostic_ceiling == "guided"
    # Reasoning from a different model of the situation needs the example
    # built, not abbreviated — however precisely the tap named the error.
    assert len(current.presentation.demonstration) == 2
    # And the teaching turn is told which error to address, so it can teach
    # against what this learner actually believes rather than the topic.
    assert teacher.turn.await_args.args[1].diagnostic_misconception == "more_pieces_means_more_each"
    assert current.support_attempts == 0 and current.skipped == []


@pytest.mark.asyncio
async def test_not_sure_yet_teaches_from_the_start_and_is_not_a_wrong_answer():
    _, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "d")
    current = state(progress)
    assert current.diagnosed and current.phase == "orient"
    # No ceiling to inherit and no misconception to teach against: the learner
    # said they were not sure, which is an answer, and an honest one.
    assert current.diagnostic_ceiling is None and current.diagnostic_misconception == ""
    assert len(current.presentation.demonstration) == 2
    # Skipping *practice* files the unit for later. Declining "can you already
    # do this?" must not, and it is not recorded as an error.
    assert current.skipped == [] and current.outbox == []
    assert [e["verdict"] for e in current.practice_events if e["kind"] == "diagnostic"] == ["declined"]


@pytest.mark.asyncio
async def test_declining_the_probe_teaches_without_marking_the_skill_for_review():
    _, runner, progress, ctx, _ = await open_session()
    await decline_probe(runner, progress, ctx)
    current = state(progress)
    assert current.diagnosed and current.phase == "orient"
    assert current.skipped == [] and not current.unit_done and not current.path_done
    assert current.presentation is not None and current.diagnostic_ceiling is None


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
    assert current.outbox == [] and current.diagnostic_ceiling is None


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


# ── The ceiling is a hypothesis, not a measurement ───────────────────────────

@pytest.mark.asyncio
async def test_real_work_that_contradicts_the_tap_withdraws_what_it_claimed():
    teacher, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "a")
    assert state(progress).diagnostic_ceiling == "independent"
    # The guided checkpoint that followed says otherwise. From here the unit is
    # paced by what the learner does, not by what they picked before it taught
    # them anything.
    await tap(runner, progress, ctx, "b")
    current = state(progress)
    assert current.diagnostic_ceiling is None
    assert teacher.turn.await_args.args[2] == "reteach"


@pytest.mark.asyncio
async def test_a_confirmed_tap_saves_the_other_component_skills_from_starting_over():
    """The one place the opening tap buys back the time it cost.

    A learner the probe placed at the top of the unit, who has since shown it
    on faded practice without needing extra help, does not drop back to
    supported practice for every remaining component skill. Declining the
    probe claims nothing, so that learner walks the full ladder each time.
    """
    async def rungs(first_move):
        teacher = ScriptedTeacher()
        curriculum = plan(1)
        curriculum.units[0].practice_targets = ["Compare equal-sized wholes",
                                                "Relate number of equal cuts to piece size"]
        teacher.plan.side_effect = None
        teacher.plan.return_value = curriculum
        _, runner, progress, ctx, _ = await open_session(teacher)
        await first_move(runner, progress, ctx)
        seen = []
        for _ in range(3):
            await advance_to_task(runner, progress, ctx)
            pending = state(progress).pending
            if pending is None:
                break
            seen.append((pending.phase, pending.task.target_index))
            await answer_checkpoint(runner, progress, ctx)
        return seen

    assert await rungs(lambda r, p, c: tap(r, p, c, "a")) == [("guided", 0), ("faded", 0), ("faded", 1)]
    assert await rungs(decline_probe) == [("guided", 0), ("faded", 0), ("guided", 1)]


# ── What the probe may not claim ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_tap_earns_no_evidence_however_right_it_is():
    _, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "a")
    # Recognising the right answer among four is not a claim worth keeping
    # about anybody, and the learner record is for claims. The tap decides
    # where the unit starts; it does not say the learner can do anything.
    assert state(progress).outbox == []


@pytest.mark.asyncio
async def test_a_saved_open_answer_probe_still_records_performance_before_instruction():
    # A session saved before the opening question became a tap can still be
    # resumed. An unaided open answer with its reasoning is the strongest thing
    # this engine can record, and it still enters at faded practice: unlike a
    # tap, it has the learner's own words behind it.
    _, runner, progress, ctx, _ = await open_session()
    current = state(progress)
    current.pending.task = open_probe()
    runner.save(progress, current, runner.checkpoint(ctx, current))
    await answer_open(runner, progress, ctx)

    current = state(progress)
    assert current.phase == "faded" and current.diagnostic_ceiling == "independent"
    assert len(current.outbox) == 1
    # Not transfer, which is defined relative to something taught. Nothing was.
    assert current.outbox[0]["evidence_type"] == "explanation"
    assert current.outbox[0]["correct"] is True
    # Unaided: no hint damping, because no help was available to take.
    assert current.outbox[0]["hints_used"] == 0 and current.outbox[0]["hint_level"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("option", ["b", "c", "d"])
async def test_a_probe_the_learner_could_not_do_writes_no_evidence_at_all(option):
    _, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, option)
    # Not a zero. "Measured at zero on a skill never taught" is a claim about
    # the learner that asking before teaching cannot support, and the record
    # keeps "not started" and "attempted and got nothing" apart on purpose.
    assert state(progress).outbox == []


@pytest.mark.asyncio
async def test_a_probe_can_never_complete_a_unit_however_good_the_answer():
    _, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "a")
    current = state(progress)
    assert current.completed == [] and not current.independent_application
    assert not current.unit_done and not current.path_done
    # The completion gate still wants an unaided independent application.
    assert current.faded_targets == [] and current.guided_targets == []


@pytest.mark.asyncio
async def test_one_probe_per_unit():
    teacher, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "a")
    assert state(progress).diagnosed
    for _ in range(5):
        if state(progress).unit_done or state(progress).path_done:
            break
        await answer_checkpoint(runner, progress, ctx)
    moves = [call.args[2] for call in teacher.turn.await_args_list]
    assert moves.count("diagnose") == 1, moves


@pytest.mark.asyncio
async def test_a_fresh_unit_asks_its_own_question_and_inherits_no_ceiling():
    teacher, runner, progress, ctx, _ = await open_session()
    await tap(runner, progress, ctx, "a")
    for _ in range(4):
        if state(progress).unit_done:
            break
        await answer_checkpoint(runner, progress, ctx)
    assert state(progress).unit_done and state(progress).diagnostic_ceiling == "independent"
    await runner.run(ctx, progress, action(component_id=state(progress).step_id))
    current = state(progress)
    assert current.unit_index == 1 and not current.diagnosed
    assert current.phase == "diagnose" and current.diagnostic_ceiling is None
    assert current.diagnostic_misconception == ""
    assert teacher.turn.await_args.args[2] == "diagnose"


@pytest.mark.asyncio
async def test_a_learner_who_asked_for_a_challenge_is_not_probed_first():
    # Asking for challenge or review mode is already a statement about prior
    # knowledge. Probing it would be asking a question the learner answered by
    # choosing the mode.
    for mode in (ClassroomMode.CHALLENGE, ClassroomMode.REVIEW):
        teacher, _, progress, _, _ = await open_session(classroom_mode=mode)
        assert state(progress).phase == "independent"
        assert teacher.turn.await_args.args[2] == "independent"


# ── The compressed example is asked for where the beats are authored ─────────

@pytest.mark.asyncio
async def test_a_near_miss_asks_the_generator_for_one_step_and_names_the_error():
    """The compression is a contract with the generator, not a client-side trim.

    Asking for 2–3 beats and then showing one would waste the generation and
    leave the example half-told. The schema the model is given changes instead,
    and the misconception travels with it.
    """
    beat = dict(speech="You matched the wholes, which is the part most learners miss.",
                board_title="The step it turns on",
                board_content="Same whole, more equal cuts, smaller pieces.")
    generate = AsyncMock(return_value=FocusedModelledTurn(**beat, demonstration=[TeachingBeat(**beat)]))
    current = GuidedState(owner="42", plan=plan(1), phase="orient",
                          diagnostic_ceiling="faded",
                          diagnostic_misconception="equal_wholes_means_equal_pieces")

    turn = await AdaptiveTeacher(generate).turn(context(), current, "orient", "They are the same size")
    assert len(turn.demonstration) == 1
    assert generate.await_args.args[2] is FocusedModelledTurn
    payload = generate.await_args.args[1]
    assert payload["compress_demonstration"] is True
    assert payload["diagnosed_misconception"] == "equal_wholes_means_equal_pieces"

    # Every other route to `orient` still gets the whole worked example.
    assert turn_schema("orient") is ModelledTurn
    assert turn_schema("orient", True) is FocusedModelledTurn


def test_the_compressed_example_is_still_an_example():
    beat = dict(speech="I check the wholes match before comparing any pieces.",
                board_title="Step one", board_content="Two identical pizzas, side by side.")
    # One step, aimed at the step the learner missed — but never none: a beat
    # with nothing after it is an assertion, not a demonstration.
    assert len(FocusedModelledTurn(**beat, demonstration=[TeachingBeat(**beat)]).demonstration) == 1
    with pytest.raises(ValueError):
        FocusedModelledTurn(**beat, demonstration=[])
    with pytest.raises(ValueError):
        FocusedModelledTurn(**beat, demonstration=[TeachingBeat(**beat) for _ in range(3)])


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
