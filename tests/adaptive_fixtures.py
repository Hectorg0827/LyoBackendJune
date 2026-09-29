"""Scripted pedagogical collaborators: tests never contact an AI provider."""

from unittest.mock import AsyncMock, MagicMock
from uuid import NAMESPACE_URL, uuid5

from lyo_app.ai_classroom.adaptive_teaching import (
    Evaluation, GuidedState, LearningPlan, LearningTask, LearningTurn, LearningUnit, PendingTask, TaskOption, TeachingBeat, unit_count,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    ContextSnapshot, SceneLifecycleEngine, Trigger, TriggerType,
)
from lyo_app.ai_classroom.skill_identity import SkillPlanIdentity, identity_scope, normalized_name
from lyo_app.ai_classroom.sdui_models import ActionIntent


def context(**overrides):
    fields = dict(user_id="42", session_id="fractions", topic="Fractions",
                  learning_objective="Compare and use fractions", language_code="en-US", target_duration_minutes=24)
    fields.update(overrides)
    return ContextSnapshot(**fields)


def plan(count=3):
    return LearningPlan(units=[LearningUnit(
        title=f"Fraction skill {i + 1}", objective="Compare equal parts of the same whole.",
        material="Equal parts must come from the same whole. Half a pizza is larger than a third of that pizza.",
    ) for i in range(count)])


def simulated_skill_identity(ctx, learning_plan):
    """Model stable database IDs while the interaction fixture uses a fake DB."""
    scope = identity_scope(ctx)
    if scope is None:
        return SkillPlanIdentity(unit_ids=[], topic_id=None)

    def identity(title, objective):
        return str(uuid5(NAMESPACE_URL, scope + "\0" + normalized_name(title)
                         + "\0" + normalized_name(objective)))

    title = ctx.lesson_title or ctx.topic
    return SkillPlanIdentity(
        unit_ids=[identity(unit.title, unit.objective) for unit in learning_plan.units],
        topic_id=identity(title, ctx.learning_objective or title) if title else None,
    )


async def resolve_simulated_skill_identity(ctx, learning_plan):
    return simulated_skill_identity(ctx, learning_plan)


def task(kind="apply", number=1):
    return LearningTask(
        kind=kind, scenario=f"In example {number}, two identical pizzas are cut into halves and thirds.",
        question="Which single piece is larger, and why?",
        response_hint="Name the larger piece and give one reason.",
        criteria=["Identifies one half as larger", "Explains fewer equal cuts make larger pieces"],
        example_answer="One half: the same pizza is divided into fewer equal pieces.",
        options=[
            TaskOption(id="a", label="One half", correct=True, feedback="Fewer equal pieces make each piece larger."),
            # The distractor names the misconception choosing it would reveal.
            # The authoring contract demands that of every distractor, and
            # without it here nothing in the suite exercised the choice path's
            # misconception capture — a tapped wrong answer reached the learner
            # record with no account of the error in it.
            TaskOption(id="b", label="One third", correct=False,
                       feedback="More equal cuts make smaller pieces, not bigger ones.",
                       misconception="more_pieces_means_more_each"),
        ] if kind == "choose" else [],
    )


def probe(number=1):
    """The unit's opening question: one tap, four options, before any teaching.

    Two distractors, each naming the misconception tapping it reveals and how
    far it leaves the learner from the skill, and one option for saying so
    when they are not sure. The routing this drives is the whole reason the
    probe is asked, so a fixture that skipped any of it would let a probe with
    nothing to diagnose pass the suite.
    """
    return LearningTask(
        kind="diagnose", response_format="choice",
        scenario=f"In example {number}, two identical pizzas are cut into 2 and 3 equal pieces.",
        question="Take one piece from each. Which piece is bigger?",
        response_hint="Choose the piece you think is bigger.",
        criteria=["Identifies the piece from the pizza cut into 2 as larger"],
        example_answer="The piece from the pizza cut into 2.",
        options=[
            TaskOption(id="a", label="The piece from the pizza cut into 2", correct=True,
                       feedback="Fewer equal pieces from the same whole leaves more on each one."),
            TaskOption(id="b", label="The piece from the pizza cut into 3", correct=False,
                       feedback="More equal cuts make each piece smaller, not bigger.",
                       misconception="more_pieces_means_more_each", gap="fundamental"),
            TaskOption(id="c", label="They are the same size", correct=False,
                       feedback="The wholes match, but the number of equal cuts still decides the piece.",
                       misconception="equal_wholes_means_equal_pieces", gap="near_miss"),
            TaskOption(id="d", label="I'm not sure yet", correct=False, abstains=True,
                       feedback="Declining to guess; teach from the start."),
        ],
    )


