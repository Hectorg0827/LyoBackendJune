
import asyncio
import logging
from unittest.mock import AsyncMock, patch
from lyo_app.chat.router import ChatRouter, ChatMode

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_router():
    router = ChatRouter()
    
    print("\n--- Testing Chat Router ---")
    
    # Test Case 1: Regex Match (Fast Pass)
    msg1 = "Quiz me on Swift"
    mode1, conf1, reason1 = await router.route(msg1)
    print(f"Input: '{msg1}' -> Mode: {mode1.value}, Conf: {conf1}, Reason: {reason1}")
    assert mode1 == ChatMode.PRACTICE
    assert "strong pattern match" in reason1.lower() or "pattern match" in reason1.lower()
    
    # Test Case 2: Semantic Match (Smart Pass)
    # Mocking semantic route to simulate LLM response
    msg2 = "I want to verify my knowledge about closures"
    # This might fail regex but should pass semantic
    
    # We must patch the source because chat.router imports it inside the function
    with patch('lyo_app.core.ai_resilience.ai_resilience_manager') as mock_ai:
        mock_ai.chat_completion = AsyncMock(return_value={
            "content": '{"mode": "PRACTICE", "reasoning": "User wants to verify knowledge"}'
        })
        
        mode2, conf2, reason2 = await router.route(msg2)
        print(f"Input: '{msg2}' -> Mode: {mode2.value}, Conf: {conf2}, Reason: {reason2}")
        assert mode2 == ChatMode.PRACTICE
        assert "semantic routing" in reason2.lower()

    # Test Case 3: Course Creation
    msg3 = "I need a curriculum for Roman History"
    with patch('lyo_app.core.ai_resilience.ai_resilience_manager') as mock_ai:
        mock_ai.chat_completion = AsyncMock(return_value={
            "content": '{"mode": "COURSE_PLANNER", "reasoning": "User asked for a curriculum"}'
        })
        mode3, conf3, reason3 = await router.route(msg3)
        print(f"Input: '{msg3}' -> Mode: {mode3.value}, Conf: {conf3}, Reason: {reason3}")
        assert mode3 == ChatMode.COURSE_PLANNER

    print("\n✅ Router Verification Passed!")

if __name__ == "__main__":
    asyncio.run(test_router())
