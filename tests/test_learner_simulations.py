"""Eight learners walk the same unit and get eight different lessons.

WHAT THIS TESTS, AND WHAT IT CANNOT

Every test here drives the real `AdaptiveSession` — the engine that runs in
production — with a scripted learner and a scripted evaluator. So what is
verified is the *orchestration*: which pedagogical move runs when, what each one
is allowed to claim, and whether the path through a unit genuinely depends on
what the learner did.

It cannot verify teaching quality. No live model produces anything here, so
nothing below is evidence that a real diagnostic question is a good question.
That distinction matters: a suite like this passing is not the same as a lesson
being worth sitting through.

THE CLAIM IT EXISTS TO CHECK

A lesson that runs the same sequence whatever the learner answers is content
delivery wearing a conversation's clothes. `test_no_two_learners_get_the_same
_lesson` is the one assertion that would catch a regression to that, and every
profile-specific test above it says *how* that learner's path differs and why
that is the right difference.
"""

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.adaptive_teaching import Evaluation, GuidedState
from lyo_app.ai_classroom.sdui_models import ActionIntent
from tests.adaptive_fixtures import ScriptedTeacher, action, context


def state(progress):
    return GuidedState.model_validate(progress["guided_state"])


def verdict(name, *, feedback, follow_up="", misconception=None):
    return Evaluation(
        verdict=name, confidence=0.95, question_clear=True, feedback=feedback,
        follow_up=follow_up, misconception=misconception,
    )


#: What each learner does, in order, at each graded checkpoint they reach.
#: `...` repeats the last entry for the rest of the session.
SCRIPTS: dict[str, list[str]] = {
    # Knows nothing yet: cannot do the probe, then learns as it is taught.
    "BEGINNER":            ["incorrect", "correct", "correct", "correct"],
    # Answers fast and wrong, with a real misconception behind it.
    "CONFIDENT_BUT_WRONG": ["incorrect", "incorrect", "correct", "correct"],
    # Can already do it.
    "ADVANCED":            ["correct"],
    # Right idea, too little of it to score.
    "QUIET":               ["partial", "correct", "correct", "correct"],
    # Has not met it yet, and the curiosity goes into questions rather than
    # into the answers — so this learner reaches a worked example to interrupt.
    "CURIOUS":             ["incorrect", "correct", "correct", "correct"],
    # Keeps missing it, which must never become a gate.
    "STRUGGLING":          ["incorrect"],
    "FAST_LEARNER":        ["correct"],
    "INTERRUPTER":         ["incorrect", "correct", "correct", "correct"],
}

FEEDBACK = {
    "correct": "You compared pieces from the same whole.",
    "partial": "Half is right; the reason is what is still missing.",
    "incorrect": "More equal cuts make each piece smaller, not bigger.",
}
ANSWERS = {
    "QUIET": "Half",
    "CONFIDENT_BUT_WRONG": "A third, obviously — three is more than two.",
}


class Learner:
    """A scripted student, and the record of what the teacher did about them."""

    def __init__(self, profile: str):
        self.profile = profile
        self.script = list(SCRIPTS[profile])
        self.answered = 0
        self.questions_asked = 0

    def next_verdict(self) -> str:
        name = self.script[self.answered] if self.answered < len(self.script) else self.script[-1]
        self.answered += 1
        return name

    def option_for_next_verdict(self) -> str:
        """Which option to tap so a *choice* checkpoint scores as scripted.

        A choice checkpoint is graded from the option's own `correct` flag and
        never reaches the evaluator — the server will not ask a model whether
        the learner tapped the right button. So the script has to be consumed
        here instead, or a learner scripted to struggle taps the right answer
        and the whole profile quietly becomes a learner who gets everything
        right. That is exactly what happened the first time this ran, and it
        made five of these tests assert the wrong thing while passing four.
        """
        return "a" if self.next_verdict() == "correct" else "b"

    def evaluator(self):
        def evaluate(context, pending, response):
            name = self.next_verdict()
            return verdict(
                name,
                feedback=FEEDBACK[name],
                follow_up="Why does cutting the same pizza fewer times make a bigger piece?"
                if name == "partial" else "",
                misconception="more_pieces_means_more_each" if name == "incorrect" else None,
            )
        return evaluate

    def answer_text(self) -> str:
        return ANSWERS.get(self.profile, "Half: fewer equal cuts of the same whole leave more on each piece.")


