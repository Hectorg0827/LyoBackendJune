import asyncio
import json
import logging
import uuid
from lyo_app.ai.schemas.lyo2 import RouterRequest, ConversationTurn
from lyo_app.ai.schemas.lyo2 import RouterRequest, ConversationTurn
from lyo_app.api.v1.stream_lyo2 import stream_lyo2_chat
from lyo_app.auth.schemas import UserRead
from fastapi import Request
# Import the main FastAPI app to enforce full module loading and SQLAlchemy model resolution
import lyo_app.main
from sqlalchemy.orm import configure_mappers
configure_mappers()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock the FastAPI Request object
class MockRequest(Request):
    def __init__(self):
        pass

async def read_stream_response(response):
    """Consume the SSE stream response from the endpoint."""
    async for chunk in response.body_iterator:
        text_chunk = chunk
        if isinstance(chunk, bytes):
            text_chunk = chunk.decode("utf-8")
        if text_chunk.startswith("data: "):
            payload_str = text_chunk[len("data: "):].strip()
            if payload_str == "[DONE]":
                print("🏁 Stream Complete (DONE)")
            else:
                try:
                    payload = json.loads(payload_str)
                    print(f"📦 EVENT TYPE: {payload.get('type')}")
                    if payload.get('type') == 'a2ui':
                        print(f"🎨 A2UI BRICK: {json.dumps(payload['block'], indent=2)}")
                    elif payload.get('type') == 'open_classroom':
                        print(f"🏫 CLASSROOM PAYLOAD: {json.dumps(payload['block'], indent=2)}")
                except json.JSONDecodeError:
                    print(f"❌ Failed to decode: {payload_str}")

from datetime import datetime, timezone

async def run_e2e_test(prompt_text: str, test_name: str):
    print(f"\n{'='*50}\n🚀 STARTING E2E TEST: {test_name}\n{'='*50}")
    
    # 1. Create a mock user
    mock_user = UserRead(
        id=b"11111111-1111-1111-1111-111111111111",
        email="test@user.com",
        username="test_user",
        created_at=datetime.now(timezone.utc),
        is_active=True,
        is_superuser=False,
        is_verified=True
    )
    
    # 2. Build the router request corresponding to the user query
    request = RouterRequest(
        user_id="11111111-1111-1111-1111-111111111111",
        text=prompt_text,
        conversation_history=[],
        client_capabilities=["a2ui_v1"]
    )
    
    # 3. Call the actual endpoint implementation
    print(f"Sending prompt: '{prompt_text}' to stream_lyo2_chat()...")
    
    response = await stream_lyo2_chat(
        request=request,
        fastapi_request=MockRequest(),
        current_user=mock_user,
        db=None # Bypassing db auth/save steps for simple unit execution
    )
    
    # 4. Read the resulting stream generator
    await read_stream_response(response)
    print(f"\n✅ {test_name} COMPLETED.\n")

async def main():
    print("Initiating E2E Tests for Lyo-Nexus A2UI v0.9 Flows...")
    
    # Test 1: Generate a Course
    await run_e2e_test(
        prompt_text="Create a course on the history of the Apollo 11 moon landing.",
        test_name="📚 CREATE COURSE FLOW"
    )
    
    # Test 2: In-Chat Quiz Generation
    await run_e2e_test(
        prompt_text="Quiz me on basic python programming concepts.",
        test_name="❓ IN-CHAT QUIZ FLOW"
    )

if __name__ == "__main__":
    asyncio.run(main())
