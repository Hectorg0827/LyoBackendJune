import asyncio
import sys
import os

# Add the project directory to sys.path
sys.path.append(os.getcwd())

from lyo_app.core.database import async_sessionmaker, create_async_engine
from lyo_app.core.config import settings
from sqlalchemy import select

# Import all models to ensure registry is populated
from lyo_app.auth.models import User
from lyo_app.auth.rbac import Role, Permission, user_roles, role_permissions
from lyo_app.models.enhanced import Task, PushDevice, GamificationProfile
from lyo_app.models.clips import Clip
from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion
from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance
from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow
from lyo_app.tenants.models import Organization, APIKey
from lyo_app.stack.models import StackItem
from lyo_app.ai_study.models import StudySession, GeneratedQuiz, QuizAttempt, StudySessionAnalytics
from lyo_app.ai_agents.models import UserEngagementState, MentorInteraction
from lyo_app.personalization.models import LearnerState, LearnerMastery, AffectSample, SpacedRepetitionSchedule
from lyo_app.chat.models import ChatConversation, ChatMessage, ChatNote, ChatCourse, ChatTelemetry
from lyo_app.ai_chat.mentor_models import MentorConversation, MentorMessage, MentorAction, MentorSuggestion
from lyo_app.classroom.models import ClassroomSession

# Setup DB connection
db_url = settings.database_url
if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(db_url)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def seed_clip():
    async with AsyncSessionLocal() as session:
        # Check for any user
        print("Checking for existing users...")
        result = await session.execute(select(User).limit(1))
        user = result.scalars().first()
        
        if not user:
            print("No users found. Creating a test user...")
            # Create a test user
            user = User(
                email="test_clip@example.com",
                hashed_password="hashed_password_placeholder", # In real app, hash this
                full_name="Clip Tester",
                username="cliptester"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"Created test user: {user.email} (ID: {user.id})")
        else:
            print(f"Using existing user: {user.email} (ID: {user.id})")
            
        user_id = user.id
        
        print(f"Creating test clip for user {user_id}...")
        
        clip = Clip(
            user_id=user_id,
            title="Intro to Calculus Limits",
            description="A quick 3-minute explanation of limits.",
            video_url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
            thumbnail_url="https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/images/BigBuckBunny.jpg",
            duration_seconds=180,
            subject="Mathematics",
            topic="Calculus",
            level="beginner",
            key_points=["Limits", "Approximation", "Infinity"],
            enable_course_generation=True,
            is_public=True
        )
        
        session.add(clip)
        await session.commit()
        print(f"✅ Created clip: {clip.title}")

if __name__ == "__main__":
    asyncio.run(seed_clip())
