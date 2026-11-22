"""Source+SQLite proof that a fallback scene remains durable without GuidedState."""
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from lyo_app.ai_classroom.scene_lifecycle_engine import (
    SceneLifecycleEngine, session_progress_key, _SESSION_PROGRESS,
)
from lyo_app.ai_classroom.sdui_models import Scene, SceneType, TeacherMessage
from lyo_app.classroom.models import ClassroomInteraction, ClassroomSession
from tests.adaptive_fixtures import action, context


@pytest.mark.asyncio
async def test_fallback_scene_persists_and_replays_without_guided_state():
    database = create_async_engine("sqlite+aiosqlite://")
    sid = "fallback-resume-" + uuid4().hex
    try:
        async with database.begin() as conn:
            await conn.run_sync(ClassroomSession.__table__.create)
            await conn.run_sync(ClassroomInteraction.__table__.create)
        ctx = context()
        ctx.session_id = sid
        initial = Scene(
            scene_id="saved-" + uuid4().hex,
            scene_type=SceneType.INSTRUCTION,
            components=[TeacherMessage(text="We can continue this lesson safely.")],
        )
        turn = action(welcome=True).model_copy(update={"session_id": sid})
        progress = {"last_scene": initial.model_dump(mode="json")}
        assert "guided_state" not in progress

        async with AsyncSession(database) as session:
            producer = SceneLifecycleEngine(session)
            assert await producer._persist_session_progress(
                turn, ctx, progress, record_interaction=False
            )

        _SESSION_PROGRESS.pop(session_progress_key("42", sid), None)
        async with AsyncSession(database) as session:
            restored = SceneLifecycleEngine(session)
            scene = await restored.resume_saved_scene("42", sid)
            assert scene is not None
            assert scene.scene_id == initial.scene_id
            assert scene.model_dump(mode="json") == initial.model_dump(mode="json")
            assert await restored.resume_saved_scene("43", sid) is None
    finally:
        _SESSION_PROGRESS.pop(session_progress_key("42", sid), None)
        _SESSION_PROGRESS.pop(session_progress_key("43", sid), None)
        await database.dispose()
