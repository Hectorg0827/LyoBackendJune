import sys
import os
print(">>> [DEBUG] Script started, sys.path and current dir set.")
import pytest
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from contextlib import asynccontextmanager

print(">>> [DEBUG] Standard libraries imported.")

# Mock dependencies before imports to prevent heavy init
from sqlalchemy.orm import DeclarativeBase

# Define a real Base for models to inherit from during tests
class Base(DeclarativeBase):
    pass

# Mock Redis
sys.modules["redis.asyncio"] = MagicMock()

# Mock Database but provide the real Base
mock_db = MagicMock()
mock_db.Base = Base
sys.modules["lyo_app.core.database"] = mock_db

# Mock AI modules
sys.modules["lyo_app.ai.next_gen_algorithm"] = MagicMock()
sys.modules["lyo_app.ai.gemma_local"] = MagicMock()

# Mock Config
mock_config = MagicMock()
mock_config.settings = MagicMock()
mock_config.settings.google_api_key = "fake_key"
mock_config.settings.database_url = "sqlite+aiosqlite:///:memory:"
sys.modules["lyo_app.core.config"] = mock_config

# Set Lightweight startup
import os
os.environ["LYO_LIGHTWEIGHT_STARTUP"] = "1"

# Now import app
from lyo_app.app_factory import app
from lyo_app.ai.schemas.lyo2 import RouterDecision, Intent, RouterResponse

client = TestClient(app)

# --- MOCK SETUP HELPERS ---

@pytest.fixture
def mock_auth():
    """Bypass authentication"""
    from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
    
    # Create a dummy user
    mock_user = MagicMock()
    mock_user.id = "test_user_123"
    
    # Override dependency
    app.dependency_overrides[get_current_user_or_guest] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: AsyncMock() # Mock DB Session
    
    yield
    
    # Cleanup
    app.dependency_overrides = {}

@pytest.fixture
def mock_ai_internals():
    """Mock the AI router and streaming components"""
    with patch("lyo_app.api.v1.stream_lyo2.router_agent") as mock_router:
        # Mock ROUTE to return CHAT intent
        mock_router.route = AsyncMock(return_value=RouterResponse(
            decision=RouterDecision(intent=Intent.CHAT, confidence=0.9),
            trace_id="test-trace"
        ))
        
        # Mock AgentRegistry to stream immediately
        with patch("lyo_app.chat.agents.agent_registry.process_stream") as mock_stream:
            async def stream_generator(*args, **kwargs):
                yield "Hello"
                yield " there"
                yield "!"
            mock_stream.side_effect = stream_generator
            
            yield mock_router, mock_stream

# --- TEST CASES ---

@pytest.mark.asyncio
async def test_ios_chat_flow_hi(mock_auth, mock_ai_internals):
    """
    REGRESSION TEST: Verify "Hi" returns a stream of tokens, not a clarification.
    """
    mock_router, mock_stream = mock_ai_internals
    
    payload = {
        "user_id": "test_user_123",
        "text": "Hi",
        "conversation_history": []
    }
    
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream("POST", "/api/v1/lyo2/chat/stream", json=payload) as response:
            assert response.status_code == 200
            
            chunks = []
            async for line in response.aiter_lines():
                if line.strip():
                    chunks.append(line)
            
            # Verify Skeleton
            assert any('type": "skeleton"' in c for c in chunks), "Missing skeleton block"
            
            # Verify Token Streaming (Fast Track)
            assert not any('type": "clarification"' in c for c in chunks), "REGRESSION: Received clarification!"
            
            # Verify Tokens
            token_lines = [c for c in chunks if 'type": "token"' in c]
            assert len(token_lines) > 0, "No tokens received"
            
            print(f"\n✅ PASSED: Received {len(token_lines)} token chunks.")

if __name__ == "__main__":
    async def manual_runner():
        print(">>> [RUNNER] Executing Regression Test: test_ios_chat_flow_hi")
        
        # Manually setup mocks
        with patch("lyo_app.api.v1.stream_lyo2.router_agent.route", new_callable=AsyncMock) as mock_route_method:
            mock_route_method.return_value = RouterResponse(
                decision=RouterDecision(intent=Intent.CHAT, confidence=0.9),
                trace_id="test-trace"
            )
            
            with patch("lyo_app.chat.agents.agent_registry.process_stream") as mock_stream_method:
                async def stream_generator(*args, **kwargs):
                    yield "Hello from Manual Runner"
                    yield "!"
                mock_stream_method.side_effect = stream_generator

                # Mock Auth
                from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
                mock_user = MagicMock()
                mock_user.id = "user_manual"
                app.dependency_overrides[get_current_user_or_guest] = lambda: mock_user
                app.dependency_overrides[get_db] = lambda: AsyncMock()

                try:
                    from httpx import AsyncClient, ASGITransport
                    transport = ASGITransport(app=app)
                    
                    payload = {
                        "user_id": "test_user_123",
                        "text": "Hi",
                        "conversation_history": []
                    }
                    
                    print(">>> Sending POST /api/v1/lyo2/chat/stream ...")
                    async with AsyncClient(transport=transport, base_url="http://test") as ac:
                        async with ac.stream("POST", "/api/v1/lyo2/chat/stream", json=payload) as response:
                            print(f">>> Response Status: {response.status_code}")
                            assert response.status_code == 200
                            
                            chunks = []
                            async for line in response.aiter_lines():
                                if line.strip():
                                    print(f"    {line}")
                                    chunks.append(line)
                            
                            assert any('type": "skeleton"' in c for c in chunks), "Missing skeleton"
                            assert not any('type": "clarification"' in c for c in chunks), "Regression: Got clarification"
                            assert any('Hello from Manual Runner' in c for c in chunks), "Streaming content missing"
                            
                    print("\n✅✅ REGRESSION TEST PASSED: Setup is robust against 'Hi' cold response.")
                    
                except Exception as e:
                    print(f"\n❌ REGRESSION TEST FAILED: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    app.dependency_overrides = {}

    import asyncio
    asyncio.run(manual_runner())
