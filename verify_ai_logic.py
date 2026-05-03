import sys
from unittest.mock import MagicMock

# Mock pgvector
pgvector_mock = MagicMock()
class MockVector(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.impl = MagicMock()
        
sys.modules["pgvector"] = pgvector_mock
sys.modules["pgvector.sqlalchemy"] = MagicMock()
sys.modules["pgvector.sqlalchemy"].Vector = MockVector

# Now import the test
import asyncio
import os
from lyo_app.ai_agents.a2a.orchestrator import A2AOrchestrator
from lyo_app.ai_agents.a2a.schemas import A2ACourseRequest

async def test_ai_generation():
    print("🤖 Testing AI Course Generation Logic...")
    
    # Ensure API keys are present (or will fallback)
    if not os.getenv("GEMINI_API_KEY"):
        print("⚠️ GEMINI_API_KEY not found in environment, using placeholder or expecting failure.")
        
    orchestrator = A2AOrchestrator()
    request = A2ACourseRequest(
        topic="Introduction to SwiftUI",
        user_id="test_user",
        level="beginner"
    )
    
    try:
        print("⏳ Calling Orchestrator (this may take a minute)...")
        # Use a shorter timeout for local test
        response = await orchestrator.generate_course(request)
        
        print("\n✅ Generation SUCCESS!")
        print(f"Title: {response.metadata.get('title')}")
        print(f"Artifacts: {len(response.artifacts)}")
        
        for art in response.artifacts:
            print(f"- {art.type}: {str(art.data)[:100]}...")
            
    except Exception as e:
        print(f"❌ Generation FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ai_generation())
