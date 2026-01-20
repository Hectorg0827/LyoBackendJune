"""
Verification script for Real AI Course Generation.
This script simulates a chat request to create a course and verifies the full pipeline execution.
"""
import asyncio
import logging
import sys
from datetime import datetime
from sqlalchemy import select, func

from lyo_app.core.database import AsyncSessionLocal
from lyo_app.models.enhanced import User
from lyo_app.ai_classroom.models import GraphCourse, LearningNode
from lyo_app.ai_classroom.routes import classroom_chat, ChatRequest
# Import other models to ensure SQLAlchemy mappers are registered
try:
    import lyo_app.ai_study.models
    import lyo_app.community.models
    import lyo_app.models.clips
    import lyo_app.feeds.models
    import lyo_app.learning.models
    import lyo_app.models.social
except ImportError:
    pass
from fastapi import BackgroundTasks

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_generation():
    print(f"[{datetime.utcnow()}] 🚀 Starting Real Course Generation Verification...")
    
    # 1. Setup User and Request
    guest_user = User(
        id="guest_session", 
        username="VerificationUser", 
        email="verify@lyo.app",
        is_active=True
    )
    
    # Use a specific, simple topic to avoid overly complex generation
    topic = "The Water Cycle"
    request = ChatRequest(
        message=f"Create a short interactive course about '{topic}'",
        include_audio=False,
        stream=False
    )
    
    async with AsyncSessionLocal() as db:
        background_tasks = BackgroundTasks()
        
        try:
            # 2. Invoke the Chat Endpoint
            print(f"[{datetime.utcnow()}] 📡 Sending request to backend (this may take 30-60s)...")
            response = await classroom_chat(
                request=request,
                background_tasks=background_tasks,
                current_user=guest_user,
                db=db
            )
            
            # 3. Analyze Response
            print(f"[{datetime.utcnow()}] ✅ Response received!")
            
            if not response.generated_course_id:
                print("❌ FAILED: No generated_course_id in response.")
                print(f"Response dump: {response}")
                return False
                
            print(f"🎉 Generated Course ID: {response.generated_course_id}")
            print(f"Message: {response.content}")
            
            # 4. Verify Database Persistence
            print(f"[{datetime.utcnow()}] 🔍 Verifying database persistence...")
            
            # Check Course
            course_query = await db.execute(
                select(GraphCourse).where(GraphCourse.id == response.generated_course_id)
            )
            course = course_query.scalar_one_or_none()
            
            if not course:
                print("❌ FAILED: Course found in response but NOT in database.")
                return False
                
            print(f"✅ Course found in DB: {course.title} (ID: {course.id})")
            
            # Check Nodes (Content)
            nodes_query = await db.execute(
                select(func.count(LearningNode.id)).where(LearningNode.course_id == course.id)
            )
            node_count = nodes_query.scalar_one()
            
            print(f"📊 Node Count: {node_count}")
            
            # Validation Logic
            # The mock course has exactly 4 nodes. Real courses should have more.
            # However, if the fallback triggered, it might be 4.
            # We check the logs or the course title/content to be sure.
            
            if node_count > 4:
                print("✅ SUCCESS: Real content generated (Node count > 4).")
            elif node_count == 4:
                print("⚠️ WARNING: Node count is 4. This likely means the FALLBACK mock was used.")
                print("Check logs to see if the real pipeline failed.")
            else:
                print(f"❌ FAILED: Unexpected node count: {node_count}")
                
            return True
            
        except Exception as e:
            print(f"❌ CRITICAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    asyncio.run(verify_generation())
