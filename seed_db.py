#!/usr/bin/env python3
"""
🌱 LyoBackend Database Seeding Script
Creates realistic fake users and test data for comprehensive app development and testing.

This script populates the database with:
- Diverse fake users with realistic profiles
- Learning content and enrollments 
- Community interactions (posts, comments, reactions)
- Gamification data (XP, achievements, streaks)
- Study sessions and AI interactions
- Social features (follows, study groups)

Usage:
    python3 seed_db.py --users 50 --clear-existing
    python3 seed_db.py --preset demo  # Creates demo users
    python3 seed_db.py --help
"""

import asyncio
import argparse
import random
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import uuid

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from faker import Faker
from faker.providers import internet, lorem, profile, date_time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('seed_db.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize Faker with multiple locales for diversity
fake = Faker(['en_US', 'es_ES', 'fr_FR', 'de_DE', 'it_IT', 'pt_BR', 'ja_JP', 'ko_KR', 'zh_CN'])
fake.add_provider(internet)
fake.add_provider(lorem)
fake.add_provider(profile)
fake.add_provider(date_time)


class DatabaseSeeder:
    """Comprehensive database seeding system."""
    
    def __init__(self):
        self.db_session = None
        self.created_users = []
        self.created_courses = []
        self.created_posts = []
        self.created_study_groups = []
        
    async def initialize(self):
        """Initialize database connection and services."""
        try:
            from lyo_app.core.database import AsyncSessionLocal, init_db
            from lyo_app.auth.service import AuthService
            from lyo_app.auth.rbac_service import RBACService
            
            # Initialize database tables
            logger.info("🏗️  Initializing database tables...")
            await init_db()
            
            # Create database session
            self.db_session = AsyncSessionLocal()
            
            # Initialize services
            self.auth_service = AuthService()
            self.rbac_service = RBACService(self.db_session)
            
            # Initialize RBAC system
            await self.rbac_service.initialize_default_roles_and_permissions()
            
            logger.info("✅ Database connection and services initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            return False
    
    async def clear_existing_data(self):
        """Clear existing test data (keeps structure)."""
        try:
            logger.info("🗑️  Clearing existing test data...")
            
            # Import models for deletion
            from lyo_app.auth.models import User
            from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion
            from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow
            from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent
            from lyo_app.gamification.models import UserXP, UserAchievement, Streak, UserLevel
            from lyo_app.ai_study.models import StudySession, StudyMessage
            from sqlalchemy import delete, select
            
            # Delete in proper order (respecting foreign key constraints)
            deletion_order = [
                # Gamification data
                UserXP, UserAchievement, Streak, UserLevel,
                # AI Study data
                StudyMessage, StudySession,
                # Social interactions
                PostReaction, CommentReaction, Comment, Post, UserFollow,
                # Community data  
                GroupMembership, CommunityEvent, StudyGroup,
                # Learning data
                LessonCompletion, CourseEnrollment, Lesson, Course,
                # Users (but keep admin users)
            ]
            
            for model in deletion_order:
                if model == User:
                    # Keep admin and system users
                    await self.db_session.execute(
                        delete(User).where(User.email.not_like('%admin%'))
                    )
                else:
                    await self.db_session.execute(delete(model))
                await self.db_session.commit()
            
            logger.info("✅ Existing test data cleared")
            
        except Exception as e:
            logger.error(f"❌ Failed to clear existing data: {e}")
            await self.db_session.rollback()
            raise
    
    async def create_fake_users(self, count: int = 50) -> List[Dict]:
        """Create diverse fake users with realistic profiles."""
        logger.info(f"👥 Creating {count} fake users...")
        
        users = []
        
        # Predefined realistic user archetypes
        archetypes = [
            {"role": "student", "age_range": (18, 25), "interests": ["technology", "science", "art"]},
            {"role": "professional", "age_range": (25, 45), "interests": ["business", "leadership", "productivity"]},
            {"role": "researcher", "age_range": (28, 60), "interests": ["science", "data", "research"]},
            {"role": "teacher", "age_range": (25, 55), "interests": ["education", "psychology", "child_development"]},
            {"role": "entrepreneur", "age_range": (22, 40), "interests": ["startup", "innovation", "networking"]},
            {"role": "retiree", "age_range": (60, 80), "interests": ["history", "gardening", "travel"]},
            {"role": "artist", "age_range": (20, 50), "interests": ["art", "music", "creativity"]},
            {"role": "developer", "age_range": (22, 45), "interests": ["coding", "technology", "open_source"]},
        ]
        
        from lyo_app.auth.schemas import UserCreate
        from lyo_app.auth.rbac import RoleType
        
        for i in range(count):
            try:
                # Choose random archetype
                archetype = random.choice(archetypes)
                
                # Generate profile based on archetype
                profile = fake.simple_profile()
                birth_year = random.randint(
                    datetime.now().year - archetype["age_range"][1],
                    datetime.now().year - archetype["age_range"][0]
                )
                
                # Create unique email and username
                base_username = fake.user_name()
                username = f"{base_username}_{i}"
                email = f"{username}@{fake.free_email_domain()}"
                
                # Generate realistic names
                first_name = fake.first_name()
                last_name = fake.last_name()
                
                # Create user data
                user_data = UserCreate(
                    email=email,
                    username=username,
                    password="TestPass123!",  # Standard test password
                    confirm_password="TestPass123!",
                    first_name=first_name,
                    last_name=last_name
                )
                
                # Register user
                user = await self.auth_service.register_user(self.db_session, user_data)
                
                # Assign appropriate role based on archetype
                if archetype["role"] in ["teacher", "researcher"]:
                    await self.rbac_service.assign_role_to_user(user.id, RoleType.INSTRUCTOR.value)
                elif random.random() < 0.1:  # 10% chance to be instructor
                    await self.rbac_service.assign_role_to_user(user.id, RoleType.INSTRUCTOR.value)
                # else: remains as default student role
                
                # Update user profile with additional info
                user.bio = fake.text(max_nb_chars=200)
                user.avatar_url = f"https://picsum.photos/200/200?random={i}"
                user.last_login = fake.date_time_between(start_date='-30d', end_date='now')
                
                # Store user info with archetype for later use
                user_info = {
                    "user": user,
                    "archetype": archetype,
                    "email": email,
                    "username": username,
                    "password": "TestPass123!",
                    "interests": archetype["interests"]
                }
                
                users.append(user_info)
                self.created_users.append(user_info)
                
                if i % 10 == 0:  # Log progress every 10 users
                    logger.info(f"   Created {i}/{count} users...")
                    
            except Exception as e:
                logger.warning(f"Failed to create user {i}: {e}")
                continue
        
        await self.db_session.commit()
        logger.info(f"✅ Created {len(users)} fake users")
        return users
    
    async def create_demo_users(self) -> List[Dict]:
        """Create specific demo users for presentation/testing."""
        logger.info("🎭 Creating demo users...")
        
        from lyo_app.auth.schemas import UserCreate
        from lyo_app.auth.rbac import RoleType
        
        demo_users_data = [
            {
                "email": "john.doe@demo.com",
                "username": "johndoe",
                "first_name": "John",
                "last_name": "Doe",
                "role": RoleType.STUDENT,
                "bio": "Computer Science student passionate about AI and machine learning.",
                "archetype": {"role": "student", "interests": ["technology", "AI", "programming"]}
            },
            {
                "email": "jane.smith@demo.com", 
                "username": "janesmith",
                "first_name": "Jane",
                "last_name": "Smith",
                "role": RoleType.INSTRUCTOR,
                "bio": "Professor of Data Science with 10+ years of experience in educational technology.",
                "archetype": {"role": "teacher", "interests": ["data_science", "education", "research"]}
            },
            {
                "email": "alex.chen@demo.com",
                "username": "alexchen",
                "first_name": "Alex",
                "last_name": "Chen",
                "role": RoleType.STUDENT,
                "bio": "Entrepreneur building the next generation of learning apps.",
                "archetype": {"role": "entrepreneur", "interests": ["startup", "mobile_apps", "UX_design"]}
            },
            {
                "email": "maria.gonzalez@demo.com",
                "username": "mariagonzalez", 
                "first_name": "Maria",
                "last_name": "Gonzalez",
                "role": RoleType.INSTRUCTOR,
                "bio": "Language learning expert specializing in immersive educational experiences.",
                "archetype": {"role": "teacher", "interests": ["languages", "cultural_exchange", "immersion"]}
            },
            {
                "email": "david.kim@demo.com",
                "username": "davidkim",
                "first_name": "David", 
                "last_name": "Kim",
                "role": RoleType.STUDENT,
                "bio": "Medical student using AI to accelerate learning and knowledge retention.",
                "archetype": {"role": "student", "interests": ["medicine", "AI_study", "efficiency"]}
            }
        ]
        
        demo_users = []
        
        for user_data in demo_users_data:
            try:
                # Create user registration data
                user_create = UserCreate(
                    email=user_data["email"],
                    username=user_data["username"], 
                    password="DemoPass123!",
                    confirm_password="DemoPass123!",
                    first_name=user_data["first_name"],
                    last_name=user_data["last_name"]
                )
                
                # Register user
                user = await self.auth_service.register_user(self.db_session, user_create)
                
                # Assign role
                if user_data["role"] != RoleType.STUDENT:
                    await self.rbac_service.assign_role_to_user(user.id, user_data["role"].value)
                
                # Update profile
                user.bio = user_data["bio"]
                user.avatar_url = f"https://ui-avatars.com/api/?name={user_data['first_name']}+{user_data['last_name']}&background=random&color=fff"
                user.last_login = fake.date_time_between(start_date='-7d', end_date='now')
                user.is_verified = True
                
                # Store user info
                user_info = {
                    "user": user,
                    "archetype": user_data["archetype"],
                    "email": user_data["email"],
                    "username": user_data["username"],
                    "password": "DemoPass123!",
                    "interests": user_data["archetype"]["interests"],
                    "is_demo": True
                }
                
                demo_users.append(user_info)
                self.created_users.append(user_info)
                
                logger.info(f"   Created demo user: {user.username} ({user_data['role'].value})")
                
            except Exception as e:
                logger.warning(f"Failed to create demo user {user_data['username']}: {e}")
                continue
        
        await self.db_session.commit()
        logger.info(f"✅ Created {len(demo_users)} demo users")
        return demo_users
    
    async def create_learning_content(self, user_count: int):
        """Create courses, lessons, and enrollments."""
        logger.info("📚 Creating learning content...")
        
        from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion
        
        # Course topics and structures
        course_templates = [
            {
                "title": "Introduction to Machine Learning",
                "description": "Learn the fundamentals of ML algorithms and applications",
                "category": "technology",
                "difficulty": "beginner",
                "lessons": [
                    "What is Machine Learning?",
                    "Types of ML Algorithms", 
                    "Supervised Learning Basics",
                    "Unsupervised Learning",
                    "Deep Learning Introduction",
                    "Hands-on Project: Building Your First Model"
                ]
            },
            {
                "title": "Data Science with Python",
                "description": "Master data analysis and visualization using Python",
                "category": "technology", 
                "difficulty": "intermediate",
                "lessons": [
                    "Python for Data Science",
                    "NumPy and Pandas Essentials",
                    "Data Cleaning Techniques",
                    "Statistical Analysis",
                    "Data Visualization with Matplotlib",
                    "Real-world Data Project"
                ]
            },
            {
                "title": "Digital Marketing Fundamentals", 
                "description": "Learn modern digital marketing strategies and tools",
                "category": "business",
                "difficulty": "beginner",
                "lessons": [
                    "Digital Marketing Landscape",
                    "Content Marketing Strategy",
                    "Social Media Marketing",
                    "SEO Basics",
                    "Email Marketing",
                    "Analytics and Measurement"
                ]
            },
            {
                "title": "UX/UI Design Principles",
                "description": "Create user-centered designs that drive engagement",
                "category": "design",
                "difficulty": "intermediate", 
                "lessons": [
                    "Design Thinking Process",
                    "User Research Methods",
                    "Wireframing and Prototyping",
                    "Visual Design Principles",
                    "Usability Testing",
                    "Portfolio Development"
                ]
            },
            {
                "title": "Spanish for Beginners",
                "description": "Start your Spanish learning journey with interactive lessons",
                "category": "language",
                "difficulty": "beginner",
                "lessons": [
                    "Basic Greetings and Introductions",
                    "Numbers and Time",
                    "Family and Relationships", 
                    "Food and Dining",
                    "Travel and Transportation",
                    "Conversational Practice"
                ]
            }
        ]
        
        # Create courses
        for template in course_templates:
            try:
                # Select a random instructor
                instructors = [u for u in self.created_users 
                             if u["archetype"]["role"] in ["teacher", "researcher"] 
                             or random.random() < 0.3]
                if not instructors:
                    instructors = self.created_users[:5]  # Fallback to first 5 users
                    
                instructor = random.choice(instructors)
                
                course = Course(
                    title=template["title"],
                    description=template["description"],
                    instructor_id=instructor["user"].id,
                    category=template["category"],
                    difficulty_level=template["difficulty"],
                    estimated_duration_hours=len(template["lessons"]) * 2,
                    is_published=True,
                    created_at=fake.date_time_between(start_date='-90d', end_date='-30d')
                )
                
                self.db_session.add(course)
                await self.db_session.flush()  # Get the course ID
                
                # Create lessons for this course
                for i, lesson_title in enumerate(template["lessons"]):
                    lesson = Lesson(
                        title=lesson_title,
                        content=fake.text(max_nb_chars=500),
                        course_id=course.id,
                        order_index=i + 1,
                        duration_minutes=random.randint(15, 45),
                        is_published=True
                    )
                    self.db_session.add(lesson)
                
                self.created_courses.append({
                    "course": course,
                    "template": template,
                    "instructor": instructor
                })
                
                logger.info(f"   Created course: {course.title}")
                
            except Exception as e:
                logger.warning(f"Failed to create course {template['title']}: {e}")
                continue
        
        await self.db_session.commit()
        
        # Create enrollments
        await self._create_enrollments()
        
        logger.info(f"✅ Created {len(self.created_courses)} courses with lessons and enrollments")
    
    async def _create_enrollments(self):
        """Create course enrollments and lesson completions."""
        from lyo_app.learning.models import CourseEnrollment, LessonCompletion
        from sqlalchemy import select
        
        for user_info in self.created_users:
            user = user_info["user"]
            user_interests = user_info["interests"]
            
            # Enroll user in courses matching their interests
            for course_info in self.created_courses:
                course = course_info["course"]
                course_category = course_info["template"]["category"]
                
                # Calculate enrollment probability based on interests
                enroll_probability = 0.1  # Base probability
                if any(interest in course_category or course_category in interest 
                      for interest in user_interests):
                    enroll_probability = 0.7
                elif random.random() < 0.3:  # Some random enrollments
                    enroll_probability = 0.4
                
                if random.random() < enroll_probability:
                    try:
                        enrollment = CourseEnrollment(
                            user_id=user.id,
                            course_id=course.id,
                            enrolled_at=fake.date_time_between(start_date='-60d', end_date='now'),
                            progress_percentage=random.randint(0, 100)
                        )
                        self.db_session.add(enrollment)
                        
                        # Create lesson completions for this enrollment
                        await self._create_lesson_completions(enrollment, course)
                        
                    except Exception as e:
                        logger.debug(f"Enrollment creation failed: {e}")
                        continue
        
        await self.db_session.commit()
    
    async def _create_lesson_completions(self, enrollment, course):
        """Create lesson completions based on course progress."""
        from lyo_app.learning.models import LessonCompletion, Lesson
        from sqlalchemy import select
        
        # Get lessons for this course
        result = await self.db_session.execute(
            select(Lesson).where(Lesson.course_id == course.id).order_by(Lesson.order_index)
        )
        lessons = result.scalars().all()
        
        # Complete lessons based on progress percentage
        lessons_to_complete = int((enrollment.progress_percentage / 100) * len(lessons))
        
        for i in range(lessons_to_complete):
            lesson = lessons[i]
            completion = LessonCompletion(
                user_id=enrollment.user_id,
                lesson_id=lesson.id,
                course_id=course.id,
                completed_at=fake.date_time_between(
                    start_date=enrollment.enrolled_at,
                    end_date='now'
                ),
                time_spent_minutes=random.randint(lesson.duration_minutes, lesson.duration_minutes * 2)
            )
            self.db_session.add(completion)
    
    async def create_social_content(self):
        """Create posts, comments, and social interactions."""
        logger.info("💬 Creating social content...")
        
        from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow
        
        # Create posts
        post_templates = [
            "Just finished my first machine learning project! 🤖 #MachineLearning #AI",
            "Anyone else struggling with data visualization in Python? Any good resources?",
            "Loving this new course on digital marketing! The instructor is amazing 👏",
            "Study group forming for UX Design course - who's interested? DM me!",
            "Finally understood recursion today! Sometimes you just need the right explanation 💡",
            "What's everyone's favorite productivity technique for studying?",
            "Just completed my 30-day learning streak! 🔥 #motivation #learning",
            "This Spanish course is making me want to book a trip to Barcelona! ✈️",
            "Coffee + coding + Sunday morning = perfect combination ☕️💻",
            "Struggling with imposter syndrome in tech... anyone else feel this way?",
            "Best resources for learning data science? Looking for recommendations!",
            "Just published my first blog post about my learning journey! Link in bio 📝",
            "Study buddy needed for weekend learning sessions! Anyone in NYC area?",
            "Mind = blown 🤯 This AI course is incredible! Thanks @instructor for the clear explanations",
            "Friday motivation: You don't have to be great to get started, but you have to get started to be great! 💪"
        ]
        
        # Create posts
        for user_info in random.sample(self.created_users, min(30, len(self.created_users))):
            try:
                num_posts = random.randint(0, 5)  # Some users are more active
                
                for _ in range(num_posts):
                    post_content = random.choice(post_templates)
                    
                    post = Post(
                        content=post_content,
                        author_id=user_info["user"].id,
                        created_at=fake.date_time_between(start_date='-30d', end_date='now'),
                        likes_count=random.randint(0, 50),
                        comments_count=random.randint(0, 10),
                        is_published=True
                    )
                    
                    self.db_session.add(post)
                    await self.db_session.flush()
                    
                    self.created_posts.append({
                        "post": post,
                        "author": user_info
                    })
                    
            except Exception as e:
                logger.debug(f"Post creation failed: {e}")
                continue
        
        await self.db_session.commit()
        
        # Create comments and reactions
        await self._create_comments_and_reactions()
        
        # Create user follows
        await self._create_user_follows()
        
        logger.info(f"✅ Created {len(self.created_posts)} posts with comments and reactions")
    
    async def _create_comments_and_reactions(self):
        """Create comments and reactions on posts."""
        from lyo_app.feeds.models import Comment, PostReaction, CommentReaction
        
        comment_templates = [
            "Great point! Thanks for sharing this.",
            "I had the same experience! Very relatable.",
            "This is exactly what I needed to hear today 🙌",
            "Could you share more details about this?",
            "Totally agree with you on this one.",
            "Thanks for the motivation! 💪",
            "This is so helpful, bookmarking for later!",
            "Love your perspective on this topic.",
            "Same here! We should connect and discuss more.",
            "Inspiring as always! Keep up the great work 🌟"
        ]
        
        for post_info in self.created_posts:
            post = post_info["post"]
            
            # Create comments
            num_comments = min(post.comments_count, random.randint(0, 8))
            for _ in range(num_comments):
                commenter = random.choice(self.created_users)
                if commenter["user"].id != post.author_id:  # Don't comment on own posts
                    comment = Comment(
                        content=random.choice(comment_templates),
                        post_id=post.id,
                        author_id=commenter["user"].id,
                        created_at=fake.date_time_between(
                            start_date=post.created_at,
                            end_date='now'
                        ),
                        likes_count=random.randint(0, 15)
                    )
                    self.db_session.add(comment)
            
            # Create post reactions
            num_reactions = min(post.likes_count, random.randint(0, 20))
            reactors = random.sample(self.created_users, min(num_reactions, len(self.created_users)))
            
            for reactor in reactors:
                if reactor["user"].id != post.author_id:  # Don't like own posts
                    reaction = PostReaction(
                        post_id=post.id,
                        user_id=reactor["user"].id,
                        reaction_type="like",
                        created_at=fake.date_time_between(
                            start_date=post.created_at,
                            end_date='now'
                        )
                    )
                    self.db_session.add(reaction)
        
        await self.db_session.commit()
    
    async def _create_user_follows(self):
        """Create follow relationships between users."""
        from lyo_app.feeds.models import UserFollow
        
        # Create realistic follow relationships
        for user_info in self.created_users:
            user = user_info["user"]
            
            # Users follow others with similar interests or instructors
            potential_follows = []
            
            # Follow instructors
            for other_user in self.created_users:
                if (other_user["user"].id != user.id and 
                    other_user["archetype"]["role"] in ["teacher", "researcher"]):
                    potential_follows.append(other_user)
            
            # Follow users with similar interests
            user_interests = set(user_info["interests"])
            for other_user in self.created_users:
                if other_user["user"].id != user.id:
                    other_interests = set(other_user["interests"])
                    if user_interests.intersection(other_interests):
                        potential_follows.append(other_user)
            
            # Randomly select some to follow
            num_follows = random.randint(2, min(15, len(potential_follows)))
            follows = random.sample(potential_follows, min(num_follows, len(potential_follows)))
            
            for follow_target in follows:
                try:
                    follow = UserFollow(
                        follower_id=user.id,
                        followed_id=follow_target["user"].id,
                        created_at=fake.date_time_between(start_date='-60d', end_date='now')
                    )
                    self.db_session.add(follow)
                except Exception:
                    continue  # Skip duplicates
        
        await self.db_session.commit()
    
    async def create_gamification_data(self):
        """Create XP, achievements, streaks, and other gamification elements."""
        logger.info("🎮 Creating gamification data...")
        
        from lyo_app.gamification.models import (
            UserXP, Achievement, UserAchievement, Streak, UserLevel, 
            XPActionType, AchievementType, AchievementRarity, StreakType
        )
        
        # Create default achievements
        await self._create_default_achievements()
        
        # Create user gamification data
        for user_info in self.created_users:
            user = user_info["user"]
            
            # Create XP records
            total_xp = 0
            xp_actions = [
                (XPActionType.DAILY_LOGIN, random.randint(5, 30), "login"),
                (XPActionType.LESSON_COMPLETED, random.randint(10, 25), "lesson"),
                (XPActionType.POST_CREATED, random.randint(3, 15), "social"),
                (XPActionType.COMMENT_CREATED, random.randint(1, 8), "social"),
                (XPActionType.COURSE_COMPLETED, random.randint(1, 3), "course"),
            ]
            
            for action_type, frequency, context in xp_actions:
                for _ in range(frequency):
                    xp_amount = self._get_xp_amount_for_action(action_type)
                    total_xp += xp_amount
                    
                    xp_record = UserXP(
                        user_id=user.id,
                        action_type=action_type,
                        xp_earned=xp_amount,
                        context_type=context,
                        earned_at=fake.date_time_between(start_date='-60d', end_date='now')
                    )
                    self.db_session.add(xp_record)
            
            # Create user level
            level = self._calculate_level_from_xp(total_xp)
            user_level = UserLevel(
                user_id=user.id,
                current_level=level,
                total_xp=total_xp,
                xp_to_next_level=self._calculate_xp_to_next_level(total_xp)
            )
            self.db_session.add(user_level)
            
            # Create streaks
            for streak_type in StreakType:
                if random.random() < 0.7:  # 70% chance to have this streak type
                    current_streak = random.randint(0, 30)
                    longest_streak = max(current_streak, random.randint(current_streak, 50))
                    
                    streak = Streak(
                        user_id=user.id,
                        streak_type=streak_type,
                        current_count=current_streak,
                        longest_count=longest_streak,
                        last_activity_date=fake.date_time_between(start_date='-7d', end_date='now'),
                        is_active=current_streak > 0
                    )
                    self.db_session.add(streak)
        
        await self.db_session.commit()
        
        # Create user achievements
        await self._create_user_achievements()
        
        logger.info("✅ Created gamification data (XP, levels, streaks, achievements)")
    
    async def _create_default_achievements(self):
        """Create default achievements."""
        from lyo_app.gamification.models import Achievement, AchievementType, AchievementRarity
        
        achievements_data = [
            {
                "name": "First Steps",
                "description": "Complete your first lesson",
                "type": AchievementType.LEARNING,
                "rarity": AchievementRarity.COMMON,
                "xp_reward": 50,
                "criteria": {"lessons_completed": 1}
            },
            {
                "name": "Learning Enthusiast", 
                "description": "Complete 10 lessons",
                "type": AchievementType.LEARNING,
                "rarity": AchievementRarity.UNCOMMON,
                "xp_reward": 200,
                "criteria": {"lessons_completed": 10}
            },
            {
                "name": "Course Master",
                "description": "Complete your first course",
                "type": AchievementType.LEARNING,
                "rarity": AchievementRarity.RARE,
                "xp_reward": 500,
                "criteria": {"courses_completed": 1}
            },
            {
                "name": "Social Butterfly",
                "description": "Make your first post",
                "type": AchievementType.SOCIAL,
                "rarity": AchievementRarity.COMMON,
                "xp_reward": 25,
                "criteria": {"posts_created": 1}
            },
            {
                "name": "Conversation Starter",
                "description": "Write 25 comments",
                "type": AchievementType.SOCIAL,
                "rarity": AchievementRarity.UNCOMMON, 
                "xp_reward": 150,
                "criteria": {"comments_created": 25}
            },
            {
                "name": "Week Warrior",
                "description": "Maintain a 7-day learning streak",
                "type": AchievementType.STREAK,
                "rarity": AchievementRarity.UNCOMMON,
                "xp_reward": 300,
                "criteria": {"learning_streak_days": 7}
            },
            {
                "name": "Month Master",
                "description": "Maintain a 30-day learning streak",
                "type": AchievementType.STREAK,
                "rarity": AchievementRarity.EPIC,
                "xp_reward": 1000,
                "criteria": {"learning_streak_days": 30}
            },
            {
                "name": "Level Up",
                "description": "Reach level 5",
                "type": AchievementType.MILESTONE,
                "rarity": AchievementRarity.RARE,
                "xp_reward": 250,
                "criteria": {"level_reached": 5}
            }
        ]
        
        for achievement_data in achievements_data:
            achievement = Achievement(
                name=achievement_data["name"],
                description=achievement_data["description"],
                type=achievement_data["type"],
                rarity=achievement_data["rarity"],
                xp_reward=achievement_data["xp_reward"],
                criteria=achievement_data["criteria"],
                icon_url=f"https://api.dicebear.com/7.x/shapes/svg?seed={achievement_data['name']}"
            )
            self.db_session.add(achievement)
        
        await self.db_session.commit()
    
    async def _create_user_achievements(self):
        """Award achievements to users based on their activity."""
        from lyo_app.gamification.models import Achievement, UserAchievement
        from sqlalchemy import select
        
        # Get all achievements
        result = await self.db_session.execute(select(Achievement))
        achievements = result.scalars().all()
        
        for user_info in self.created_users:
            user = user_info["user"]
            
            # Award achievements based on user activity
            for achievement in achievements:
                should_award = False
                
                # Simple criteria checking (in real app, this would be more sophisticated)
                if "lessons_completed" in achievement.criteria:
                    # Simulate lesson completion check
                    if random.random() < 0.6:  # 60% chance
                        should_award = True
                elif "posts_created" in achievement.criteria:
                    if random.random() < 0.4:  # 40% chance
                        should_award = True
                elif "level_reached" in achievement.criteria:
                    if random.random() < 0.3:  # 30% chance
                        should_award = True
                elif "learning_streak_days" in achievement.criteria:
                    days_required = achievement.criteria["learning_streak_days"]
                    if days_required <= 7:
                        if random.random() < 0.5:  # 50% chance for week streak
                            should_award = True
                    elif days_required <= 30:
                        if random.random() < 0.2:  # 20% chance for month streak
                            should_award = True
                
                if should_award:
                    user_achievement = UserAchievement(
                        user_id=user.id,
                        achievement_id=achievement.id,
                        is_completed=True,
                        completed_at=fake.date_time_between(start_date='-30d', end_date='now')
                    )
                    self.db_session.add(user_achievement)
        
        await self.db_session.commit()
    
    def _get_xp_amount_for_action(self, action_type: 'XPActionType') -> int:
        """Get XP amount for a specific action."""
        xp_amounts = {
            'XPActionType.LESSON_COMPLETED': random.randint(10, 25),
            'XPActionType.COURSE_COMPLETED': random.randint(100, 200),
            'XPActionType.POST_CREATED': random.randint(5, 15),
            'XPActionType.COMMENT_CREATED': random.randint(2, 8),
            'XPActionType.DAILY_LOGIN': random.randint(5, 10),
            'XPActionType.STREAK_MILESTONE': random.randint(20, 50),
        }
        return xp_amounts.get(str(action_type), 10)
    
    def _calculate_level_from_xp(self, total_xp: int) -> int:
        """Calculate user level from total XP."""
        # Simple exponential level progression
        level = 1
        xp_needed = 100
        current_xp = total_xp
        
        while current_xp >= xp_needed:
            current_xp -= xp_needed
            level += 1
            xp_needed = int(xp_needed * 1.5)  # Exponential growth
            
        return level
    
    def _calculate_xp_to_next_level(self, total_xp: int) -> int:
        """Calculate XP needed to reach next level."""
        current_level = self._calculate_level_from_xp(total_xp)
        
        # Calculate XP needed for current level
        xp_for_current = 0
        xp_needed = 100
        for _ in range(current_level - 1):
            xp_for_current += xp_needed
            xp_needed = int(xp_needed * 1.5)
        
        # XP needed for next level
        xp_for_next = xp_for_current + xp_needed
        
        return xp_for_next - total_xp
    
    async def create_study_groups(self):
        """Create study groups and community events."""
        logger.info("👥 Creating study groups and community events...")
        
        from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance
        
        # Study group templates
        group_templates = [
            {
                "name": "ML Study Circle",
                "description": "Weekly discussions about machine learning concepts and projects",
                "category": "technology",
                "max_members": 15
            },
            {
                "name": "Data Science Book Club", 
                "description": "Reading and discussing data science books together",
                "category": "technology",
                "max_members": 20
            },
            {
                "name": "Spanish Conversation Practice",
                "description": "Practice speaking Spanish in a supportive environment",
                "category": "language",
                "max_members": 10
            },
            {
                "name": "UX Design Workshop Group",
                "description": "Hands-on UX design practice and portfolio reviews", 
                "category": "design",
                "max_members": 12
            },
            {
                "name": "Digital Marketing Masterminds",
                "description": "Share strategies and analyze successful campaigns together",
                "category": "business", 
                "max_members": 25
            },
            {
                "name": "Code Review Circle",
                "description": "Peer code reviews and programming best practices",
                "category": "technology",
                "max_members": 18
            }
        ]
        
        # Create study groups
        for template in group_templates:
            try:
                # Select a creator (preferably instructor or active user)
                creators = [u for u in self.created_users 
                           if u["archetype"]["role"] in ["teacher", "researcher", "entrepreneur"]]
                if not creators:
                    creators = self.created_users[:10]  # Fallback
                    
                creator = random.choice(creators)
                
                study_group = StudyGroup(
                    name=template["name"],
                    description=template["description"],
                    creator_id=creator["user"].id,
                    category=template["category"],
                    max_members=template["max_members"],
                    is_active=True,
                    is_public=random.choice([True, True, False]),  # Mostly public
                    created_at=fake.date_time_between(start_date='-60d', end_date='-7d')
                )
                
                self.db_session.add(study_group)
                await self.db_session.flush()
                
                # Add creator as member
                creator_membership = GroupMembership(
                    user_id=creator["user"].id,
                    study_group_id=study_group.id,
                    role="admin",
                    joined_at=study_group.created_at
                )
                self.db_session.add(creator_membership)
                
                # Add other members
                interested_users = [
                    u for u in self.created_users 
                    if (template["category"] in u["interests"] or 
                        any(cat in interest for interest in u["interests"] for cat in [template["category"]]))
                    and u["user"].id != creator["user"].id
                ]
                
                num_members = random.randint(3, min(template["max_members"] - 1, len(interested_users)))
                members = random.sample(interested_users, min(num_members, len(interested_users)))
                
                for member_info in members:
                    membership = GroupMembership(
                        user_id=member_info["user"].id,
                        study_group_id=study_group.id,
                        role="member",
                        joined_at=fake.date_time_between(
                            start_date=study_group.created_at,
                            end_date='now'
                        )
                    )
                    self.db_session.add(membership)
                
                # Create community events for this group
                await self._create_community_events(study_group, creator)
                
                self.created_study_groups.append({
                    "group": study_group,
                    "template": template,
                    "creator": creator
                })
                
                logger.info(f"   Created study group: {study_group.name}")
                
            except Exception as e:
                logger.warning(f"Failed to create study group {template['name']}: {e}")
                continue
        
        await self.db_session.commit()
        logger.info(f"✅ Created {len(self.created_study_groups)} study groups with events")
    
    async def _create_community_events(self, study_group, creator):
        """Create community events for a study group."""
        from lyo_app.community.models import CommunityEvent, EventAttendance
        
        event_templates = [
            "Weekly Study Session",
            "Project Showcase",
            "Q&A with Expert",
            "Peer Review Workshop",
            "Group Discussion",
            "Practice Session"
        ]
        
        # Create 1-3 events per group
        num_events = random.randint(1, 3)
        
        for _ in range(num_events):
            event_name = f"{study_group.name}: {random.choice(event_templates)}"
            
            event = CommunityEvent(
                title=event_name,
                description=f"Join us for an engaging {random.choice(event_templates).lower()} session!",
                organizer_id=creator["user"].id,
                study_group_id=study_group.id,
                event_type="virtual",
                start_time=fake.date_time_between(start_date='now', end_date='+30d'),
                duration_minutes=random.choice([60, 90, 120]),
                max_attendees=study_group.max_members,
                is_public=study_group.is_public,
                created_at=fake.date_time_between(start_date=study_group.created_at, end_date='now')
            )
            
            # Set end time
            event.end_time = event.start_time.replace() + timedelta(minutes=event.duration_minutes)
            
            self.db_session.add(event)
            await self.db_session.flush()
            
            # Create event attendances (some group members)
            from lyo_app.community.models import GroupMembership
            from sqlalchemy import select
            
            result = await self.db_session.execute(
                select(GroupMembership).where(GroupMembership.study_group_id == study_group.id)
            )
            memberships = result.scalars().all()
            
            attendee_count = random.randint(2, min(len(memberships), event.max_attendees))
            attendees = random.sample(memberships, attendee_count)
            
            for membership in attendees:
                attendance = EventAttendance(
                    user_id=membership.user_id,
                    event_id=event.id,
                    status=random.choice(["registered", "attended", "registered"]),  # Bias toward registered
                    registered_at=fake.date_time_between(
                        start_date=event.created_at,
                        end_date='now'
                    )
                )
                self.db_session.add(attendance)
    
    async def create_ai_study_data(self):
        """Create AI study sessions and interactions."""
        logger.info("🤖 Creating AI study data...")
        
        from lyo_app.ai_study.models import StudySession, StudyMessage
        
        # AI study topics and queries
        study_topics = [
            "machine learning fundamentals",
            "python data structures", 
            "digital marketing strategies",
            "UX design principles",
            "Spanish grammar rules",
            "statistical analysis methods",
            "web development basics",
            "project management frameworks"
        ]
        
        sample_queries = [
            "Can you explain this concept in simple terms?",
            "What are the key points I should remember?",
            "How does this apply to real-world scenarios?",
            "Can you give me some practice questions?",
            "What are common mistakes to avoid?",
            "How does this relate to what I learned earlier?",
            "Can you summarize the main ideas?",
            "What resources would you recommend for deeper learning?"
        ]
        
        ai_responses = [
            "Great question! Let me break this down for you step by step...",
            "This is a fundamental concept that connects to several other topics...",
            "Here's a practical example that might help illustrate this...",
            "I'd recommend focusing on these key areas...",
            "Based on your learning style, here's an approach that might work well...",
            "This reminds me of a related concept we discussed earlier...",
            "Let me provide some practice exercises to reinforce this...",
            "Here are some additional resources that dive deeper into this topic..."
        ]
        
        # Create study sessions for active users
        active_users = random.sample(self.created_users, min(25, len(self.created_users)))
        
        for user_info in active_users:
            user = user_info["user"]
            user_interests = user_info["interests"]
            
            # Create 1-5 study sessions per user
            num_sessions = random.randint(1, 5)
            
            for _ in range(num_sessions):
                # Choose topic based on user interests
                if user_interests:
                    relevant_topics = [topic for topic in study_topics 
                                     if any(interest in topic or topic in interest 
                                           for interest in user_interests)]
                    if relevant_topics:
                        topic = random.choice(relevant_topics)
                    else:
                        topic = random.choice(study_topics)
                else:
                    topic = random.choice(study_topics)
                
                session = StudySession(
                    user_id=user.id,
                    session_name=f"Study: {topic.title()}",
                    subject=topic,
                    started_at=fake.date_time_between(start_date='-30d', end_date='now'),
                    is_active=random.choice([True, False]),
                    message_count=0
                )
                
                # Set end time if session is not active
                if not session.is_active:
                    session.ended_at = session.started_at + timedelta(
                        minutes=random.randint(15, 120)
                    )
                
                self.db_session.add(session)
                await self.db_session.flush()
                
                # Create messages for this session
                num_messages = random.randint(4, 15)
                session.message_count = num_messages
                
                message_time = session.started_at
                
                for i in range(num_messages):
                    # Alternate between user and AI messages
                    is_user_message = i % 2 == 0
                    
                    if is_user_message:
                        content = random.choice(sample_queries)
                        message_type = "user_query"
                        sender = "user"
                    else:
                        content = random.choice(ai_responses)
                        message_type = "ai_response" 
                        sender = "ai"
                    
                    message = StudyMessage(
                        session_id=session.id,
                        user_id=user.id,
                        content=content,
                        message_type=message_type,
                        sender=sender,
                        created_at=message_time,
                        tokens_used=random.randint(50, 200) if sender == "ai" else 0
                    )
                    
                    self.db_session.add(message)
                    
                    # Increment message time
                    message_time += timedelta(minutes=random.randint(1, 10))
        
        await self.db_session.commit()
        logger.info("✅ Created AI study sessions and messages")
    
    async def close(self):
        """Clean up database connections."""
        if self.db_session:
            await self.db_session.close()
    
    async def print_summary(self):
        """Print a summary of created data."""
        logger.info("\n" + "=" * 60)
        logger.info("🎉 DATABASE SEEDING COMPLETE!")
        logger.info("=" * 60)
        
        logger.info(f"📊 SUMMARY:")
        logger.info(f"   👥 Users: {len(self.created_users)}")
        logger.info(f"   📚 Courses: {len(self.created_courses)}")
        logger.info(f"   💬 Posts: {len(self.created_posts)}")
        logger.info(f"   🏫 Study Groups: {len(self.created_study_groups)}")
        
        # Print demo users for easy testing
        demo_users = [u for u in self.created_users if u.get("is_demo")]
        if demo_users:
            logger.info(f"\n🎭 DEMO USERS (for testing):")
            for user_info in demo_users:
                user = user_info["user"]
                logger.info(f"   Email: {user_info['email']}")
                logger.info(f"   Username: {user_info['username']}")
                logger.info(f"   Password: {user_info['password']}")
                logger.info(f"   Role: {user.get_role_names()}")
                logger.info("   ---")
        
        # Print some regular users for testing
        regular_test_users = [u for u in self.created_users[:5] if not u.get("is_demo")]
        if regular_test_users:
            logger.info(f"\n👤 SAMPLE TEST USERS:")
            for user_info in regular_test_users:
                logger.info(f"   Email: {user_info['email']} | Password: {user_info['password']}")
        
        logger.info(f"\n🔗 NEXT STEPS:")
        logger.info(f"   1. Start your server: python3 start_server.py")
        logger.info(f"   2. Access API docs: http://localhost:8000/docs")
        logger.info(f"   3. Test with demo users above")
        logger.info(f"   4. Explore the rich test data in your app!")
        logger.info("=" * 60)


async def main():
    """Main seeding function."""
    parser = argparse.ArgumentParser(description="Seed LyoBackend database with fake users and data")
    parser.add_argument("--users", type=int, default=30, help="Number of fake users to create")
    parser.add_argument("--clear-existing", action="store_true", help="Clear existing test data first")
    parser.add_argument("--preset", choices=["demo", "development", "testing"], 
                       help="Use predefined seeding presets")
    parser.add_argument("--skip-learning", action="store_true", help="Skip creating learning content")
    parser.add_argument("--skip-social", action="store_true", help="Skip creating social content")
    parser.add_argument("--skip-gamification", action="store_true", help="Skip creating gamification data")
    parser.add_argument("--skip-community", action="store_true", help="Skip creating community content")
    parser.add_argument("--skip-ai", action="store_true", help="Skip creating AI study data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Adjust user count based on preset
    if args.preset == "demo":
        user_count = 5
    elif args.preset == "development":
        user_count = 25
    elif args.preset == "testing":
        user_count = 100
    else:
        user_count = args.users
    
    seeder = DatabaseSeeder()
    
    try:
        # Initialize
        if not await seeder.initialize():
            logger.error("Failed to initialize seeder")
            return False
        
        # Clear existing data if requested
        if args.clear_existing:
            await seeder.clear_existing_data()
        
        # Create users
        if args.preset == "demo":
            await seeder.create_demo_users()
        else:
            await seeder.create_fake_users(user_count)
        
        # Create content based on flags
        if not args.skip_learning:
            await seeder.create_learning_content(len(seeder.created_users))
        
        if not args.skip_social:
            await seeder.create_social_content()
        
        if not args.skip_gamification:
            await seeder.create_gamification_data()
        
        if not args.skip_community:
            await seeder.create_study_groups()
        
        if not args.skip_ai:
            await seeder.create_ai_study_data()
        
        # Print summary
        await seeder.print_summary()
        
        return True
        
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await seeder.close()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
