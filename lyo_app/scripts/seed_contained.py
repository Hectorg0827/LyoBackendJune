import asyncio
import random
from datetime import datetime, timedelta
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Import models to satisfy mapper relationships
from lyo_app.auth.models import User, RefreshToken  # noqa: F401
from lyo_app.auth.rbac import Role, Permission, user_roles, role_permissions  # noqa: F401
from lyo_app.models.enhanced import Task, PushDevice, GamificationProfile  # noqa: F401
from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion  # noqa: F401
from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance, CommunityQuestion, CommunityAnswer  # noqa: F401
from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow  # noqa: F401
from lyo_app.tenants.models import Organization, APIKey  # noqa: F401
from lyo_app.stack.models import StackItem  # noqa: F401
from lyo_app.ai_study.models import StudySession, GeneratedQuiz, QuizAttempt, StudySessionAnalytics  # noqa: F401
from lyo_app.ai_agents.models import UserEngagementState, MentorInteraction  # noqa: F401
from lyo_app.personalization.models import LearnerState, LearnerMastery, AffectSample, SpacedRepetitionSchedule  # noqa: F401
from lyo_app.chat.models import ChatConversation, ChatMessage, ChatNote, ChatCourse, ChatTelemetry  # noqa: F401
from lyo_app.ai_chat.mentor_models import MentorConversation, MentorMessage, MentorAction, MentorSuggestion  # noqa: F401
from lyo_app.classroom.models import ClassroomSession  # noqa: F401

async def seed_data():
    print("Self-contained seeding script starting...")
    db_url = "sqlite+aiosqlite:///./lyo_app_dev.db"
    engine = create_async_engine(db_url)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    print("Engine created. Connecting...")
    async with AsyncSessionLocal() as db:
        print("Connected! Fetching users...")
        result = await db.execute(select(User).limit(5))
        users = result.scalars().all()
        print(f"Found {len(users)} users.")
        
        user_ids = [u.id for u in users]
        if not user_ids:
            print("No users found to associate with. Please create a user first via the app.")
            return

        base_lat, base_lng = 37.7749, -122.4194

        # 3. Create Study Groups
        print("Creating study groups...")
        g1 = StudyGroup(
            name="SwiftUI Masterminds",
            description="Deep dive into advanced SwiftUI animations.",
            creator_id=random.choice(user_ids),
            created_at=datetime.utcnow()
        )
        db.add(g1)
        
        # 4. Create Events
        print("Creating events...")
        start = datetime.utcnow() + timedelta(days=2)
        event = CommunityEvent(
            title="SwiftUI Animations Deep Dive",
            description="Detailed session about animations.",
            event_type=EventType.WORKSHOP,
            status=EventStatus.SCHEDULED,
            location="Innovation Lab Room 1",
            room_id="room-1",
            latitude=base_lat + 0.001,
            longitude=base_lng + 0.001,
            start_time=start,
            end_time=start + timedelta(hours=2),
            organizer_id=random.choice(user_ids),
            created_at=datetime.utcnow()
        )
        db.add(event)

        # 5. Create Marketplace Items
        print("Creating marketplace items...")
        item = MarketplaceItem(
            title="Cracking the Coding Interview",
            description="Used book, great condition.",
            price=25.0,
            currency="USD",
            latitude=base_lat - 0.001,
            longitude=base_lng - 0.001,
            location_name="Campus Center",
            image_urls=["https://picsum.photos/200/300"],
            seller_id=random.choice(user_ids),
            is_active=True,
            is_sold=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(item)

        print("Committing changes...")
        await db.commit()
        print("Seeding completed successfully!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
