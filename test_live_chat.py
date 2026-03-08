import asyncio
from unittest.mock import AsyncMock, patch

from lyo_app.api.v1.chat import chat, ChatRequest
from lyo_app.auth.models import User

async def main():
    mock_user = User(id=1, email="test@example.com")
    mock_db = AsyncMock()
    request = ChatRequest(message="Hello")
    try:
        response = await chat(request, current_user=mock_user, db=mock_db)
        print("Success:", response)
    except Exception as e:
        print("Error:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
