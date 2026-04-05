import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from lyo_app.ai.executor import LyoExecutor
from lyo_app.ai.schemas.lyo2 import LyoPlan, Intent, ActionType, PlannedAction, UIBlockType

@pytest.mark.asyncio
async def test_executor_course_generation_payload():
    """
    Directly test that LyoExecutor.execute populates open_classroom_payload
    by mocking the internal _generate_course_data method.
    """
    # 1. Setup executor and mock its dependencies
    executor = LyoExecutor()
    executor.rag = AsyncMock()
    executor.artifacts = AsyncMock()
    executor.mutator = AsyncMock()
    
    # 2. Mock the internal course data generator
    mock_course_data = {
        "title": "Introduction to Python",
        "topic": "Python",
        "description": "A magical journey into Python programming.",
        "difficulty": "Beginner",
        "estimated_duration": "45 min",
        "objectives": ["Variables", "Loops", "Functions"],
        "lessons": [
            {"title": "Lesson 1", "description": "Overview", "type": "reading", "duration": "10 min"}
        ]
    }
    
    executor._generate_course_data = AsyncMock(return_value=mock_course_data)
    
    # Also mock _generate_text so it doesn't try to call real AI
    executor._generate_text = AsyncMock(return_value="Hello! I've built your course.")
    
    # 3. Define a simple plan
    plan = LyoPlan(
        steps=[
            PlannedAction(
                action_type=ActionType.GENERATE_TEXT,
                description="Greeting",
                parameters={"content": "Hello! I've built your course."}
            )
        ]
    )
    
    # 4. Execute with COURSE intent
    response = await executor.execute(
        user_id="test_user",
        plan=plan,
        original_request="Build me a course on Python",
        intent="COURSE"
    )
    
    # 5. Verify rendering payload
    assert response.open_classroom_payload is not None
    assert response.open_classroom_payload["title"] == "Introduction to Python"
    assert response.open_classroom_payload["topic"] == "Python"
    assert len(response.open_classroom_payload["lessons"]) == 1
    
    # Verify the tutor message block is rendered correctly
    assert response.answer_block.type == UIBlockType.TUTOR_MESSAGE
    assert "Hello!" in response.answer_block.content["text"]
    
    # Verify next actions are present (CTA for courses)
    assert len(response.next_actions) > 0
    assert response.next_actions[0].type == UIBlockType.CTA_ROW

@pytest.mark.asyncio
async def test_executor_course_generation_intent_trigger():
    """
    Verify that open_classroom_payload is NOT populated for non-COURSE intents.
    """
    executor = LyoExecutor()
    executor.rag = AsyncMock()
    executor.artifacts = AsyncMock()
    executor.mutator = AsyncMock()
    executor._generate_text = AsyncMock(return_value="I'm explaining Python.")
    
    plan = LyoPlan(steps=[PlannedAction(action_type=ActionType.GENERATE_TEXT, description="Explain")])
    
    response = await executor.execute(
        user_id="test_user",
        plan=plan,
        original_request="Explain Python variables",
        intent="EXPLAIN" # Not COURSE
    )
    
    assert response.open_classroom_payload is None
    assert "explaining" in response.answer_block.content["text"].lower()

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
