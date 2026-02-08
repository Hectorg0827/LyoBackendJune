
import asyncio
import os
import sys

# Add the project root to sys.path
sys.path.append("/Users/hectorgarcia/Desktop/LyoBackendJune")

async def test_agent_init():
    try:
        from lyo_app.core.enhanced_config import settings
        print(f"DEBUG: settings.ENVIRONMENT = {settings.ENVIRONMENT}")
        print(f"DEBUG: has GOOGLE_API_KEY = {bool(getattr(settings, 'GOOGLE_API_KEY', None))}")
        print(f"DEBUG: has google_api_key = {bool(getattr(settings, 'google_api_key', None))}")
        print(f"DEBUG: has GEMINI_API_KEY = {bool(getattr(settings, 'GEMINI_API_KEY', None))}")
        print(f"DEBUG: has gemini_api_key = {bool(getattr(settings, 'gemini_api_key', None))}")
        
        from lyo_app.ai_agents.multi_agent_v2.agents.base_agent import BaseAgent
        from pydantic import BaseModel
        
        class MockOutput(BaseModel):
            decision: str
            
        agent = BaseAgent(
            name="TestAgent",
            output_schema=MockOutput,
            model_name="gemini-2.0-flash"
        )
        
        print(f"DEBUG: Agent available: {agent.is_available}")
        if agent.model:
            print(f"DEBUG: Agent model type: {type(agent.model)}")
        else:
            print("DEBUG: Agent model is None")
            
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_agent_init())
