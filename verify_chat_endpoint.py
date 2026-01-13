
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_chat_endpoint():
    print("🧪 Testing chat endpoint logic...")
    
    # Mock dependencies
    with patch('lyo_app.api.v1.chat.PersonalizationEngine') as MockPersonalization, \
         patch('lyo_app.api.v1.chat.ai_resilience_manager') as mock_ai_manager, \
         patch('lyo_app.api.v1.chat.get_current_user') as mock_get_user, \
         patch('lyo_app.api.v1.chat.get_db') as mock_get_db:
        
        # Setup PersonalizationEngine mock
        mock_engine = MockPersonalization.return_value
        mock_engine.build_prompt_context.return_value = "User context"
        mock_engine.get_mastery_profile.return_value = MagicMock(model_dump=lambda: {"level": "beginner"})
        
        # Setup AI Resilience Manager mock
        mock_ai_manager.chat_completion = AsyncMock(return_value={
            "content": "Hello! I am Lyo.",
            "model": "gemini-2.5-flash"
        })
        
        # Import the router handler
        from lyo_app.api.v1.chat import chat, ChatRequest
        from lyo_app.auth.models import User
        
        # Create mock user and db
        mock_user = User(id=1, email="test@example.com")
        mock_db = AsyncMock()
        
        # Create request
        request = ChatRequest(message="Hello")
        
        # Call the endpoint handler directly
        print("🚀 Calling chat()...")
        response = await chat(request, current_user=mock_user, db=mock_db)
        
        # Verify response
        print(f"✅ Response: {response.response}")
        assert response.response == "Hello! I am Lyo."
        assert response.success is True
        
        print("✨ Chat endpoint verification successful!")

if __name__ == "__main__":
    try:
        asyncio.run(test_chat_endpoint())
    except Exception as e:
        print(f"❌ Test failed: {e}")
