"""Completion is server-authoritative and cannot precede durable saving."""

import pytest

from lyo_app.ai_classroom.adaptive_teaching import GuidedState
from lyo_app.ai_classroom.scene_lifecycle_engine import _SESSION_PROGRESS, session_progress_key
from tests.adaptive_fixtures import action, context, engine, plan


@pytest.mark.asyncio
@pytest.mark.parametrize("saved,skipped,total_lessons,expected", [
    (True, [], 1, True),
    (False, [], 1, False),
    (True, [0], 1, False),
    (True, [], 2, False),
])
async def test_guided_completion_metadata_requires_saved_final_work(saved, skipped, total_lessons, expected):
    ctx = context(session_id=f"completion-{saved}-{skipped}-{total_lessons}", total_lessons=total_lessons)
    instance = engine(ctx)
    instance._persist_session_progress.return_value = saved
    state = GuidedState(owner=ctx.user_id, plan=plan(1), path_done=True,
                        completed=[] if skipped else [0], skipped=skipped)
    key = session_progress_key(ctx.user_id, ctx.session_id)
    _SESSION_PROGRESS[key] = {"guided_state": state.model_dump(mode="json")}
    try:
        trigger = action(welcome=True)
        trigger.session_id = ctx.session_id
        scene = await instance.process_trigger(trigger)
        assert scene.metadata.course_complete is expected
    finally:
        _SESSION_PROGRESS.pop(key, None)
