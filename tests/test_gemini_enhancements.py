"""
Integration Tests for Gemini API Enhancements

Tests all 4 phases of enhancements:
- Phase 1: Quality tiers & cost estimation
- Phase 2: Streaming generation
- Phase 3: Smart routing & caching
- Phase 4: Analytics tracking
"""

import os
import pytest
import asyncio
from fastapi.testclient import TestClient


# Test Phase 1: Cost Estimation & Quality Tiers
def test_cost_estimation(client: TestClient):
    """Test cost estimation endpoint"""
    response = client.post(
        "/api/v2/courses/estimate-cost",
        json={
            "topic": "Python Programming for Beginners",
            "quality_tier": "balanced",
            "enable_code_examples": True,
            "enable_practice_exercises": True,
            "enable_final_quiz": True
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Check response structure
    assert "estimated_cost_usd" in data
    assert "estimated_generation_time_sec" in data
    assert "quality_tier" in data
    assert "recommendations" in data
    
    # Verify cost is reasonable
    assert 0.01 <= data["estimated_cost_usd"] <= 0.25
    
    # Check recommendations exist
    assert isinstance(data["recommendations"], list)


def test_quality_tiers(client: TestClient):
    """Test different quality tiers have different costs"""
    tiers = ["fast", "balanced", "ultra"]
    costs = []
    
    for tier in tiers:
        response = client.post(
            "/api/v2/courses/estimate-cost",
            json={
                "topic": "JavaScript Basics",
                "quality_tier": tier,
                "enable_code_examples": True
            }
        )
        assert response.status_code == 200
        costs.append(response.json()["estimated_cost_usd"])
    
    # Verify: FAST < BALANCED < ULTRA
    assert costs[0] < costs[1] < costs[2]


def test_budget_validation(client: TestClient):
    """Test budget validation rejects over-budget requests"""
    response = client.post(
        "/api/v2/courses/generate",
        json={
            "request": "Create comprehensive Python course",
            "quality_tier": "ultra",
            "max_budget_usd": 0.01  # Too low for ULTRA
        }
    )
    
    assert response.status_code == 400
    # The error middleware reshapes HTTPException payloads; match on text.
    assert "exceeds budget" in response.text.lower()


# Test Phase 2: Streaming
@pytest.mark.asyncio
async def test_streaming_generation():
    if os.environ.get("LIVE_BACKEND_TESTS") != "1":
        pytest.skip("requires a live backend on localhost:8000; set LIVE_BACKEND_TESTS=1")
    """Test SSE streaming endpoint"""
    import httpx
    
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        async with client.stream(
            "POST",
            "/api/v2/courses/generate/stream",
            json={
                "request": "Quick Python basics course",
                "quality_tier": "fast"
            },
            headers={"Accept": "text/event-stream"}
        ) as response:
            assert response.status_code == 200
            
            events_received = []
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    events_received.append(line)
                    
                    # Stop after a few events (don't wait for full generation)
                    if len(events_received) >= 3:
                        break
            
            # Verify we received events
            assert len(events_received) > 0


# Test Phase 3: Smart Routing
@pytest.mark.asyncio
async def test_smart_routing():
    """Test intent detection"""
    from lyo_app.ai_agents.multi_agent_v2.smart_router import SmartRouter
    
    # Test quick explainer detection
    explainer_request = "Explain what recursion is"
    intent = SmartRouter.detect_intent(explainer_request)
    assert intent.intent_type == "quick_explainer"
    assert intent.confidence > 0.7
    
    # Test full course detection
    course_request = "Create a comprehensive Python programming course"
    intent = SmartRouter.detect_intent(course_request)
    assert intent.intent_type == "full_course"
    assert intent.confidence > 0.8
    
    # Test quiz detection
    quiz_request = "Give me 10 quiz questions on JavaScript"
    intent = SmartRouter.detect_intent(quiz_request)
    assert intent.intent_type == "quiz_only"


@pytest.mark.asyncio
async def test_curriculum_caching():
    """Test curriculum caching"""
    from lyo_app.ai_agents.multi_agent_v2.caching import CurriculumCache
    
    # Note: Requires Redis to be running
    cache = CurriculumCache(redis_url="redis://localhost:6379")
    
    if cache.enabled:
        # Test cache miss
        result = await cache.get("Python Programming", "beginner", 8)
        assert result is None  # First call should miss
        
        # Get stats
        stats = await cache.get_stats()
        assert stats["enabled"] == True
    else:
        pytest.skip("Redis not available")


# Test Phase 4: Analytics
def test_user_analytics(client: TestClient):
    """Test user analytics endpoint"""
    response = client.get("/api/v2/courses/analytics/user/test_user_123?days=30")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check structure (UsageTracker.get_user_analytics shape)
    assert "total_courses" in data
    assert "total_cost" in data
    assert "total_tokens" in data


def test_system_analytics(client: TestClient):
    """Test system-wide analytics"""
    response = client.get("/api/v2/courses/analytics/system?days=7")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check structure (empty tracker returns only total_generations)
    assert "total_generations" in data


@pytest.mark.asyncio
async def test_usage_tracking():
    """Test usage tracking system"""
    from lyo_app.ai_agents.multi_agent_v2.analytics import UsageTracker
    
    tracker = UsageTracker()
    
    # Start tracking
    gen_id = await tracker.start_tracking(
        user_id="test_user",
        topic="Python Test",
        quality_tier="balanced"
    )
    
    assert gen_id is not None
    
    # Update metrics
    await tracker.update_metrics(gen_id, {
        "orchestrator_tokens": 1000,
        "orchestrator_cost": 0.01
    })
    
    # Get analytics
    analytics = await tracker.get_user_analytics("test_user", days=1)
    assert analytics["total_courses"] >= 1


# Integration Test: Full Flow
@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_generation_flow():
    if os.environ.get("LIVE_BACKEND_TESTS") != "1":
        pytest.skip("requires a live backend on localhost:8000; set LIVE_BACKEND_TESTS=1")
    """End-to-end test of course generation with all enhancements"""
    import httpx
    
    client = httpx.AsyncClient(base_url="http://localhost:8000", timeout=120.0)
    
    try:
        # Step 1: Get cost estimate
        estimate_response = await client.post(
            "/api/v2/courses/estimate-cost",
            json={
                "topic": "Test Course Integration",
                "quality_tier": "fast"
            }
        )
        assert estimate_response.status_code == 200
        estimated_cost = estimate_response.json()["estimated_cost_usd"]
        
        # Step 2: Generate course (non-streaming)
        gen_response = await client.post(
            "/api/v2/courses/generate",
            json={
                "request": "Test Course Integration",
                "quality_tier": "fast",
                "max_budget_usd": estimated_cost * 2  # Allow some buffer
            }
        )
        assert gen_response.status_code == 200
        job_id = gen_response.json()["job_id"]
        
        # Step 3: Poll for completion (simplified - would need to wait in real scenario)
        status_response = await client.get(f"/api/v2/courses/status/{job_id}")
        assert status_response.status_code == 200
        
        # Step 4: Check analytics updated
        analytics_response = await client.get("/api/v2/courses/analytics/system?days=1")
        assert analytics_response.status_code == 200
        
    finally:
        await client.aclose()


# Pytest configuration
@pytest.fixture
def client():
    """Create test client (auth overridden — endpoints use or-guest auth
    that otherwise requires an X-API-Key header)."""
    from unittest.mock import MagicMock

    from lyo_app.auth.dependencies import get_current_user_or_guest
    from lyo_app.enhanced_main import app

    user = MagicMock()
    user.id = "test_user_123"
    app.dependency_overrides[get_current_user_or_guest] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user_or_guest, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
