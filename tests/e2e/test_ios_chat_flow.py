import os
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Set Lightweight startup
os.environ["LYO_LIGHTWEIGHT_STARTUP"] = "1"

# Now import app
from lyo_app.app_factory import create_app
from lyo_app.ai.schemas.lyo2 import RouterDecision, Intent, RouterResponse
from lyo_app.teaching_runtime import TeachingAction, TeachingDecision
from lyo_app.core.ai_resilience import StreamingIncompleteError

app = create_app()
client = TestClient(app)

# --- MOCK SETUP HELPERS ---

@pytest.fixture
def mock_auth():
    """Bypass authentication"""
    from lyo_app.auth.dependencies import get_current_user_or_guest, get_db
    
    # Create a dummy user
    mock_user = MagicMock()
    mock_user.id = 123  # authenticated User IDs are database integers

    # Match SQLAlchemy's real AsyncSession contract. Session I/O is async,
    # while add() and the Result scalar accessors are synchronous.
    mock_db = AsyncMock()
    query_result = MagicMock()
    query_result.scalar_one_or_none.return_value = None
    query_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = query_result
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.refresh = AsyncMock()
    
    # Override dependency
    app.dependency_overrides[get_current_user_or_guest] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    
    yield
    
    # Cleanup
    app.dependency_overrides = {}

@pytest.fixture
def mock_ai_internals():
    """Isolate the transport contract from learner-policy/database behavior."""
    decision = TeachingDecision(
        action=TeachingAction.ANSWER,
        reason_code="transport_test",
        model_tier="reflex",
        policy_version="test",
    )

    with patch("lyo_app.api.v1.stream_lyo2.router_agent") as mock_router:
        mock_router.route = AsyncMock(return_value=RouterResponse(
            decision=RouterDecision(intent=Intent.CHAT, confidence=0.9),
            trace_id="test-trace"
        ))

        with patch(
            "lyo_app.teaching_runtime.decide_for_chat",
            new=AsyncMock(return_value=decision),
        ), patch(
            "lyo_app.teaching_runtime.record_policy_decision",
            new=AsyncMock(return_value=None),
        ), patch(
            "lyo_app.api.v1.stream_lyo2.LyoExecutor.stream_text"
        ) as mock_stream:
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
            
            # This payload intentionally does NOT advertise text_delta support:
            # legacy iOS builds must still receive the final answer envelope.
            delta_lines = [c for c in chunks if 'type": "text_delta"' in c]
            answer_lines = [c for c in chunks if 'type": "answer"' in c]
            assert len(delta_lines) == 0, "Legacy client unexpectedly received text deltas"
            assert len(answer_lines) > 0, f"Legacy client did not receive final answer content: {chunks}"

            print(f"\n✅ PASSED: Legacy client received {len(answer_lines)} final answer event(s).")


@pytest.mark.asyncio
async def test_ios_chat_flow_text_delta_capability(mock_auth, mock_ai_internals):
    """Updated clients get incremental deltas plus one final compatibility snapshot."""
    payload = {
        "user_id": "test_user_123",
        "text": "Hi",
        "conversation_history": [],
        "state_summary": {
            "stream_capabilities": {"text_delta": True},
        },
    }

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream("POST", "/api/v1/lyo2/chat/stream", json=payload) as response:
            assert response.status_code == 200
            chunks = [
                line
                async for line in response.aiter_lines()
                if line.strip()
            ]

    delta_lines = [line for line in chunks if 'type": "text_delta"' in line]
    answer_lines = [line for line in chunks if 'type": "answer"' in line]
    assert len(delta_lines) == 3, f"Expected three text deltas, got: {chunks}"
    assert len(answer_lines) == 1
    assert any('"final_snapshot": true' in line for line in answer_lines)
    assert any('"generation_status": "completed"' in line for line in answer_lines)
    assert any('"message_id":' in line for line in answer_lines)


@pytest.mark.asyncio
async def test_fast_chat_preserves_partial_answer_on_provider_failure(
    mock_auth,
    mock_ai_internals,
):
    """A provider drop after visible text returns one persisted incomplete snapshot."""
    _, mock_stream = mock_ai_internals

    async def interrupted_stream(*args, **kwargs):
        yield "Partial "
        yield "answer"
        raise StreamingIncompleteError("Partial answer", "gemini-2.5-flash")

    mock_stream.side_effect = interrupted_stream
    payload = {
        "user_id": "test_user_123",
        "text": "Hi",
        "conversation_history": [],
        "state_summary": {
            "stream_capabilities": {"text_delta": True},
        },
    }

    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with ac.stream(
            "POST",
            "/api/v1/lyo2/chat/stream",
            json=payload,
        ) as response:
            assert response.status_code == 200
            chunks = [
                line
                async for line in response.aiter_lines()
                if line.strip()
            ]

    delta_lines = [line for line in chunks if 'type": "text_delta"' in line]
    answer_lines = [line for line in chunks if 'type": "answer"' in line]
    assert len(delta_lines) == 2, chunks
    assert len(answer_lines) == 1, chunks
    assert '"generation_status": "incomplete"' in answer_lines[0]
    assert '"message_id":' in answer_lines[0]
    assert "Partial answer" in answer_lines[0]
    assert not any(
        'type": "error"' in line
        for line in chunks
    ), chunks

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
