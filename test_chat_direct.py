"""Direct test of classroom chat endpoint"""
import asyncio
import sys
import logging
from lyo_app.core.database import AsyncSessionLocal
from lyo_app.models.enhanced import User

# Setup logging to see what happens
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_chat():
    """Test the chat endpoint directly"""
    from lyo_app.ai_classroom.routes import classroom_chat, ChatRequest
    from fastapi import BackgroundTasks
    
    # Create a guest user
    guest_user = User(
        id="guest_session", 
        username="Guest Learner", 
        email="guest@lyo.app",
        is_active=True
    )
    
    # Create request
    request = ChatRequest(
        message="Create a complete interactive course on 'Molecular Genetics' suitable for beginner learners.",
        include_audio=False,
        stream=False
    )
    
    # Create DB session
    async with AsyncSessionLocal() as db:
        background_tasks = BackgroundTasks()
        
        try:
            response = await classroom_chat(
                request=request,
                background_tasks=background_tasks,
                current_user=guest_user,
                db=db
            )
            print("✅ SUCCESS!")
            print(f"Response: {response}")
            return response
        except Exception as e:
            logger.exception("❌ ERROR in classroom_chat:")
            print(f"\n❌ Exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == "__main__":
    asyncio.run(test_chat())
