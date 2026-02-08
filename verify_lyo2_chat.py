import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

sys.path.append(os.getcwd())

# --- FULL MOCK SETUP ---

# 1. Config & Database
mock_config = MagicMock()
sys.modules["lyo_app.core.config"] = mock_config
mock_config.settings = MagicMock()
mock_config.settings.google_api_key = "fake_key"
sys.modules["lyo_app.core.database"] = MagicMock()

# 2. Auth Dependencies
mock_auth_deps = MagicMock()
sys.modules["lyo_app.auth.dependencies"] = mock_auth_deps
mock_auth_deps.get_current_user_or_guest = MagicMock()
mock_auth_deps.get_db = MagicMock()
sys.modules["lyo_app.auth.schemas"] = MagicMock()

# 3. AI Services & Agents (Prevent module-level init lag)
mock_router_module = MagicMock()
# Make MultimodalRouter a class that returns a mock
class MockMultimodalRouter:
    async def route(self, request):
         # This will be overridden in the test, but good default
         return MagicMock()
mock_router_module.MultimodalRouter = MockMultimodalRouter
sys.modules["lyo_app.ai.router"] = mock_router_module

mock_planner_module = MagicMock()
mock_planner_module.LyoPlanner = MagicMock() # Returns a mock planner
sys.modules["lyo_app.ai.planner"] = mock_planner_module

mock_executor_module = MagicMock()
mock_executor_module.LyoExecutor = MagicMock() # Returns a mock executor
sys.modules["lyo_app.ai.executor"] = mock_executor_module

# 4. Helper Services
sys.modules["lyo_app.services.rag_service"] = MagicMock()
sys.modules["lyo_app.services.mutator"] = MagicMock()
sys.modules["lyo_app.services.artifact_service"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()

# --- IMPORTS AFTER MOCKS ---

from lyo_app.ai.schemas.lyo2 import RouterRequest, RouterResponse, RouterDecision, Intent
from lyo_app.api.v1.stream_lyo2 import stream_lyo2_chat, router_agent

# Mock Logic for Test
async def mock_router_route_logic(request):
    print(">>> [MOCK] Router.route called")
    decision = RouterDecision(
        intent=Intent.CHAT, # Force CHAT intent
        confidence=0.9,
    )
    return RouterResponse(decision=decision, trace_id="test-trace")

async def mock_process_stream_logic(*args, **kwargs):
    print(">>> [MOCK] AgentRegistry.process_stream called")
    yield "Hello"
    yield " world"

async def test_lyo2_chat():
    print(">>> Setting up specific test logic...")
    
    # Override the instantiated router_agent's method
    # Note: stream_lyo2.py instantiates router_agent = MultimodalRouter() at module level.
    # So we need to patch specifically THAT instance, which we imported above.
    router_agent.route = AsyncMock(side_effect=mock_router_route_logic)
    
    # Mock Agent Registry (which is imported inside the logic flow or module level?)
    # In my refactor, I did: "from lyo_app.chat.agents import agent_registry" inside the function?
    # No, I did it inside the IF block! 
    # But wait, python imports are cached. If I mock "lyo_app.chat.agents" BEFORE calling the function, it should pick up the mock.
    
    mock_agents_module = MagicMock()
    mock_registry = MagicMock()
    mock_registry.process_stream = mock_process_stream_logic
    mock_agents_module.agent_registry = mock_registry
    
    # Patch the module in sys.modules so the local import inside stream_lyo2_chat picks it up
    sys.modules["lyo_app.chat.agents"] = mock_agents_module
    
    # Also need ChatMode
    mock_chat_models = MagicMock()
    class MockChatMode:
        GENERAL = "general"
    mock_chat_models.ChatMode = MockChatMode
    sys.modules["lyo_app.chat.models"] = mock_chat_models

    # Create Dummy Request
    req = RouterRequest(
        user_id="test_user",
        text="Hi",
        conversation_history=[]
    )
    
    mock_user = MagicMock()
    mock_user.id = "test_user"
    mock_db = AsyncMock()
    
    print(">>> Executing Stream Endpoint...")
    
    # Get the response (StreamingResponse)
    try:
        response = await stream_lyo2_chat(req, MagicMock(), mock_user, mock_db)
        
        print(">>> Reading Stream...")
        chunk_count = 0
        tokens = []
        
        # Iterate over the generator
        async for chunk in response.body_iterator:
            print(f"Chunk: {chunk.strip()}")
            if "token" in chunk:
                chunk_count += 1
                try:
                    data = json.loads(chunk.replace("data: ", ""))
                    if data["type"] == "token":
                        tokens.append(data["token"])
                except:
                    pass

        print(f"\n>>> Total Token Chunks: {chunk_count}")
        print(f">>> Full Text: {''.join(tokens)}")
        
        if chunk_count > 0:
            print(">>> SUCCESS: Streamed tokens via CHAT fast track.")
        else:
            print(">>> FAILURE: No tokens streamed.")
            
    except Exception as e:
        print(f"Endpoint Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        print(">>> Starting verification script...")
        asyncio.run(test_lyo2_chat())
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
