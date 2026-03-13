import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from lyo_app.ai_agents.a2a.orchestrator import A2AOrchestrator, PipelinePhase, EventType, PipelineConfig
from lyo_app.ai_agents.a2a.schemas import A2ACourseRequest, StreamingEvent

@pytest.mark.asyncio
async def test_orchestrator_streaming_with_qa_gate():
    """Test that the orchestrator streams events and handles the QA gate."""
    
    # 1. Setup Request & Config
    request = A2ACourseRequest(
        topic="Testing Orchestrator",
        difficulty="intermediate",
        quality_tier="premium"
    )
    config = PipelineConfig(enable_qa=True, enable_streaming=True)
    
    # Create instance BUT mock redis before it can fail or hang
    with MagicMock() as mock_redis:
        orchestrator = A2AOrchestrator(config=config)
        orchestrator.redis = mock_redis
        mock_redis.set = AsyncMock()
        
    orchestrator._save_state = AsyncMock()
    
    # 2. Mock Agent Executes
    orchestrator.pedagogy_agent.execute = AsyncMock(return_value=MagicMock(dict=lambda: {"objectives": ["Test"]}))
    orchestrator.researcher_agent.execute = AsyncMock(return_value=MagicMock(dict=lambda: {"data": "research"}))
    orchestrator.visual_agent.execute = AsyncMock(return_value=MagicMock(dict=lambda: {"assets": []}))
    orchestrator.voice_agent.execute = AsyncMock(return_value=MagicMock(dict=lambda: {"scripts": []}))
    
    # Mock Cinematic rejection/success
    cinematic_mock = AsyncMock()
    cinematic_mock.side_effect = [
        MagicMock(dict=lambda: {"modules": [{"title": "Initial Fail"}]}),
        MagicMock(dict=lambda: {"modules": [{"title": "Final Success"}]})
    ]
    orchestrator.cinematic_agent.execute = cinematic_mock
    
    # Mock QA rejection/success
    qa_mock = AsyncMock()
    qa_mock.side_effect = [
        MagicMock(dict=lambda: {"approval_status": "needs_revision", "issues": [{"description": "Missing depth"}]}, overall_quality_score=60.0),
        MagicMock(dict=lambda: {"approval_status": "approved", "issues": []}, overall_quality_score=95.0)
    ]
    orchestrator.qa_agent.execute = qa_mock
    
    # 3. Execution
    events = []
    # Set a total timeout to prevent hang
    try:
        async with asyncio.timeout(10): 
            async for event in orchestrator.generate_course_streaming(request):
                events.append(event)
    except asyncio.TimeoutError:
        pytest.fail("Orchestrator generation timed out - potentially stuck in a loop")
        
    # 4. Assertions
    assert len(events) > 0
    assert cinematic_mock.call_count == 2
    assert any(e.type == EventType.PIPELINE_COMPLETED for e in events)

@pytest.mark.asyncio
async def test_fast_tier_skips_qa():
    """Test that 'fast' tier bypasses QA for ultra-low latency."""
    request = A2ACourseRequest(
        topic="Fast Course",
        quality_tier="fast"
    )
    orchestrator = A2AOrchestrator()
    orchestrator.redis = MagicMock()
    orchestrator._save_state = AsyncMock()
    orchestrator.qa_agent.execute = AsyncMock()
    
    # Mock all preceding phases
    orchestrator._initialize = AsyncMock(return_value={})
    orchestrator._run_research = AsyncMock(return_value={})
    orchestrator._run_pedagogy = AsyncMock(return_value={})
    orchestrator._run_cinematic = AsyncMock(return_value={"modules": []})
    
    # Async generator mock for _run_parallel_streaming
    async def mock_parallel():
        yield StreamingEvent(type=EventType.PHASE_PROGRESS, task_id="1", agent_name="test", message="test")

    orchestrator._run_parallel_streaming = mock_parallel
    
    events = []
    async for event in orchestrator.generate_course_streaming(request):
        events.append(event)
        
    assert orchestrator.qa_agent.execute.call_count == 0