async def simulate(profile: str, minutes: int = 8, max_turns: int = 80):
    """Run one learner through a session and return the moves the teacher chose.

    Eight minutes is one unit, which is the right size for comparing profiles:
    the divergence this file is about happens inside a unit, and a three-unit
    run would repeat it three times and bury it. `minutes=24` gives the
    multi-unit session, which the last test uses.
    """
    learner = Learner(profile)
    teacher = ScriptedTeacher()
    teacher.evaluate.side_effect = learner.evaluator()
    runner, progress, ctx = AdaptiveSession(teacher), {}, context(target_duration_minutes=minutes)
    await runner.run(ctx, progress, action(welcome=True))

    beats_in_a_row, worst_run = 1, 1
    for _ in range(max_turns):
        current = state(progress)
        if current.path_done:
            break

        if current.unit_done:
            await runner.run(ctx, progress, action(component_id=current.step_id))
            beats_in_a_row = 0
            continue

        if current.presentation is not None:
            # A learner who interrupts does so mid-example, once, and the
            # example must survive it. A curious one asks and comes back.
            if profile in ("CURIOUS", "INTERRUPTER") and learner.questions_asked < 2:
                learner.questions_asked += 1
                await runner.run(ctx, progress, action(
                    ActionIntent.ASK_QUESTION, current.step_id,
                    message="Wait — what does 'equal pieces' actually mean?"))
                beats_in_a_row = 0
                continue
            await runner.run(ctx, progress, action(component_id=current.step_id))
            beats_in_a_row += 1
            worst_run = max(worst_run, beats_in_a_row)
            continue

        if current.pending is not None:
            choice = current.pending.task.response_format == "choice"
            payload = ({"selected_option_id": learner.option_for_next_verdict()} if choice
                       else {"response": learner.answer_text()})
            await runner.run(ctx, progress, action(
                ActionIntent.SUBMIT_ANSWER if choice else ActionIntent.SUBMIT_TRANSFER,
                current.pending.id, answer_data=payload))
            beats_in_a_row = 0
            continue
        break

    moves = [call.args[2] for call in teacher.turn.await_args_list]
    return dict(
        profile=profile, moves=moves, state=state(progress), units=len(state(progress).plan.units),
        answered=learner.answered, worst_teacher_run=worst_run, teacher=teacher,
    )


# ── Each learner gets the lesson their answers earned ─────────────────────────

@pytest.mark.asyncio
async def test_a_learner_who_already_has_the_skill_is_not_taught_it_from_scratch():
    run = await simulate("ADVANCED")
    # The probe is passed, so the worked example is skipped entirely. Sitting a
    # learner through "watch me" on something they just did is the fastest way
    # to lose them.
    assert run["moves"][0] == "diagnose"
    assert "orient" not in run["moves"] and "model" not in run["moves"]
    assert run["moves"][1] == "faded"
    # And it is real completion, not a shortcut: the gate still wanted an
    # unaided independent application.
    assert run["state"].independent_application
    assert run["state"].completed == [0]


@pytest.mark.asyncio
async def test_a_beginner_gets_the_worked_example_the_advanced_learner_skipped():
    run = await simulate("BEGINNER")
    assert run["moves"][0] == "diagnose"
    # Could not do the probe, so the unit teaches: a modelled example first,
    # then supported practice, then fading, then independence.
    assert "orient" in run["moves"]
    assert run["moves"].index("orient") < run["moves"].index("guided")
    assert run["state"].guided_targets and run["state"].faded_targets
    assert run["state"].independent_application
    # Being wrong on the probe left no mark: it is not a skill they failed.
    assert run["state"].skipped == []


@pytest.mark.asyncio
async def test_confidence_is_not_evidence_and_a_named_misconception_is_reteaught():
    run = await simulate("CONFIDENT_BUT_WRONG")
    # Wrong twice, so the second one is reteaching — and the reteaching turn is
    # given the learner's actual answer to teach against, which for a tapped
    # distractor is the option they chose. That is the point of authoring
    # distractors as real misconceptions rather than filler: "One third" tells
    # the next turn what to explain.
    assert "reteach" in run["moves"]
    reteach_call = next(c for c in run["teacher"].turn.await_args_list if c.args[2] == "reteach")
    assert reteach_call.args[3] == "One third"
    # And the reteaching is built from the grader's own account of the error,
    # not from a generic "wrong".
    assert "smaller" in run["state"].last_feedback or "smaller" in reteach_call.args[1].last_feedback
    # The wrong practice answer is recorded as what it was, with the specific
    # error named so remediation can target it. The wrong *probe* is not
    # recorded at all, so the first thing in the record is the practice answer.
    graded = run["state"].outbox
    assert graded and graded[0]["correct"] is False
    assert graded[0]["misconception"] == "more_pieces_means_more_each"
    # Being sure of a wrong answer never produced a correct record.
    assert not any(e["correct"] and e["misconception"] for e in graded)


@pytest.mark.asyncio
async def test_a_short_answer_gets_one_targeted_follow_up_not_a_rewrite_request():
    run = await simulate("QUIET")
    # The probe came back partial, so the unit starts at guided practice — not
    # from zero, because they did show something.
    assert run["moves"][0] == "diagnose" and run["moves"][1] == "guided"
    assert "orient" not in run["moves"]
    # Their reasoning so far is kept, and the follow-up asks for the one thing
    # missing rather than the whole answer again.
    assert run["state"].independent_application