def explanation(number=1):
    """The once-per-unit "why does this work?", asked after a first success."""
    return LearningTask(
        kind="explain", response_format="short_answer",
        scenario=f"In example {number}, you compared one half with one third of the same pizza.",
        question="Why does cutting the same pizza into more equal pieces make each piece smaller?",
        response_hint="Two or three sentences in your own words.",
        criteria=["Relates more equal pieces to a smaller share of the same whole"],
        example_answer="The whole stays the same size, so sharing it between more pieces leaves less on each.",
    )


def transfer_task(number=1):
    return LearningTask(
        kind="apply", response_format="short_answer",
        scenario=f"In workshop {number}, two equal lengths of ribbon are each cut into 4 or 8 equal pieces.",
        question="Which ribbon gives a longer single piece, and why?",
        response_hint="Name the cut and give one reason.",
        criteria=["Identifies the ribbon cut into 4", "Relates fewer cuts to longer pieces"],
        example_answer="The ribbon cut into 4; fewer equal cuts of the same length leave longer pieces.",
    )


def evaluation(verdict="correct", **overrides):
    fields = dict(verdict=verdict, confidence=0.96, question_clear=True,
                  feedback="You compared pieces from the same whole.")
    fields.update(overrides)
    return Evaluation(**fields)


class ScriptedTeacher:
    def __init__(self):
        self.number = 0
        self.plan = AsyncMock(side_effect=lambda c: plan(unit_count(c.target_duration_minutes, c.total_lessons)))
        self.turn = AsyncMock(side_effect=self._turn)
        self.evaluate = AsyncMock(return_value=evaluation())

    def _turn(self, context, state, move, learner_input=""):
        self.number += 1
        teaching = move not in ("diagnose", "guided", "faded", "independent", "transfer", "interleave", "explain", "closing_win")
        kind = "choose" if move in ("guided", "closing_win") else "apply" if move in ("independent", "transfer", "interleave") else "diagnose"
        if move == "explain":
            checkpoint = explanation(self.number).model_copy(update={"target_index": state.target_index})
        elif move in ("transfer", "interleave"):
            checkpoint = transfer_task(self.number).model_copy(update={
                "target_index": 0 if move == "interleave" else state.target_index
            })
        else:
            checkpoint = None if teaching else (
                probe(self.number) if move == "diagnose" else task(kind, self.number)
            ).model_copy(update={
                "target_index": state.target_index,
                **({} if move == "diagnose" else {
                    "response_format": "choice" if kind == "choose" else "completion" if move == "faded"
                    else "short_answer",
                }),
            })
        beats = [TeachingBeat(speech=speech, board_title="One example, step by step", board_content=board)
                 for speech, board in [
                     ("First compare two identical pizzas. Cut the first into two equal pieces.", "Same-sized pizzas. First pizza: 2 equal pieces. Each is 1/2."),
                     ("Cut the second into three equal pieces. Each third is smaller than a half because there are more equal pieces.", "Same whole: 1/2 > 1/3. More equal cuts make smaller pieces."),
                 ]] if move in ("orient", "reteach", "prerequisite") else []
        if move == "orient" and state.diagnostic_ceiling == "faded":
            beats = beats[:1]
        return LearningTurn(
            speech=("Before I explain anything, show me where you are."
                    if move == "diagnose" else
                    "Equal pieces are comparable when they come from the same whole. "
                    "More cuts make each piece smaller."),
            board_title="Equal-sized wholes",
            board_content=("Two equal ribbons are cut into 4 or 8 equal lengths."
                           if move in ("transfer", "interleave") else
                           "One bar cut into 4 equal pieces has larger pieces than an identical bar cut into 8."),
            task=checkpoint, demonstration=beats,
        )


