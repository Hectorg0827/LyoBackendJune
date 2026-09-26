"""Scripted pedagogical collaborators: tests never contact an AI provider."""

from unittest.mock import AsyncMock, MagicMock

from lyo_app.ai_classroom.adaptive_teaching import (
    Evaluation, GuidedState, LearningPlan, LearningTask, LearningTurn, LearningUnit, PendingTask, TaskOption, TeachingBeat, unit_count,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    ContextSnapshot, SceneLifecycleEngine, Trigger, TriggerType,
)
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
        teaching = move not in ("diagnose", "guided", "faded", "independent")
        kind = "choose" if move == "guided" else "apply" if move == "independent" else "diagnose"
        checkpoint = None if teaching else task(kind, self.number).model_copy(update={
            "target_index": state.target_index,
            "response_format": "choice" if kind == "choose" else "completion" if move == "faded"
            else "short_answer",
        })
        beats = [TeachingBeat(speech=speech, board_title="One example, step by step", board_content=board)
                 for speech, board in [
                     ("First compare two identical pizzas. Cut the first into two equal pieces.", "Same-sized pizzas. First pizza: 2 equal pieces. Each is 1/2."),
                     ("Cut the second into three equal pieces. Each third is smaller than a half because there are more equal pieces.", "Same whole: 1/2 > 1/3. More equal cuts make smaller pieces."),
                 ]] if move in ("orient", "reteach", "prerequisite") else []
        return LearningTurn(
            speech=("Before I explain anything, show me where you are."
                    if move == "diagnose" else
                    "Equal pieces are comparable when they come from the same whole. "
                    "More cuts make each piece smaller."),
            board_title="Equal-sized wholes",
            board_content="One bar cut into 4 equal pieces has larger pieces than an identical bar cut into 8.",
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
