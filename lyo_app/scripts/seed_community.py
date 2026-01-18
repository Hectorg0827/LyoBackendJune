import asyncio
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from lyo_app.core.database import AsyncSessionLocal, init_db
from lyo_app.auth.models import User
from lyo_app.community.models import (
    StudyGroup, GroupMembership, CommunityEvent, EventType, 
    EventStatus, MarketplaceItem
)
from lyo_app.auth.security import hash_password

async def seed_data():
    print("Starting seeding process...")
    # Import all models to ensure mappers are initialized
    from lyo_app.auth.models import User  # noqa: F401
    from lyo_app.auth.rbac import Role, Permission, user_roles, role_permissions  # noqa: F401
    from lyo_app.models.enhanced import Task, PushDevice, GamificationProfile  # noqa: F401
    from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion  # noqa: F401
    from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance  # noqa: F401
    from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow  # noqa: F401
    from lyo_app.tenants.models import Organization, APIKey  # noqa: F401
    from lyo_app.stack.models import StackItem  # noqa: F401
    from lyo_app.ai_study.models import StudySession, GeneratedQuiz, QuizAttempt, StudySessionAnalytics  # noqa: F401
    
    async with AsyncSessionLocal() as db:
        print("Connected to session. Fetching users...")
        # 1. Ensure users exist
        result = await db.execute(select(User).limit(5))
        users = result.scalars().all()
        print(f"Found {len(users)} users.")
        
        if len(users) < 3:
            print("Creating test users...")
            test_users = [
                User(
                    email=f"user{i}@example.com",
                    username=f"user{i}",
                    hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGGa31S.", # "password123"
                    first_name=f"First{i}",
                    last_name=f"Last{i}",
                    is_active=True,
                    is_verified=True
                )
                for i in range(1, 6)
            ]
            for u in test_users:
                db.add(u)
            await db.commit()
            result = await db.execute(select(User).limit(5))
            users = result.scalars().all()

        user_ids = [u.id for u in users]
        
        # 2. 定位 (Campus coordinates - San Francisco area as placeholder)
        base_lat, base_lng = 37.7749, -122.4194

        # 3. Create Study Groups
        print("Creating study groups...")
        groups = [
            StudyGroup(
                name="SwiftUI Masterminds",
                description="Deep dive into advanced SwiftUI animations and state management.",
                creator_id=random.choice(user_ids),
                created_at=datetime.utcnow()
            ),
            StudyGroup(
                name="Python for Data Science",
                description="Weekly sessions covering Pandas, NumPy, and Scikit-Learn.",
                creator_id=random.choice(user_ids),
                created_at=datetime.utcnow()
            )
        ]
        for g in groups:
            db.add(g)
        await db.commit()
        for g in groups:
            await db.refresh(g)

        # 4. Create Events
        print("Creating events...")
        event_titles = [
            ("SwiftUI Animations Deep Dive", EventType.WORKSHOP),
            ("Career Advice Office Hours", EventType.OFFICE_HOURS),
            ("Networking Mixer", EventType.NETWORKING),
            ("Algorithmic Study Session", EventType.STUDY_SESSION)
        ]
        
        for i, (title, etype) in enumerate(event_titles):
            start = datetime.utcnow() + timedelta(days=random.randint(1, 7), hours=random.randint(1, 23))
            event = CommunityEvent(
                title=title,
                description=f"Detailed session about {title}.",
                event_type=etype,
                status=EventStatus.SCHEDULED,
                location=f"Innovation Lab Room {i+1}",
                room_id=f"room-{i+1}",
                latitude=base_lat + (random.random() - 0.5) * 0.01,
                longitude=base_lng + (random.random() - 0.5) * 0.01,
                start_time=start,
                end_time=start + timedelta(hours=2),
                organizer_id=random.choice(user_ids),
                created_at=datetime.utcnow()
            )
            db.add(event)

        # 5. Create Marketplace Items
        print("Creating marketplace items...")
        marketplace_data = [
            ("Cracking the Coding Interview", 25.0, "Used book, great condition."),
            ("Blue Snowball Microphone", 40.0, "Perfect for recording lessons."),
            ("MacBook Pro Stand", 15.0, "Ergonomic aluminum stand."),
            ("Calculus 101 Textbook", 30.0, "Required for CS freshmen.")
        ]
        
        for title, price, desc in marketplace_data:
            item = MarketplaceItem(
                title=title,
                description=desc,
                price=price,
                currency="USD",
                latitude=base_lat + (random.random() - 0.5) * 0.01,
                longitude=base_lng + (random.random() - 0.5) * 0.01,
                location_name="Campus Center",
                image_urls=["https://picsum.photos/200/300"],
                seller_id=random.choice(user_ids),
                is_active=True,
                is_sold=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(item)

        await db.commit()
        print("Seeding completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
