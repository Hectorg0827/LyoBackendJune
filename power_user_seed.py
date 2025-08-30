#!/usr/bin/env python3
"""
🌟 Power Users Seeder for LyoBackend
Creates 20 highly active power users with extensive content and engagement.

Power users are characterized by:
- High activity levels (posts, comments, courses)
- Rich profiles with detailed bios and achievements
- Leadership roles in communities
- Extensive learning histories
- Strong social connections
- Advanced gamification stats
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
import random

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from faker import Faker
    fake = Faker(['en_US', 'es_ES', 'fr_FR', 'de_DE', 'it_IT'])
    print("✅ Faker imported successfully")
except ImportError:
    print("❌ Faker not available")
    sys.exit(1)

class PowerUserSeeder:
    """Creates power users with extensive content."""
    
    def __init__(self):
        self.db_session = None
        self.power_users = []
        self.created_courses = []
        self.created_posts = []
        
    async def initialize(self):
        """Initialize database connection and services."""
        try:
            # Set environment variables explicitly if not set
            import os
            if not os.getenv('SECRET_KEY'):
                os.environ['SECRET_KEY'] = 'P9tr2ptj1LZxVYmeygu6GbVWicoiU3058pbL+ZmcaMY='
            if not os.getenv('JWT_SECRET_KEY'):
                os.environ['JWT_SECRET_KEY'] = 'P9tr2ptj1LZxVYmeygu6GbVWicoiU3058pbL+ZmcaMY='
            
            from lyo_app.core.database import AsyncSessionLocal, init_db
            from lyo_app.auth.service import AuthService
            from lyo_app.auth.rbac_service import RBACService
            
            # Initialize database
            await init_db()
            
            # Create database session
            self.db_session = AsyncSessionLocal()
            
            # Initialize services
            self.auth_service = AuthService()
            self.rbac_service = RBACService(self.db_session)
            
            # Initialize RBAC system
            await self.rbac_service.initialize_default_roles_and_permissions()
            
            print("✅ Database connection and services initialized")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def create_power_users(self, count: int = 20):
        """Create power users with rich profiles."""
        print(f"🌟 Creating {count} power users...")
        
        from lyo_app.auth.schemas import UserCreate
        from lyo_app.auth.rbac import RoleType
        
        # Power user archetypes with specific characteristics
        power_archetypes = [
            {
                "type": "tech_leader",
                "interests": ["technology", "AI", "machine_learning", "leadership"],
                "bio_template": "Tech industry veteran with {years}+ years experience in {specialty}. Passionate about mentoring and sharing knowledge in {focus_area}. {achievement}",
                "specialties": ["software architecture", "data science", "AI/ML", "product management"],
                "achievements": ["Built and led teams of 50+", "Scaled systems to millions of users", "Published research papers", "Keynote speaker at major conferences"],
                "role_chance": {"instructor": 0.8, "student": 0.2}
            },
            {
                "type": "academic_expert",
                "interests": ["research", "education", "science", "writing"],
                "bio_template": "Professor and researcher specializing in {specialty}. Author of {publications} publications and {books} books. Dedicated to advancing knowledge in {focus_area}.",
                "specialties": ["computer science", "data science", "psychology", "education technology"],
                "achievements": ["PhD from top university", "100+ peer-reviewed papers", "Award-winning educator", "Invited lecturer worldwide"],
                "role_chance": {"instructor": 0.9, "student": 0.1}
            },
            {
                "type": "entrepreneur",
                "interests": ["startups", "business", "innovation", "networking"],
                "bio_template": "Serial entrepreneur with {companies} successful exits. Currently building the future of {focus_area}. Investor and mentor to {mentees}+ startups.",
                "specialties": ["fintech", "edtech", "healthtech", "enterprise software"],
                "achievements": ["Raised $50M+ in funding", "Successful IPO/acquisition", "Featured in major media", "Angel investor in 100+ startups"],
                "role_chance": {"instructor": 0.7, "student": 0.3}
            },
            {
                "type": "industry_expert",
                "interests": ["consulting", "strategy", "leadership", "innovation"],
                "bio_template": "Senior executive at Fortune 500 companies with expertise in {specialty}. Consultant to global organizations on {focus_area} transformation.",
                "specialties": ["digital transformation", "organizational development", "innovation management", "strategic planning"],
                "achievements": ["Led billion-dollar transformations", "Board member at multiple companies", "Recognized thought leader", "International speaker"],
                "role_chance": {"instructor": 0.6, "student": 0.4}
            },
            {
                "type": "creative_innovator",
                "interests": ["design", "creativity", "user_experience", "innovation"],
                "bio_template": "Award-winning {role} with {years}+ years creating transformative user experiences. Pioneer in {specialty} design thinking.",
                "specialties": ["UX/UI design", "product design", "creative direction", "design systems"],
                "achievements": ["Won major design awards", "Products used by millions", "Design team leader", "Design conference organizer"],
                "role_chance": {"instructor": 0.5, "student": 0.5}
            }
        ]
        
        for i in range(count):
            try:
                # Select archetype
                archetype = random.choice(power_archetypes)
                
                # Generate rich profile
                first_name = fake.first_name()
                last_name = fake.last_name()
                username = f"{first_name.lower()}.{last_name.lower()}.{random.randint(100, 999)}"
                email = f"{username}@{random.choice(['company.com', 'university.edu', 'consulting.com', 'startup.io'])}"
                
                # Create detailed bio
                years = random.randint(8, 25)
                specialty = random.choice(archetype["specialties"])
                focus_area = random.choice(archetype["interests"])
                achievement = random.choice(archetype["achievements"])
                
                bio_data = {
                    "years": years,
                    "specialty": specialty,
                    "focus_area": focus_area,
                    "achievement": achievement,
                    "companies": random.randint(2, 5),
                    "publications": random.randint(20, 100),
                    "books": random.randint(1, 5),
                    "mentees": random.randint(50, 200),
                    "role": random.choice(["designer", "architect", "strategist", "innovator"])
                }
                
                bio = archetype["bio_template"].format(**bio_data)
                
                # Create user
                user_data = UserCreate(
                    email=email,
                    username=username,
                    password="PowerUser123!",
                    confirm_password="PowerUser123!",
                    first_name=first_name,
                    last_name=last_name
                )
                
                user = await self.auth_service.register_user(self.db_session, user_data)
                
                # Assign role based on archetype
                if random.random() < archetype["role_chance"]["instructor"]:
                    await self.rbac_service.assign_role_to_user(user.id, RoleType.INSTRUCTOR.value)
                    user_role = "instructor"
                else:
                    user_role = "student"
                
                # Update profile with rich information
                user.bio = bio
                user.avatar_url = f"https://api.dicebear.com/7.x/avataaars/svg?seed={username}"
                user.last_login = fake.date_time_between(start_date='-3d', end_date='now')
                user.is_verified = True
                
                # Store power user info
                power_user_info = {
                    "user": user,
                    "archetype": archetype,
                    "email": email,
                    "username": username,
                    "password": "PowerUser123!",
                    "interests": archetype["interests"],
                    "role": user_role,
                    "years_experience": years,
                    "specialty": specialty,
                    "is_power_user": True
                }
                
                self.power_users.append(power_user_info)
                
                if i % 5 == 0:
                    print(f"   Created power user {i+1}/{count}: {user.username} ({user_role})")
                    
            except Exception as e:
                print(f"❌ Failed to create power user {i}: {e}")
                continue
        
        await self.db_session.commit()
        print(f"✅ Created {len(self.power_users)} power users")
    
    async def create_extensive_courses(self):
        """Create comprehensive courses by power users."""
        print("📚 Creating extensive learning content...")
        
        from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion
        
        # Advanced course templates for power users
        advanced_courses = [
            {
                "title": "Advanced Machine Learning in Production",
                "description": "Master the art of deploying ML models at scale with real-world case studies and hands-on projects.",
                "category": "technology",
                "difficulty": "advanced",
                "lessons": [
                    "ML System Design Principles",
                    "Model Serving Architecture",
                    "A/B Testing for ML Models",
                    "Monitoring Model Performance",
                    "Scaling ML Infrastructure",
                    "MLOps Best Practices",
                    "Real-time Feature Engineering",
                    "Model Versioning and Rollback",
                    "Cross-functional ML Teams",
                    "Case Study: Netflix Recommendation System"
                ],
                "archetype_match": ["tech_leader", "academic_expert"]
            },
            {
                "title": "Startup Leadership Masterclass",
                "description": "From zero to unicorn: comprehensive guide to building and scaling successful startups.",
                "category": "business",
                "difficulty": "advanced",
                "lessons": [
                    "Vision and Product-Market Fit",
                    "Building High-Performance Teams",
                    "Fundraising Strategy and Execution",
                    "Scaling Operations and Culture",
                    "Strategic Partnerships",
                    "International Expansion",
                    "Crisis Management",
                    "Exit Strategies",
                    "Board Management",
                    "Case Study: Successful Unicorn Journey"
                ],
                "archetype_match": ["entrepreneur", "industry_expert"]
            },
            {
                "title": "Design Systems at Enterprise Scale",
                "description": "Build, implement, and maintain design systems that scale across large organizations.",
                "category": "design",
                "difficulty": "advanced",
                "lessons": [
                    "Design System Fundamentals",
                    "Component Library Architecture",
                    "Cross-Platform Consistency",
                    "Accessibility at Scale",
                    "Design Tokens and Variables",
                    "Documentation and Guidelines",
                    "Team Adoption Strategies",
                    "Measuring Design System Success",
                    "Evolution and Maintenance",
                    "Case Study: Airbnb Design Language System"
                ],
                "archetype_match": ["creative_innovator", "tech_leader"]
            },
            {
                "title": "Digital Transformation Leadership",
                "description": "Lead organizational change in the digital age with proven frameworks and strategies.",
                "category": "business",
                "difficulty": "advanced",
                "lessons": [
                    "Digital Strategy Development",
                    "Change Management at Scale",
                    "Technology Integration Planning",
                    "Cultural Transformation",
                    "Data-Driven Decision Making",
                    "Agile Organization Design",
                    "Innovation Management",
                    "Stakeholder Alignment",
                    "Measuring Transformation Success",
                    "Case Study: Fortune 500 Digital Pivot"
                ],
                "archetype_match": ["industry_expert", "tech_leader"]
            },
            {
                "title": "Advanced Data Science Techniques",
                "description": "Cutting-edge data science methods with practical applications in industry.",
                "category": "technology",
                "difficulty": "advanced",
                "lessons": [
                    "Advanced Statistical Modeling",
                    "Deep Learning Architectures",
                    "Causal Inference Methods",
                    "Bayesian Data Analysis",
                    "Time Series Forecasting",
                    "Graph Neural Networks",
                    "Reinforcement Learning Applications",
                    "Ethical AI and Fairness",
                    "Model Interpretability",
                    "Research to Production Pipeline"
                ],
                "archetype_match": ["academic_expert", "tech_leader"]
            }
        ]
        
        # Create courses by matching instructors to their expertise
        instructors = [pu for pu in self.power_users if pu["role"] == "instructor"]
        
        for course_template in advanced_courses:
            try:
                # Find best instructor for this course
                suitable_instructors = [
                    inst for inst in instructors 
                    if inst["archetype"]["type"] in course_template["archetype_match"]
                ]
                
                if not suitable_instructors:
                    suitable_instructors = instructors[:3]  # Fallback
                
                instructor = random.choice(suitable_instructors)
                
                # Create course
                course = Course(
                    title=course_template["title"],
                    description=course_template["description"],
                    instructor_id=instructor["user"].id,
                    category=course_template["category"],
                    difficulty_level=course_template["difficulty"],
                    estimated_duration_hours=len(course_template["lessons"]) * 3,  # More intensive
                    is_published=True,
                    created_at=fake.date_time_between(start_date='-180d', end_date='-30d')
                )
                
                self.db_session.add(course)
                await self.db_session.flush()
                
                # Create detailed lessons
                for i, lesson_title in enumerate(course_template["lessons"]):
                    lesson = Lesson(
                        title=lesson_title,
                        content=fake.text(max_nb_chars=800),  # More detailed content
                        course_id=course.id,
                        order_index=i + 1,
                        duration_minutes=random.randint(45, 90),  # Longer lessons
                        is_published=True
                    )
                    self.db_session.add(lesson)
                
                self.created_courses.append({
                    "course": course,
                    "template": course_template,
                    "instructor": instructor
                })
                
                print(f"   Created course: {course.title} by {instructor['username']}")
                
            except Exception as e:
                print(f"❌ Failed to create course: {e}")
                continue
        
        await self.db_session.commit()
        print(f"✅ Created {len(self.created_courses)} advanced courses")
        
        # Create enrollments with high completion rates
        await self._create_power_user_enrollments()
    
    async def _create_power_user_enrollments(self):
        """Create course enrollments for power users with high engagement."""
        from lyo_app.learning.models import CourseEnrollment, LessonCompletion, Lesson
        from sqlalchemy import select
        
        for user_info in self.power_users:
            user = user_info["user"]
            interests = user_info["interests"]
            
            # Power users enroll in more courses
            courses_to_enroll = random.randint(3, 6)
            enrolled_count = 0
            
            for course_info in self.created_courses:
                if enrolled_count >= courses_to_enroll:
                    break
                    
                course = course_info["course"]
                course_category = course_info["template"]["category"]
                
                # Higher enrollment probability for power users
                enroll_probability = 0.3  # Base
                if any(interest in course_category for interest in interests):
                    enroll_probability = 0.9  # Very high for matching interests
                elif user_info["role"] == "instructor":
                    enroll_probability = 0.6  # Instructors explore more
                
                if random.random() < enroll_probability:
                    try:
                        # Power users have higher completion rates
                        progress = random.randint(70, 100)  # 70-100% completion
                        
                        enrollment = CourseEnrollment(
                            user_id=user.id,
                            course_id=course.id,
                            enrolled_at=fake.date_time_between(start_date='-120d', end_date='-10d'),
                            progress_percentage=progress
                        )
                        self.db_session.add(enrollment)
                        await self.db_session.flush()
                        
                        # Create lesson completions
                        result = await self.db_session.execute(
                            select(Lesson).where(Lesson.course_id == course.id).order_by(Lesson.order_index)
                        )
                        lessons = result.scalars().all()
                        
                        lessons_to_complete = int((progress / 100) * len(lessons))
                        
                        for i in range(lessons_to_complete):
                            lesson = lessons[i]
                            completion = LessonCompletion(
                                user_id=user.id,
                                lesson_id=lesson.id,
                                course_id=course.id,
                                completed_at=fake.date_time_between(
                                    start_date=enrollment.enrolled_at,
                                    end_date='now'
                                ),
                                time_spent_minutes=random.randint(lesson.duration_minutes, lesson.duration_minutes * 2)
                            )
                            self.db_session.add(completion)
                        
                        enrolled_count += 1
                        
                    except Exception as e:
                        continue
        
        await self.db_session.commit()
    
    async def create_rich_social_content(self):
        """Create extensive social content by power users."""
        print("💬 Creating rich social content...")
        
        from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow
        
        # High-quality post templates for power users
        power_post_templates = [
            "🚀 Just launched our new ML pipeline that processes 10M+ events/day! Key learnings: {insight}. Happy to share the architecture details. #MachineLearning #Scale",
            "📊 After analyzing 5 years of user behavior data, here are the 3 most important patterns every product manager should know: {insight} 🧵",
            "💡 Hot take: {opinion}. Here's why this matters for the future of {field}: {reasoning}",
            "🎯 Completed my 50th course this year! The most impactful was definitely {course}. Key takeaways: {insight}",
            "🔥 Just finished mentoring 20 startups this quarter. The common success pattern I see: {insight}. Thread 👇",
            "📚 Reading recommendation: {book} completely changed how I think about {topic}. Essential for anyone in {field}",
            "⚡ Quick tip for {audience}: {insight}. This simple change increased our {metric} by 40%",
            "🌟 Proud to announce our team achieved {milestone}! The secret sauce: {insight}. AMA about the journey!",
            "🤔 Interesting observation from working with 100+ companies: {insight}. What's your experience with {topic}?",
            "🎉 Celebrating 10 years in {field}! The biggest lesson: {insight}. What would you add to this list?",
            "📈 Data from our latest study shows {finding}. Implications for {industry}: {insight}",
            "💭 Unpopular opinion: {opinion}. Been thinking about this after {experience}. Thoughts?"
        ]
        
        insights = [
            "consistency beats perfection every time",
            "user feedback is your north star",
            "technical debt compounds faster than financial debt",
            "culture eats strategy for breakfast",
            "the best features often come from customer complaints",
            "automation should enhance human creativity, not replace it",
            "diverse teams consistently outperform homogeneous ones",
            "the biggest breakthroughs happen at the intersection of disciplines"
        ]
        
        opinions = [
            "remote work has fundamentally changed how we should measure productivity",
            "most AI projects fail not because of technology but because of organizational readiness",
            "the future belongs to generalists who can connect disparate domains",
            "traditional education is becoming irrelevant faster than we admit"
        ]
        
        # Create posts for each power user
        for user_info in self.power_users:
            user = user_info["user"]
            specialty = user_info["specialty"]
            archetype = user_info["archetype"]["type"]
            
            # Power users create more content
            num_posts = random.randint(8, 15)
            
            for _ in range(num_posts):
                try:
                    template = random.choice(power_post_templates)
                    
                    # Generate contextual content
                    content = template.format(
                        insight=random.choice(insights),
                        opinion=random.choice(opinions),
                        field=specialty,
                        course=f"Advanced {specialty.title()}",
                        book=f"The Future of {specialty.title()}",
                        topic=random.choice(user_info["interests"]),
                        audience=f"{specialty} professionals",
                        metric=random.choice(["conversion", "engagement", "retention", "satisfaction"]),
                        milestone=f"{random.randint(10, 100)}K users",
                        finding=f"{random.randint(60, 90)}% of companies struggle with {specialty}",
                        industry=specialty,
                        experience=f"consulting with Fortune 500 companies"
                    )
                    
                    post = Post(
                        content=content,
                        author_id=user.id,
                        created_at=fake.date_time_between(start_date='-90d', end_date='now'),
                        likes_count=random.randint(50, 300),  # Power users get more engagement
                        comments_count=random.randint(10, 50),
                        is_published=True
                    )
                    
                    self.db_session.add(post)
                    await self.db_session.flush()
                    
                    self.created_posts.append({
                        "post": post,
                        "author": user_info
                    })
                    
                except Exception as e:
                    continue
        
        await self.db_session.commit()
        
        # Create high-quality comments and reactions
        await self._create_power_user_interactions()
        
        # Create strategic follow relationships
        await self._create_power_user_network()
        
        print(f"✅ Created {len(self.created_posts)} high-quality posts")
    
    async def _create_power_user_interactions(self):
        """Create meaningful comments and reactions."""
        from lyo_app.feeds.models import Comment, PostReaction
        
        # High-quality comment templates
        quality_comments = [
            "Excellent insights! This aligns with what we've seen at {company}. The key challenge we faced was {challenge}.",
            "This is spot on. I'd add that {additional_insight} is equally important based on my experience with {context}.",
            "Great post! For others interested in this topic, I recommend checking out {resource}. Game-changer for our team.",
            "Love this perspective. We implemented something similar and saw {result}. Happy to share our learnings.",
            "Thought-provoking as always! Have you considered the implications for {related_area}?",
            "This resonates strongly. In our recent project with {client}, we discovered {finding}.",
            "Brilliant analysis! This connects well with the research from {source}. The convergence is fascinating.",
            "Absolutely agree. The trend we're seeing in {industry} supports this thesis completely."
        ]
        
        for post_info in self.created_posts:
            post = post_info["post"]
            
            # Select other power users to comment
            num_comments = min(post.comments_count, random.randint(3, 8))
            commenters = random.sample(self.power_users, min(num_comments, len(self.power_users)))
            
            for commenter in commenters:
                if commenter["user"].id != post.author_id:
                    try:
                        comment_template = random.choice(quality_comments)
                        comment_content = comment_template.format(
                            company=f"{commenter['specialty'].title()} Corp",
                            challenge=f"scaling {commenter['specialty']} operations",
                            additional_insight=random.choice([
                                "stakeholder alignment",
                                "technical implementation",
                                "change management",
                                "user adoption"
                            ]),
                            context=f"{commenter['years_experience']} years in {commenter['specialty']}",
                            resource=f"the latest {commenter['specialty']} research",
                            result=f"40% improvement in {random.choice(['efficiency', 'outcomes', 'satisfaction'])}",
                            related_area=random.choice(commenter["interests"]),
                            client=f"a major {commenter['specialty']} company",
                            finding=f"the importance of {random.choice(['data-driven decisions', 'user-centric design', 'iterative approach'])}",
                            source=f"{commenter['specialty']} Institute",
                            industry=commenter['specialty']
                        )
                        
                        comment = Comment(
                            content=comment_content,
                            post_id=post.id,
                            author_id=commenter["user"].id,
                            created_at=fake.date_time_between(
                                start_date=post.created_at,
                                end_date='now'
                            ),
                            likes_count=random.randint(5, 25)
                        )
                        self.db_session.add(comment)
                        
                    except Exception as e:
                        continue
            
            # Create post reactions
            num_reactions = min(post.likes_count, random.randint(20, 100))
            reactors = random.sample(self.power_users, min(num_reactions, len(self.power_users)))
            
            for reactor in reactors:
                if reactor["user"].id != post.author_id:
                    try:
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
                    except Exception:
                        continue
        
        await self.db_session.commit()
    
    async def _create_power_user_network(self):
        """Create strategic follow relationships between power users."""
        from lyo_app.feeds.models import UserFollow
        
        for user_info in self.power_users:
            user = user_info["user"]
            
            # Power users follow other power users strategically
            potential_follows = []
            
            # Follow users with complementary expertise
            for other_user in self.power_users:
                if other_user["user"].id != user.id:
                    # High probability to follow if different but related expertise
                    if (other_user["archetype"]["type"] != user_info["archetype"]["type"] and
                        any(interest in other_user["interests"] for interest in user_info["interests"])):
                        potential_follows.append(other_user)
                    # Also follow users in same field (competitors/peers)
                    elif other_user["specialty"] == user_info["specialty"]:
                        potential_follows.append(other_user)
            
            # Power users follow many people (they're networkers)
            num_follows = random.randint(12, 18)
            follows = random.sample(potential_follows, min(num_follows, len(potential_follows)))
            
            for follow_target in follows:
                try:
                    follow = UserFollow(
                        follower_id=user.id,
                        followed_id=follow_target["user"].id,
                        created_at=fake.date_time_between(start_date='-180d', end_date='now')
                    )
                    self.db_session.add(follow)
                except Exception:
                    continue
        
        await self.db_session.commit()
    
    async def create_advanced_gamification(self):
        """Create advanced gamification data for power users."""
        print("🎮 Creating advanced gamification data...")
        
        from lyo_app.gamification.models import (
            UserXP, Achievement, UserAchievement, Streak, UserLevel, 
            XPActionType, AchievementType, AchievementRarity, StreakType
        )
        
        # Create power user specific achievements
        await self._create_power_achievements()
        
        for user_info in self.power_users:
            user = user_info["user"]
            
            # Power users have high XP from extensive activity
            total_xp = 0
            
            # Massive XP from teaching/creating content
            teaching_xp_records = random.randint(50, 100)
            for _ in range(teaching_xp_records):
                xp_amount = random.randint(25, 50)  # Higher XP per action
                total_xp += xp_amount
                
                xp_record = UserXP(
                    user_id=user.id,
                    action_type=random.choice([XPActionType.COURSE_COMPLETED, XPActionType.POST_CREATED]),
                    xp_earned=xp_amount,
                    context_type="power_user_activity",
                    earned_at=fake.date_time_between(start_date='-180d', end_date='now')
                )
                self.db_session.add(xp_record)
            
            # High XP from social engagement
            social_xp_records = random.randint(100, 200)
            for _ in range(social_xp_records):
                xp_amount = random.randint(5, 20)
                total_xp += xp_amount
                
                xp_record = UserXP(
                    user_id=user.id,
                    action_type=random.choice([XPActionType.COMMENT_CREATED, XPActionType.DAILY_LOGIN]),
                    xp_earned=xp_amount,
                    earned_at=fake.date_time_between(start_date='-180d', end_date='now')
                )
                self.db_session.add(xp_record)
            
            # Create high-level user level
            level = max(15, self._calculate_level_from_xp(total_xp))  # Power users are high level
            user_level = UserLevel(
                user_id=user.id,
                current_level=level,
                total_xp=total_xp,
                xp_to_next_level=self._calculate_xp_to_next_level(total_xp),
                levels_gained_today=random.randint(0, 2),
                last_level_up=fake.date_time_between(start_date='-30d', end_date='now')
            )
            self.db_session.add(user_level)
            
            # Create impressive streaks
            for streak_type in StreakType:
                current_streak = random.randint(30, 180)  # Long streaks
                longest_streak = max(current_streak + random.randint(0, 50), 100)
                
                streak = Streak(
                    user_id=user.id,
                    streak_type=streak_type,
                    current_count=current_streak,
                    longest_count=longest_streak,
                    last_activity_date=fake.date_time_between(start_date='-2d', end_date='now'),
                    is_active=True
                )
                self.db_session.add(streak)
        
        await self.db_session.commit()
        
        # Award achievements to power users
        await self._award_power_achievements()
        
        print("✅ Created advanced gamification data")
    
    async def _create_power_achievements(self):
        """Create achievements specifically for power users."""
        from lyo_app.gamification.models import Achievement, AchievementType, AchievementRarity
        
        power_achievements = [
            {
                "name": "Knowledge Architect",
                "description": "Create 5 comprehensive courses with high completion rates",
                "type": AchievementType.LEARNING,
                "rarity": AchievementRarity.EPIC,
                "xp_reward": 1000,
                "criteria": {"courses_created": 5, "avg_completion_rate": 0.8}
            },
            {
                "name": "Community Leader",
                "description": "Reach 1000+ followers and maintain high engagement",
                "type": AchievementType.SOCIAL,
                "rarity": AchievementRarity.LEGENDARY,
                "xp_reward": 2000,
                "criteria": {"followers": 1000, "avg_post_likes": 100}
            },
            {
                "name": "Influence Multiplier",
                "description": "Have your content shared 500+ times",
                "type": AchievementType.SOCIAL,
                "rarity": AchievementRarity.EPIC,
                "xp_reward": 1500,
                "criteria": {"content_shares": 500}
            },
            {
                "name": "Master Mentor",
                "description": "Successfully mentor 50+ learners to completion",
                "type": AchievementType.MILESTONE,
                "rarity": AchievementRarity.LEGENDARY,
                "xp_reward": 2500,
                "criteria": {"mentees_completed": 50}
            },
            {
                "name": "Innovation Pioneer",
                "description": "Be among first 10 to complete cutting-edge courses",
                "type": AchievementType.SPECIAL,
                "rarity": AchievementRarity.RARE,
                "xp_reward": 750,
                "criteria": {"early_adopter": True, "advanced_courses": 10}
            }
        ]
        
        for achievement_data in power_achievements:
            achievement = Achievement(
                name=achievement_data["name"],
                description=achievement_data["description"],
                type=achievement_data["type"],
                rarity=achievement_data["rarity"],
                xp_reward=achievement_data["xp_reward"],
                criteria=achievement_data["criteria"],
                icon_url=f"https://api.dicebear.com/7.x/shapes/svg?seed={achievement_data['name']}&backgroundColor=gold"
            )
            self.db_session.add(achievement)
        
        await self.db_session.commit()
    
    async def _award_power_achievements(self):
        """Award achievements to power users."""
        from lyo_app.gamification.models import Achievement, UserAchievement
        from sqlalchemy import select
        
        result = await self.db_session.execute(select(Achievement))
        achievements = result.scalars().all()
        
        for user_info in self.power_users:
            user = user_info["user"]
            
            # Power users get more achievements
            achievements_to_award = random.randint(5, 12)
            selected_achievements = random.sample(achievements, min(achievements_to_award, len(achievements)))
            
            for achievement in selected_achievements:
                try:
                    user_achievement = UserAchievement(
                        user_id=user.id,
                        achievement_id=achievement.id,
                        is_completed=True,
                        completed_at=fake.date_time_between(start_date='-120d', end_date='now'),
                        progress_data={"completion_rate": 1.0, "power_user": True}
                    )
                    self.db_session.add(user_achievement)
                except Exception:
                    continue
        
        await self.db_session.commit()
    
    def _calculate_level_from_xp(self, total_xp: int) -> int:
        """Calculate user level from total XP."""
        level = 1
        xp_needed = 100
        current_xp = total_xp
        
        while current_xp >= xp_needed:
            current_xp -= xp_needed
            level += 1
            xp_needed = int(xp_needed * 1.2)  # Gradual progression for high levels
            
        return min(level, 50)  # Cap at level 50
    
    def _calculate_xp_to_next_level(self, total_xp: int) -> int:
        """Calculate XP needed to reach next level."""
        current_level = self._calculate_level_from_xp(total_xp)
        
        xp_for_current = 0
        xp_needed = 100
        for _ in range(current_level - 1):
            xp_for_current += xp_needed
            xp_needed = int(xp_needed * 1.2)
        
        xp_for_next = xp_for_current + xp_needed
        return xp_for_next - total_xp
    
    async def create_study_groups_and_events(self):
        """Create study groups led by power users."""
        print("👥 Creating power user study groups...")
        
        from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance
        
        # Advanced study group templates
        advanced_groups = [
            {
                "name": "AI Research Collective",
                "description": "Weekly deep dives into cutting-edge AI research papers and implementations",
                "category": "technology",
                "max_members": 30,
                "archetype_match": ["tech_leader", "academic_expert"]
            },
            {
                "name": "Startup Founders Circle",
                "description": "Exclusive community for experienced entrepreneurs and startup founders",
                "category": "business",
                "max_members": 25,
                "archetype_match": ["entrepreneur", "industry_expert"]
            },
            {
                "name": "Design Leadership Forum",
                "description": "Strategic design thinking for senior design professionals",
                "category": "design",
                "max_members": 20,
                "archetype_match": ["creative_innovator", "industry_expert"]
            },
            {
                "name": "Executive Strategy Roundtable",
                "description": "C-level discussions on digital transformation and innovation",
                "category": "business",
                "max_members": 15,
                "archetype_match": ["industry_expert", "entrepreneur"]
            }
        ]
        
        for group_template in advanced_groups:
            try:
                # Find power user to lead this group
                suitable_leaders = [
                    pu for pu in self.power_users 
                    if pu["archetype"]["type"] in group_template["archetype_match"]
                ]
                
                if not suitable_leaders:
                    suitable_leaders = self.power_users[:3]
                
                leader = random.choice(suitable_leaders)
                
                study_group = StudyGroup(
                    name=group_template["name"],
                    description=group_template["description"],
                    creator_id=leader["user"].id,
                    category=group_template["category"],
                    max_members=group_template["max_members"],
                    is_active=True,
                    is_public=True,
                    created_at=fake.date_time_between(start_date='-120d', end_date='-30d')
                )
                
                self.db_session.add(study_group)
                await self.db_session.flush()
                
                # Add leader as admin
                leader_membership = GroupMembership(
                    user_id=leader["user"].id,
                    study_group_id=study_group.id,
                    role="admin",
                    joined_at=study_group.created_at
                )
                self.db_session.add(leader_membership)
                
                # Add other power users as members
                potential_members = [
                    pu for pu in self.power_users 
                    if (pu["user"].id != leader["user"].id and
                        any(interest in group_template["category"] for interest in pu["interests"]))
                ]
                
                num_members = random.randint(10, group_template["max_members"] - 1)
                members = random.sample(potential_members, min(num_members, len(potential_members)))
                
                for member in members:
                    membership = GroupMembership(
                        user_id=member["user"].id,
                        study_group_id=study_group.id,
                        role="member",
                        joined_at=fake.date_time_between(
                            start_date=study_group.created_at,
                            end_date='now'
                        )
                    )
                    self.db_session.add(membership)
                
                # Create premium events
                await self._create_premium_events(study_group, leader)
                
                print(f"   Created group: {study_group.name}")
                
            except Exception as e:
                print(f"❌ Failed to create study group: {e}")
                continue
        
        await self.db_session.commit()
        print("✅ Created power user study groups")
    
    async def _create_premium_events(self, study_group, leader):
        """Create high-value events for power user groups."""
        from lyo_app.community.models import CommunityEvent, EventAttendance, GroupMembership
        from sqlalchemy import select
        
        premium_events = [
            "Exclusive Industry Roundtable",
            "Expert Panel Discussion",
            "Advanced Workshop Series",
            "Networking & Knowledge Exchange",
            "Case Study Deep Dive",
            "Future Trends Symposium"
        ]
        
        # Create 3-5 events per group
        num_events = random.randint(3, 5)
        
        for _ in range(num_events):
            event_name = f"{study_group.name}: {random.choice(premium_events)}"
            
            event = CommunityEvent(
                title=event_name,
                description=f"Exclusive {random.choice(premium_events).lower()} for {study_group.name} members. Expert insights and networking opportunities.",
                organizer_id=leader["user"].id,
                study_group_id=study_group.id,
                event_type=random.choice(["virtual", "hybrid"]),
                start_time=fake.date_time_between(start_date='-30d', end_date='+60d'),
                duration_minutes=random.choice([90, 120, 180]),  # Longer, more valuable events
                max_attendees=study_group.max_members,
                is_public=False,  # Exclusive events
                created_at=fake.date_time_between(start_date=study_group.created_at, end_date='now')
            )
            
            event.end_time = event.start_time + timedelta(minutes=event.duration_minutes)
            self.db_session.add(event)
            await self.db_session.flush()
            
            # High attendance rates for premium events
            result = await self.db_session.execute(
                select(GroupMembership).where(GroupMembership.study_group_id == study_group.id)
            )
            memberships = result.scalars().all()
            
            attendance_rate = random.uniform(0.7, 0.9)  # High attendance
            attendee_count = int(len(memberships) * attendance_rate)
            attendees = random.sample(memberships, attendee_count)
            
            for membership in attendees:
                attendance = EventAttendance(
                    user_id=membership.user_id,
                    event_id=event.id,
                    status=random.choice(["attended", "attended", "registered"]),  # Bias toward attended
                    registered_at=fake.date_time_between(
                        start_date=event.created_at,
                        end_date=event.start_time
                    )
                )
                self.db_session.add(attendance)
    
    async def run_power_user_seeding(self):
        """Run complete power user seeding process."""
        print("🌟 STARTING POWER USER SEEDING")
        print("=" * 60)
        
        # Create power users
        await self.create_power_users(20)
        
        # Create extensive content
        await self.create_extensive_courses()
        await self.create_rich_social_content()
        await self.create_advanced_gamification()
        await self.create_study_groups_and_events()
        
        # Print summary
        await self.print_power_user_summary()
    
    async def print_power_user_summary(self):
        """Print summary of created power users."""
        print("\n" + "=" * 60)
        print("🎉 POWER USER SEEDING COMPLETE!")
        print("=" * 60)
        
        print(f"📊 SUMMARY:")
        print(f"   🌟 Power Users: {len(self.power_users)}")
        print(f"   📚 Advanced Courses: {len(self.created_courses)}")
        print(f"   💬 Quality Posts: {len(self.created_posts)}")
        
        print(f"\n🌟 POWER USER PROFILES:")
        archetype_counts = {}
        for user_info in self.power_users:
            archetype = user_info["archetype"]["type"]
            archetype_counts[archetype] = archetype_counts.get(archetype, 0) + 1
        
        for archetype, count in archetype_counts.items():
            print(f"   {archetype.replace('_', ' ').title()}: {count} users")
        
        print(f"\n👑 SAMPLE POWER USERS:")
        for user_info in self.power_users[:5]:
            print(f"   📧 {user_info['email']} (Password: PowerUser123!)")
            print(f"      Role: {user_info['role'].title()} | {user_info['archetype']['type'].replace('_', ' ').title()}")
            print(f"      Specialty: {user_info['specialty']}")
            print(f"      Experience: {user_info['years_experience']} years")
            print("      ---")
        
        print(f"\n🔗 NEXT STEPS:")
        print(f"   1. Test with power users above (Password: PowerUser123!)")
        print(f"   2. Explore rich content and interactions")
        print(f"   3. Review advanced courses and study groups")
        print(f"   4. Deploy updated backend to production")
        print("=" * 60)
    
    async def close(self):
        """Clean up database connections."""
        if self.db_session:
            await self.db_session.close()


async def main():
    """Main power user seeding function."""
    seeder = PowerUserSeeder()
    
    try:
        if not await seeder.initialize():
            print("❌ Failed to initialize power user seeder")
            return False
        
        await seeder.run_power_user_seeding()
        return True
        
    except Exception as e:
        print(f"❌ Power user seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await seeder.close()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
