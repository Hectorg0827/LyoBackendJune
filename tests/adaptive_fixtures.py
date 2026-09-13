"""Scripted pedagogical collaborators: tests never contact an AI provider."""

from unittest.mock import AsyncMock, MagicMock

from lyo_app.ai_classroom.adaptive_teaching import (
    Evaluation, GuidedState, LearningPlan, LearningTask, LearningTurn, LearningUnit, PendingTask, TaskOption, unit_count,
)
from lyo_app.ai_classroom.scene_lifecycle_engine import (
    ContextSnapshot, SceneLifecycleEngine, Trigger, TriggerType,
)
from lyo_app.ai_classroom.sdui_models import ActionIntent


def context(**overrides):
    fields = dict(user_id="42", session_id="fractions", topic="Fractions",
                  learning_objective="Compare and use fractions", language_code="en-US")
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
            TaskOption(id="b", label="One third", correct=False, feedback="More equal cuts make smaller pieces, not bigger ones."),
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
        kind = "choose" if move == "teach" else "apply" if move == "independent" else "diagnose"
        return LearningTurn(
            speech="Equal pieces are comparable when they come from the same whole. More cuts make each piece smaller.",
            board_title="Equal-sized wholes",
            board_content="One bar cut into 4 equal pieces has larger pieces than an identical bar cut into 8.",
            task=task(kind, self.number),
        )


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