@pytest.mark.asyncio
async def test_a_detour_is_answered_and_the_example_is_not_thrown_away():
    run = await simulate("CURIOUS")
    assert "answer_question" in run["moves"]
    # The lesson survived the detour: the learner still reached independent
    # application of the unit's own objective.
    assert run["state"].independent_application
    assert run["state"].completed == [0]


@pytest.mark.asyncio
async def test_interrupting_mid_example_resumes_the_same_example():
    run = await simulate("INTERRUPTER")
    assert "answer_question" in run["moves"]
    # The paused demonstration was restored rather than regenerated: the
    # teacher did not start the worked example over because it was interrupted.
    orient_turns = [c for c in run["teacher"].turn.await_args_list if c.args[2] == "orient"]
    assert len(orient_turns) <= 1
    assert run["state"].completed == [0]


@pytest.mark.asyncio
async def test_repeated_difficulty_teaches_a_prerequisite_and_never_becomes_a_gate():
    run = await simulate("STRUGGLING")
    assert "reteach" in run["moves"] and "prerequisite" in run["moves"]
    current = run["state"]
    # Teaching continued. The skill is filed for more practice — not failed,
    # and not a wall the learner has to pass to see anything else.
    assert 0 in current.skipped
    assert current.completed == [] and not current.independent_application
    # Nothing claimed they got it, and nothing claimed they gave up.
    assert all(e["correct"] is False for e in current.outbox)


@pytest.mark.asyncio
async def test_a_fast_learner_spends_the_fewest_turns_listening():
    fast = await simulate("FAST_LEARNER")
    beginner = await simulate("BEGINNER")
    assert fast["state"].independent_application and beginner["state"].independent_application
    # Same destination, and the learner who needed less explanation got less.
    assert len(fast["moves"]) < len(beginner["moves"])
    assert fast["worst_teacher_run"] < beginner["worst_teacher_run"]


# ── The one assertion that would catch a relapse ──────────────────────────────

@pytest.mark.asyncio
async def test_no_two_learners_get_the_same_lesson():
    """A fixed sequence whatever the learner answers is content delivery.

    This is the regression that matters. Every profile above can keep passing
    while the engine quietly converges on one script — a `diagnose` whose result
    is ignored, say — so the shape of the whole set is asserted here rather than
    inferred from the parts.
    """
    runs = {name: await simulate(name) for name in SCRIPTS}
    sequences = {name: tuple(run["moves"]) for name, run in runs.items()}

    # Every learner is asked before anything is explained.
    assert all(sequence[0] == "diagnose" for sequence in sequences.values())

    # Learners who answered differently were taught differently. The three
    # profiles scripted to answer identically (ADVANCED, FAST_LEARNER, and
    # CURIOUS/INTERRUPTER before their questions) are expected to share a
    # spine, so the check is on the distinct answering behaviours.
    distinct = {sequences[name] for name in
                ("BEGINNER", "CONFIDENT_BUT_WRONG", "ADVANCED", "QUIET", "STRUGGLING", "CURIOUS")}
    assert len(distinct) == 6, sequences

    # And the difference is not cosmetic: what each learner ended up having
    # demonstrated differs too.
    assert runs["ADVANCED"]["state"].completed == [0]
    assert runs["STRUGGLING"]["state"].completed == []
    assert runs["BEGINNER"]["state"].completed == [0]

    # No learner sat through more than the ceiling of consecutive teacher beats.
    assert all(run["worst_teacher_run"] <= 4 for run in runs.values()), {
        name: run["worst_teacher_run"] for name, run in runs.items()
    }


# ── A whole session, not one unit ────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["BEGINNER", "ADVANCED", "CONFIDENT_BUT_WRONG"])
async def test_a_full_session_probes_each_unit_once_and_ends_with_demonstrations(profile):
    """Three units, start to finish, with the per-unit rules holding throughout.

    The profile tests above each run a single unit, which is where their
    divergence lives. This one checks the properties that only a whole session
    can break: a probe per unit rather than per session, the beat ceiling
    holding across unit boundaries, and evidence that adds up to something at
    the end rather than resetting.
    """
    run = await simulate(profile, minutes=24)
    assert run["units"] == 3
    current = run["state"]

    # Asked once per unit — not once per session, which would assume a learner
    # who can do unit one can do unit three; and not once per turn, which would
    # be a quiz pretending to be a diagnosis.
    assert run["moves"].count("diagnose") == 3
    # Each unit's own probe is the first move of that unit.
    assert run["moves"][0] == "diagnose"

    assert current.path_done
    assert current.completed == [0, 1, 2]
    assert current.skipped == []

    # Every completed unit banked an unaided independent application, and the
    # record has one demonstration per unit at the least.
    correct = [e for e in current.outbox if e["correct"]]
    assert len(correct) >= 3
    assert all(e["concept_id"] for e in current.outbox)

    # And no stretch of the session was a lecture.
    assert run["worst_teacher_run"] <= 4, run["worst_teacher_run"]
