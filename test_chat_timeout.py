import asyncio
from unittest.mock import AsyncMock

from lyo_app.api.v1.chat import chat, ChatRequest
from lyo_app.auth.models import User
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    print("Starting test...")
    mock_user = User(id=1, email="test@example.com")
    mock_db = AsyncMock()
    request = ChatRequest(message="Hello")
    try:
        print("Calling chat endpoint...")
        response = await asyncio.wait_for(chat(request, current_user=mock_user, db=mock_db), timeout=10.0)
        print("Success:", response)
    except asyncio.TimeoutError:
        print("Error: Chat endpoint timed out!")
    except Exception as e:
        print("Error:", e)
        import traceback
        traceback.print_exc()
    print("Test finished.")

if __name__ == "__main__":
    asyncio.run(main())
