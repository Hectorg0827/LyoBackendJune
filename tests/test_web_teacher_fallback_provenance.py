"""Recovery scenes must never masquerade as model-generated instruction."""
from unittest.mock import AsyncMock

import pytest

from lyo_app.ai_classroom.adaptive_session import AdaptiveSession
from lyo_app.ai_classroom.scene_lifecycle_engine import SceneLifecycleEngine
from tests.adaptive_fixtures import context, action


def test_model_budget_fallback_scene_has_explicit_fallback_provenance():
    scene = AdaptiveSession(None).unavailable(context(), None)
    assert scene.metadata.scene_source == "fallback"
    assert scene.scene_id
    assert any(
        getattr(component, "presentation_role", None) == "recovery"
        for component in scene.components
    )
    assert any(getattr(component, "type", None) == "TeacherMessage"
               for component in scene.components)


@pytest.mark.asyncio
async def test_error_recovery_scene_has_explicit_fallback_provenance():
    engine = SceneLifecycleEngine(AsyncMock())
    scene = await engine._create_fallback_scene(action(welcome=True))
    assert scene.metadata.scene_source == "fallback"
    assert scene.scene_id
    assert scene.components