async def decline_probe(runner, progress, ctx):
    """Pass on the unit's opening diagnostic, leaving the teaching at its first beat.

    Every unit now opens by finding out what the learner can already do.
    Declining that probe is the "starts from zero" route, which is what tests
    about modelling, support and recovery are written against. Calling it
    explicitly keeps the probe visible in each test rather than hiding it
    inside a helper that claims to do something else.
    """
    pending = (progress.get("guided_state") or {}).get("pending")
    if pending and pending.get("phase") == "diagnose":
        await runner.run(ctx, progress, action(ActionIntent.SKIP_QUESTION, pending["id"]))


async def tap_probe(runner, progress, ctx, option="a"):
    """Answer the unit's opening probe with one tap, the way a learner does.

    The default taps the correct option, which is the "already has it" route:
    the unit skips the worked example and starts at supported practice, one
    rung below what the tap suggests. Pass another id for a distractor or for
    "not sure yet". Like `decline_probe`, this is called explicitly so the
    probe stays visible in the test that walks past it.
    """
    pending = (progress.get("guided_state") or {}).get("pending")
    if pending and pending.get("phase") == "diagnose":
        await runner.run(ctx, progress, action(ActionIntent.SUBMIT_ANSWER, pending["id"],
                                               answer_data={"selected_option_id": option}))


async def past_the_probe(runner, progress, ctx):
    """`decline_probe`, then advance through the teaching to the first checkpoint."""
    await decline_probe(runner, progress, ctx)
    await advance_to_task(runner, progress, ctx)


async def advance_to_task(runner, progress, ctx):
    while progress["guided_state"].get("presentation"):
        await runner.run(ctx, progress, action(component_id=progress["guided_state"]["step_id"]))


async def advance_engine(instance):
    from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
    progress = _SESSION_PROGRESS[session_progress_key("42", "fractions")]
    while progress["guided_state"].get("presentation"):
        await instance.process_trigger(action(component_id=progress["guided_state"]["step_id"]))


async def engine_decline_probe(instance):
    """`decline_probe`, for a test driving the whole engine rather than the session."""
    from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
    progress = _SESSION_PROGRESS[session_progress_key("42", "fractions")]
    pending = (progress.get("guided_state") or {}).get("pending")
    if pending and pending.get("phase") == "diagnose":
        await instance.process_trigger(action(ActionIntent.SKIP_QUESTION, pending["id"]))


async def engine_past_the_probe(instance):
    """`past_the_probe`, for a test driving the whole engine rather than the session."""
    await engine_decline_probe(instance)
    await advance_engine(instance)


def action(intent=ActionIntent.CONTINUE, component_id=None, **data):
    return Trigger(trigger_type=TriggerType.USER_ACTION, user_id="42", session_id="fractions",
                   component_id=component_id, action_data={"action_intent": intent, **data})


def engine(ctx=None):
    ctx = ctx or context()
    instance = SceneLifecycleEngine.__new__(SceneLifecycleEngine)
    instance.db = MagicMock()
    instance.db.rollback = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    instance.db.execute = AsyncMock(return_value=result)
    instance.context_assembler = MagicMock()
    instance.context_assembler.assemble_context = AsyncMock(return_value=ctx)
    instance.context_assembler.db = instance.db
    instance.adaptive_teacher = ScriptedTeacher()
    # The interaction fixture uses a MagicMock DB, but must still exercise
    # production-style persistent IDs. SQLite resolver tests exercise real
    # inserts, foreign keys, and prerequisite edges separately.
    instance.skill_resolver = resolve_simulated_skill_identity
    instance.session_contexts = {}
    instance.active_scenes = {}
    instance.websocket_manager = None
    instance._persist_session_progress = AsyncMock(return_value=True)
    return instance


def seed(instance, ctx, kind="choose", hint_level=None):
    from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
    from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
    pending = PendingTask(task=task(kind), speech="Compare pieces from the same whole.",
                          board_title="Equal wholes", board_content="One half is bigger than one third.",
                          assisted=hint_level is not None, hint_level=hint_level,
                          hints_used=1 if hint_level else 0)
    current = GuidedState(owner=ctx.user_id, plan=plan(), pending=pending, remaining_units=[1, 2])
    runner = AdaptiveSession(instance.adaptive_teacher)
    progress = {}
    runner.save(progress, current, runner.checkpoint(ctx, current))
    _SESSION_PROGRESS[session_progress_key(ctx.user_id, ctx.session_id)] = progress
    return pending.id
