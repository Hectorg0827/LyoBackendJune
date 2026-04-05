import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from lyo_app.ai.router import MultimodalRouter
from lyo_app.ai.planner import LyoPlanner
from lyo_app.ai.schemas.lyo2 import RouterRequest, RouterDecision, Intent

@pytest.fixture
def router():
    return MultimodalRouter()

@pytest.fixture
def planner():
    return LyoPlanner()

@pytest.mark.asyncio
async def test_router_classification_weekly_review(router):
    # Test keyword fallback for Weekly Review
    request = RouterRequest(user_id="test_user", text="how am i doing overall this week")
    
    # We mock execute to force the failure and trigger keyword fallback
    with patch.object(router, 'execute', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = MagicMock(success=False, error="Mocked Failure")
        response = await router.route(request)
        assert response.decision.intent == Intent.WEEKLY_REVIEW
        assert response.decision.suggested_tier == "MEDIUM"

@pytest.mark.asyncio
async def test_router_classification_reflect(router):
    # Test keyword fallback for Reflect
    request = RouterRequest(user_id="test_user", text="i feel frustrated with calculus")
    
    with patch.object(router, 'execute', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = MagicMock(success=False, error="Mocked Failure")
        response = await router.route(request)
        assert response.decision.intent == Intent.REFLECT
        assert response.decision.suggested_tier == "TINY"

@pytest.mark.asyncio
async def test_planner_logic(planner):
    request = RouterRequest(user_id="test_user", text="this was hard")
    decision = RouterDecision(intent=Intent.REFLECT, confidence=0.9, suggested_tier="TINY")
    
    # Mocking execution to see if it would return a plan (we'll just check if it's called with the right data)
    with patch.object(planner, 'execute', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = MagicMock(success=True, data=MagicMock(steps=[]))
        await planner.plan(request, decision)
        # Check if the prompt contains the reflection intent rules (this is hard to test directly without checking internal strings)
        # For now, just ensure it doesn't crash.
        pass

@pytest.mark.asyncio
async def test_router_real_prompt_content(router):
    # This verifies the system prompt was updated
    prompt = router.get_system_prompt()
    assert "REFLECT:" in prompt
    assert "WEEKLY_REVIEW:" in prompt

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
