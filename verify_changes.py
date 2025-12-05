import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from lyo_app.ai_agents.mentor_agent import ai_mentor
from lyo_app.ai_agents.schemas import ResponseModeEnum
from lyo_app.ai_agents.orchestrator import ModelType

async def verify_modes():
    print("Verifying Mentor Agent Modes...")
    
    # Mock DB
    mock_db = AsyncMock()
    mock_db.get.return_value = MagicMock(state="neutral")
    
    # 1. Verify Explainer Mode
    print("\n1. Testing Quick Explainer Mode...")
    explainer_json = {
        "concept": "PEMDAS",
        "explanation": "Parentheses, Exponents...",
        "chips": ["Practice", "Examples"]
    }
    
    # Mock orchestrator for explainer
    mock_response_explainer = MagicMock()
    mock_response_explainer.content = f"[MODE: EXPLAINER] {json.dumps(explainer_json)}"
    mock_response_explainer.model_used = ModelType.GEMMA_4_ON_DEVICE
    mock_response_explainer.response_time_ms = 100.0
    
    # Patch orchestrator in the module
    with patch("lyo_app.ai_agents.mentor_agent.ai_orchestrator") as mock_orchestrator, \
         patch("lyo_app.ai_agents.mentor_agent.MentorInteraction") as MockMentorInteraction, \
         patch("lyo_app.ai_agents.mentor_agent.UserEngagementState") as MockUserEngagementState:
        
        # Setup mocks
        mock_orchestrator.generate_response = AsyncMock(return_value=mock_response_explainer)
        
        # Mock MentorInteraction instance
        mock_interaction_instance = MagicMock()
        mock_interaction_instance.id = 123
        MockMentorInteraction.return_value = mock_interaction_instance
        
        response = await ai_mentor.get_response(1, "Explain PEMDAS", mock_db)
        
        if response["response_mode"] == ResponseModeEnum.EXPLAINER:
            print("✅ Response mode is EXPLAINER")
        else:
            print(f"❌ Expected EXPLAINER, got {response['response_mode']}")
            
        if response["quick_explainer"].concept == "PEMDAS":
            print("✅ Concept data matches")
        else:
            print("❌ Concept data mismatch")

        # 2. Verify Course Mode
        print("\n2. Testing Course Mode...")
        course_json = {
            "title": "Math 101",
            "subtext": "Basics",
            "summary": "Intro to Math",
            "modules": ["Add", "Sub"],
            "button_text": "Start"
        }
        
        # Mock orchestrator for course
        mock_response_course = MagicMock()
        mock_response_course.content = f"[MODE: COURSE] {json.dumps(course_json)}"
        mock_response_course.model_used = ModelType.GEMMA_4_ON_DEVICE
        mock_response_course.response_time_ms = 100.0
        
        mock_orchestrator.generate_response.return_value = mock_response_course
        
        response = await ai_mentor.get_response(1, "Teach me math", mock_db)
        
        if response["response_mode"] == ResponseModeEnum.COURSE:
            print("✅ Response mode is COURSE")
        else:
            print(f"❌ Expected COURSE, got {response['response_mode']}")
            
        if response["course_proposal"].title == "Math 101":
            print("✅ Course data matches")
        else:
            print("❌ Course data mismatch")

if __name__ == "__main__":
    # Mock the ai_orchestrator import in mentor_agent if needed, 
    # but here we are patching the instance attribute directly which is easier
    
    # We need to mock the ai_orchestrator module before importing if it does heavy init
    # But we already imported it. Let's just run.
    asyncio.run(verify_modes())
