import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch

# --- SUPER MOCKING ---
from sqlalchemy.orm import DeclarativeBase
class Base(DeclarativeBase):
    pass

# Mock everything that might hang or cause issues during import
mock_fastapi = MagicMock()
def mock_decorator(*args, **kwargs):
    return lambda f: f
mock_fastapi.APIRouter.return_value.get = mock_decorator
mock_fastapi.APIRouter.return_value.post = mock_decorator
sys.modules["fastapi"] = mock_fastapi
sys.modules["fastapi.security"] = MagicMock()

class FakeStreamingResponse:
    def __init__(self, generator, **kwargs):
        self.body_iterator = generator
mock_responses = MagicMock()
mock_responses.StreamingResponse = FakeStreamingResponse
sys.modules["fastapi.responses"] = mock_responses

mock_db = MagicMock()
mock_db.Base = Base
sys.modules["lyo_app.core.database"] = mock_db

sys.modules["lyo_app.core.config"] = MagicMock()
sys.modules["lyo_app.auth.dependencies"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()
sys.modules["lyo_app.services.rag_service"] = MagicMock()
sys.modules["lyo_app.services.mutator"] = MagicMock()
sys.modules["lyo_app.services.artifact_service"] = MagicMock()
sys.modules["lyo_app.ai.planner"] = MagicMock()
sys.modules["lyo_app.ai.executor"] = MagicMock()

# Mock api.v1 submodules to satisfy __init__.py
sys.modules["lyo_app.api.v1.chat_lyo2"] = MagicMock()
# sys.modules["lyo_app.api.v1.stream_lyo2"] = MagicMock() <--- DO NOT MOCK THE TARGET
sys.modules["lyo_app.api.v1.health"] = MagicMock()
sys.modules["lyo_app.api.v1.auth"] = MagicMock()
sys.modules["lyo_app.api.v1.courses"] = MagicMock()
sys.modules["lyo_app.api.v1.tasks"] = MagicMock()
sys.modules["lyo_app.api.v1.websocket"] = MagicMock()
sys.modules["lyo_app.api.v1.feeds"] = MagicMock()
sys.modules["lyo_app.api.v1.gamification"] = MagicMock()
sys.modules["lyo_app.api.v1.push"] = MagicMock()

# Mock Chat and Agents
mock_chat = MagicMock()
sys.modules["lyo_app.chat"] = mock_chat
mock_chat_models = MagicMock()
class ChatMode:
    GENERAL = "general"
mock_chat_models.ChatMode = ChatMode
sys.modules["lyo_app.chat.models"] = mock_chat_models
sys.modules["lyo_app.chat.agents"] = MagicMock()

# Pre-mock MultimodalRouter to prevent blocking init
mock_router_module = MagicMock()
class FakeRouter:
    def __init__(self, *args, **kwargs): pass
    async def route(self, *args, **kwargs): pass
mock_router_module.MultimodalRouter = FakeRouter
sys.modules["lyo_app.ai.router"] = mock_router_module

# Now import the logic after mocks
# We need to manually handle the imports that stream_lyo2.py does
from lyo_app.ai.schemas.lyo2 import RouterRequest, RouterResponse, RouterDecision, Intent

# We want to test this function:
# from lyo_app.api.v1.stream_lyo2 import stream_lyo2_chat

async def test_fast_track_logic():
    print(">>> Starting Fast Track Logic Test")
    
    # Mock dependencies for the function
    mock_user = MagicMock()
    mock_db = MagicMock()
    
    # Mock the router agent behavior
    mock_router_decision = RouterDecision(intent=Intent.CHAT, confidence=0.99)
    mock_router_response = RouterResponse(decision=mock_router_decision, trace_id="test")
    
    # Mock Agent Registry
    mock_agent_registry = MagicMock()
    async def mock_gen(*args, **kwargs):
        yield "Hello"
        yield " from"
        yield " fast"
        yield " track"
    mock_agent_registry.process_stream = mock_gen

    # Import the module FIRST so it exists in sys.modules
    import lyo_app.api.v1.stream_lyo2 as stream_lyo2

    # Mock the internal imports inside the function
    with patch("lyo_app.api.v1.stream_lyo2.router_agent.route", new_callable=AsyncMock) as mock_route:
        mock_route.return_value = mock_router_response
        
        # Correctly patch the source of the import used inside the function
        with patch("lyo_app.chat.agents.agent_registry", mock_agent_registry):
            test_request = RouterRequest(
                user_id="test",
                text="Hi",
                conversation_history=[]
            )
            
            # Call the function
            print(">>> Calling stream_lyo2_chat...")
            # We pass None for response since we'll check the generator it returns in the StreamingResponse
            response_obj = await stream_lyo2.stream_lyo2_chat(test_request, MagicMock(), mock_user, mock_db)
            
            # StreamingResponse has a .body_iterator
            chunks = []
            async for chunk in response_obj.body_iterator:
                chunks.append(chunk)
            
            print(f">>> Received {len(chunks)} chunks.")
            full_text = "".join(chunks)
            
            # Assertions
            assert 'type": "skeleton"' in full_text
            assert "Hello" in full_text
            assert "fast track" in full_text
            assert 'type": "completion"' in full_text
            
            print(">>> SUCCESS: Fast track logic verified.")

if __name__ == "__main__":
    try:
        asyncio.run(test_fast_track_logic())
    except Exception as e:
        print(f">>> FAILED: {e}")
        import traceback
        traceback.print_exc()
