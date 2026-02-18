
import asyncio
import json
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from unittest.mock import MagicMock, patch
from lyo_app.chat.agents import TestPrepAgent, ChatMode

# Mock response from LLM
MOCK_LLM_RESPONSE = """
Here is your study plan for the chemistry test.

{
    "type": "STUDY_PLAN",
    "payload": {
        "plan_id": "plan-123",
        "title": "Chemistry Midterm Prep",
        "test_date": "2024-10-25T09:00:00Z",
        "sessions": [
            {
                "id": "s1",
                "title": "Stoichiometry Basics",
                "description": "Review mole concept and balancing equations",
                "topic": "Stoichiometry",
                "duration_minutes": 45,
                "activity_type": "review"
            }
        ]
    }
}
"""

async def test_test_prep_agent():
    print("🧪 Verifying TestPrepAgent flow...")
    
    # Mock the ai_resilience_manager used in BaseAgent.call_ai
    with patch("lyo_app.chat.agents.ai_resilience_manager") as mock_ai:
        # Setup mock return value
        future = asyncio.Future()
        future.set_result({
            "content": MOCK_LLM_RESPONSE,
            "usage": {"total_tokens": 150},
            "model": "gpt-4-mock"
        })
        mock_ai.chat_completion.return_value = future
        
        agent = TestPrepAgent()
        
        # Test processing
        print("   - Calling agent.process()...")
        result = await agent.process("I have a chemistry test on Friday")
        
        # Verification
        print("   - Verifying result structure...")
        
        # 1. Check Response Text
        if result["response"] != MOCK_LLM_RESPONSE:
            print("❌ Response text mismatch")
            return
        
        # 2. Check Study Plan Extraction
        study_plan = result.get("study_plan")
        if not study_plan:
            print("❌ Failed to extract study_plan")
            print(f"Result keys: {result.keys()}")
            return
            
        if study_plan["title"] != "Chemistry Midterm Prep":
             print(f"❌ Wrong plan title: {study_plan['title']}")
             return
             
        if len(study_plan["sessions"]) != 1:
            print("❌ Wrong number of sessions")
            return
            
        print("   ✅ Study Plan extracted successfully")
        
        # 3. Check CTAs
        ctas = result.get("ctas", [])
        if not ctas:
            print("❌ No CTAs returned")
            return
            
        has_calendar = any(cta["action"] == "add_calendar" for cta in ctas)
        if not has_calendar:
            print("❌ Missing 'add_calendar' CTA")
            return
            
        print("   ✅ CTAs populated correctly")
        
        print("\n🎉 TestPrepAgent Logic Verified!")

if __name__ == "__main__":
    asyncio.run(test_test_prep_agent())
