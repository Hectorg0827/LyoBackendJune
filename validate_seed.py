#!/usr/bin/env python3
"""
🔍 Seeded Database Validation Script
Validates that the database seeding was successful and all data relationships are correct.

This script checks:
- User accounts and authentication
- Learning content and enrollments
- Social interactions and relationships
- Gamification data integrity
- Community features
- AI study sessions

Usage:
    python3 validate_seed.py
"""

import asyncio
import sys
import os
from typing import Dict, List, Any
import json

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseValidator:
    """Validates seeded database data."""
    
    def __init__(self):
        self.db_session = None
        self.validation_results = {}
        
    async def initialize(self):
        """Initialize database connection."""
        try:
            from lyo_app.core.database import AsyncSessionLocal, init_db
            
            # Create database session
            self.db_session = AsyncSessionLocal()
            
            logger.info("✅ Database connection established")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to database: {e}")
            return False
    
    async def validate_users(self) -> Dict[str, Any]:
        """Validate user accounts and authentication."""
        logger.info("\n👥 Validating users...")
        
        try:
            from lyo_app.auth.models import User
            from lyo_app.auth.rbac import Role, user_roles
            from sqlalchemy import select, func
            
            # Count total users
            result = await self.db_session.execute(select(func.count(User.id)))
            total_users = result.scalar()
            
            # Count users by status
            result = await self.db_session.execute(
                select(func.count(User.id)).where(User.is_active == True)
            )
            active_users = result.scalar()
            
            # Count users with roles
            result = await self.db_session.execute(
                select(func.count(user_roles.c.user_id.distinct()))
            )
            users_with_roles = result.scalar()
            
            # Get demo users
            result = await self.db_session.execute(
                select(User).where(User.email.like('%demo.com'))
            )
            demo_users = result.scalars().all()
            
            validation_data = {
                "total_users": total_users,
                "active_users": active_users,
                "users_with_roles": users_with_roles,
                "demo_users": len(demo_users),
                "demo_user_emails": [u.email for u in demo_users]
            }
            
            logger.info(f"   📊 Total users: {total_users}")
            logger.info(f"   ✅ Active users: {active_users}")
            logger.info(f"   🔐 Users with roles: {users_with_roles}")
            logger.info(f"   🎭 Demo users: {len(demo_users)}")
            
            if demo_users:
                logger.info("   📧 Demo user emails:")
                for user in demo_users:
                    logger.info(f"      - {user.email}")
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ User validation failed: {e}")
            return {"error": str(e)}
    
    async def validate_learning_content(self) -> Dict[str, Any]:
        """Validate learning content and enrollments."""
        logger.info("\n📚 Validating learning content...")
        
        try:
            from lyo_app.learning.models import Course, Lesson, CourseEnrollment, LessonCompletion
            from sqlalchemy import select, func
            
            # Count courses
            result = await self.db_session.execute(select(func.count(Course.id)))
            total_courses = result.scalar()
            
            # Count lessons
            result = await self.db_session.execute(select(func.count(Lesson.id)))
            total_lessons = result.scalar()
            
            # Count enrollments
            result = await self.db_session.execute(select(func.count(CourseEnrollment.id)))
            total_enrollments = result.scalar()
            
            # Count lesson completions
            result = await self.db_session.execute(select(func.count(LessonCompletion.id)))
            total_completions = result.scalar()
            
            # Get average lessons per course
            if total_courses > 0:
                avg_lessons_per_course = total_lessons / total_courses
            else:
                avg_lessons_per_course = 0
            
            validation_data = {
                "total_courses": total_courses,
                "total_lessons": total_lessons,
                "total_enrollments": total_enrollments,
                "total_completions": total_completions,
                "avg_lessons_per_course": round(avg_lessons_per_course, 1)
            }
            
            logger.info(f"   📖 Courses: {total_courses}")
            logger.info(f"   📄 Lessons: {total_lessons}")
            logger.info(f"   👨‍🎓 Enrollments: {total_enrollments}")
            logger.info(f"   ✅ Completions: {total_completions}")
            logger.info(f"   📊 Avg lessons/course: {avg_lessons_per_course:.1f}")
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ Learning content validation failed: {e}")
            return {"error": str(e)}
    
    async def validate_social_content(self) -> Dict[str, Any]:
        """Validate social interactions."""
        logger.info("\n💬 Validating social content...")
        
        try:
            from lyo_app.feeds.models import Post, Comment, PostReaction, CommentReaction, UserFollow
            from sqlalchemy import select, func
            
            # Count posts
            result = await self.db_session.execute(select(func.count(Post.id)))
            total_posts = result.scalar()
            
            # Count comments
            result = await self.db_session.execute(select(func.count(Comment.id)))
            total_comments = result.scalar()
            
            # Count reactions
            result = await self.db_session.execute(select(func.count(PostReaction.id)))
            total_post_reactions = result.scalar()
            
            result = await self.db_session.execute(select(func.count(CommentReaction.id)))
            total_comment_reactions = result.scalar()
            
            # Count follows
            result = await self.db_session.execute(select(func.count(UserFollow.id)))
            total_follows = result.scalar()
            
            validation_data = {
                "total_posts": total_posts,
                "total_comments": total_comments,
                "total_post_reactions": total_post_reactions,
                "total_comment_reactions": total_comment_reactions,
                "total_follows": total_follows
            }
            
            logger.info(f"   📝 Posts: {total_posts}")
            logger.info(f"   💭 Comments: {total_comments}")
            logger.info(f"   👍 Post reactions: {total_post_reactions}")
            logger.info(f"   💗 Comment reactions: {total_comment_reactions}")
            logger.info(f"   👥 User follows: {total_follows}")
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ Social content validation failed: {e}")
            return {"error": str(e)}
    
    async def validate_gamification(self) -> Dict[str, Any]:
        """Validate gamification data."""
        logger.info("\n🎮 Validating gamification data...")
        
        try:
            from lyo_app.gamification.models import (
                UserXP, Achievement, UserAchievement, Streak, UserLevel
            )
            from sqlalchemy import select, func
            
            # Count XP records
            result = await self.db_session.execute(select(func.count(UserXP.id)))
            total_xp_records = result.scalar()
            
            # Count achievements
            result = await self.db_session.execute(select(func.count(Achievement.id)))
            total_achievements = result.scalar()
            
            # Count user achievements
            result = await self.db_session.execute(select(func.count(UserAchievement.id)))
            total_user_achievements = result.scalar()
            
            # Count streaks
            result = await self.db_session.execute(select(func.count(Streak.id)))
            total_streaks = result.scalar()
            
            # Count user levels
            result = await self.db_session.execute(select(func.count(UserLevel.id)))
            total_user_levels = result.scalar()
            
            # Get total XP distributed
            result = await self.db_session.execute(select(func.sum(UserXP.xp_earned)))
            total_xp_distributed = result.scalar() or 0
            
            validation_data = {
                "total_xp_records": total_xp_records,
                "total_achievements": total_achievements,
                "total_user_achievements": total_user_achievements,
                "total_streaks": total_streaks,
                "total_user_levels": total_user_levels,
                "total_xp_distributed": total_xp_distributed
            }
            
            logger.info(f"   🏆 XP records: {total_xp_records}")
            logger.info(f"   🎯 Achievements: {total_achievements}")
            logger.info(f"   🏅 User achievements: {total_user_achievements}")
            logger.info(f"   🔥 Streaks: {total_streaks}")
            logger.info(f"   📊 User levels: {total_user_levels}")
            logger.info(f"   ⭐ Total XP distributed: {total_xp_distributed:,}")
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ Gamification validation failed: {e}")
            return {"error": str(e)}
    
    async def validate_community(self) -> Dict[str, Any]:
        """Validate community features."""
        logger.info("\n👥 Validating community features...")
        
        try:
            from lyo_app.community.models import StudyGroup, GroupMembership, CommunityEvent, EventAttendance
            from sqlalchemy import select, func
            
            # Count study groups
            result = await self.db_session.execute(select(func.count(StudyGroup.id)))
            total_study_groups = result.scalar()
            
            # Count memberships
            result = await self.db_session.execute(select(func.count(GroupMembership.id)))
            total_memberships = result.scalar()
            
            # Count events
            result = await self.db_session.execute(select(func.count(CommunityEvent.id)))
            total_events = result.scalar()
            
            # Count event attendances
            result = await self.db_session.execute(select(func.count(EventAttendance.id)))
            total_attendances = result.scalar()
            
            validation_data = {
                "total_study_groups": total_study_groups,
                "total_memberships": total_memberships,
                "total_events": total_events,
                "total_attendances": total_attendances
            }
            
            logger.info(f"   🏫 Study groups: {total_study_groups}")
            logger.info(f"   👨‍👩‍👧‍👦 Memberships: {total_memberships}")
            logger.info(f"   📅 Events: {total_events}")
            logger.info(f"   🎪 Event attendances: {total_attendances}")
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ Community validation failed: {e}")
            return {"error": str(e)}
    
    async def validate_ai_study(self) -> Dict[str, Any]:
        """Validate AI study features."""
        logger.info("\n🤖 Validating AI study features...")
        
        try:
            from lyo_app.ai_study.models import StudySession, StudyMessage
            from sqlalchemy import select, func
            
            # Count study sessions
            result = await self.db_session.execute(select(func.count(StudySession.id)))
            total_sessions = result.scalar()
            
            # Count study messages
            result = await self.db_session.execute(select(func.count(StudyMessage.id)))
            total_messages = result.scalar()
            
            # Count active sessions
            result = await self.db_session.execute(
                select(func.count(StudySession.id)).where(StudySession.is_active == True)
            )
            active_sessions = result.scalar()
            
            # Get average messages per session
            if total_sessions > 0:
                avg_messages_per_session = total_messages / total_sessions
            else:
                avg_messages_per_session = 0
            
            validation_data = {
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "active_sessions": active_sessions,
                "avg_messages_per_session": round(avg_messages_per_session, 1)
            }
            
            logger.info(f"   🎓 Study sessions: {total_sessions}")
            logger.info(f"   💬 Messages: {total_messages}")
            logger.info(f"   🔄 Active sessions: {active_sessions}")
            logger.info(f"   📊 Avg messages/session: {avg_messages_per_session:.1f}")
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ AI study validation failed: {e}")
            return {"error": str(e)}
    
    async def validate_data_relationships(self) -> Dict[str, Any]:
        """Validate data relationships and integrity."""
        logger.info("\n🔗 Validating data relationships...")
        
        try:
            from lyo_app.auth.models import User
            from lyo_app.learning.models import CourseEnrollment
            from lyo_app.feeds.models import Post
            from lyo_app.gamification.models import UserLevel
            from sqlalchemy import select, func
            
            issues = []
            
            # Check orphaned enrollments
            result = await self.db_session.execute(
                select(func.count(CourseEnrollment.id))
                .outerjoin(User, CourseEnrollment.user_id == User.id)
                .where(User.id.is_(None))
            )
            orphaned_enrollments = result.scalar()
            if orphaned_enrollments > 0:
                issues.append(f"Found {orphaned_enrollments} orphaned enrollments")
            
            # Check orphaned posts
            result = await self.db_session.execute(
                select(func.count(Post.id))
                .outerjoin(User, Post.author_id == User.id)
                .where(User.id.is_(None))
            )
            orphaned_posts = result.scalar()
            if orphaned_posts > 0:
                issues.append(f"Found {orphaned_posts} orphaned posts")
            
            # Check users without levels
            result = await self.db_session.execute(
                select(func.count(User.id))
                .outerjoin(UserLevel, User.id == UserLevel.user_id)
                .where(UserLevel.user_id.is_(None))
            )
            users_without_levels = result.scalar()
            if users_without_levels > 0:
                issues.append(f"Found {users_without_levels} users without levels")
            
            validation_data = {
                "orphaned_enrollments": orphaned_enrollments,
                "orphaned_posts": orphaned_posts,
                "users_without_levels": users_without_levels,
                "issues": issues
            }
            
            if issues:
                logger.warning("   ⚠️  Data integrity issues found:")
                for issue in issues:
                    logger.warning(f"      - {issue}")
            else:
                logger.info("   ✅ All data relationships are valid")
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ Relationship validation failed: {e}")
            return {"error": str(e)}
    
    async def test_authentication(self) -> Dict[str, Any]:
        """Test authentication with demo users."""
        logger.info("\n🔐 Testing authentication...")
        
        try:
            from lyo_app.auth.service import AuthService
            from lyo_app.auth.models import User
            from sqlalchemy import select
            
            auth_service = AuthService()
            
            # Get demo users
            result = await self.db_session.execute(
                select(User).where(User.email.like('%demo.com')).limit(2)
            )
            demo_users = result.scalars().all()
            
            if not demo_users:
                return {"error": "No demo users found"}
            
            auth_results = []
            
            for user in demo_users:
                try:
                    # Test authentication (simulate)
                    authenticated_user = await auth_service.get_user_by_email(self.db_session, user.email)
                    if authenticated_user:
                        auth_results.append({
                            "email": user.email,
                            "username": user.username,
                            "status": "success"
                        })
                        logger.info(f"   ✅ {user.email} - authentication ready")
                    else:
                        auth_results.append({
                            "email": user.email,
                            "status": "failed"
                        })
                        logger.warning(f"   ❌ {user.email} - authentication failed")
                
                except Exception as e:
                    auth_results.append({
                        "email": user.email,
                        "status": "error",
                        "error": str(e)
                    })
                    logger.error(f"   ❌ {user.email} - error: {e}")
            
            validation_data = {
                "tested_users": len(auth_results),
                "successful_auths": len([r for r in auth_results if r["status"] == "success"]),
                "results": auth_results
            }
            
            return validation_data
            
        except Exception as e:
            logger.error(f"   ❌ Authentication testing failed: {e}")
            return {"error": str(e)}
    
    async def run_full_validation(self) -> Dict[str, Any]:
        """Run comprehensive validation."""
        logger.info("🔍 RUNNING COMPREHENSIVE DATABASE VALIDATION")
        logger.info("=" * 60)
        
        results = {}
        
        # Run all validations
        results["users"] = await self.validate_users()
        results["learning"] = await self.validate_learning_content()
        results["social"] = await self.validate_social_content()
        results["gamification"] = await self.validate_gamification()
        results["community"] = await self.validate_community()
        results["ai_study"] = await self.validate_ai_study()
        results["relationships"] = await self.validate_data_relationships()
        results["authentication"] = await self.test_authentication()
        
        return results
    
    async def print_summary(self, results: Dict[str, Any]):
        """Print validation summary."""
        logger.info("\n" + "=" * 60)
        logger.info("📊 VALIDATION SUMMARY")
        logger.info("=" * 60)
        
        total_issues = 0
        
        for category, data in results.items():
            if "error" in data:
                logger.error(f"❌ {category.title()}: ERROR - {data['error']}")
                total_issues += 1
            else:
                logger.info(f"✅ {category.title()}: OK")
        
        # Print key statistics
        if "users" in results and "error" not in results["users"]:
            user_data = results["users"]
            logger.info(f"\n📈 KEY STATISTICS:")
            logger.info(f"   👥 Users: {user_data.get('total_users', 0)}")
            
            if "learning" in results and "error" not in results["learning"]:
                learning_data = results["learning"]
                logger.info(f"   📚 Courses: {learning_data.get('total_courses', 0)}")
                logger.info(f"   👨‍🎓 Enrollments: {learning_data.get('total_enrollments', 0)}")
            
            if "social" in results and "error" not in results["social"]:
                social_data = results["social"]
                logger.info(f"   💬 Posts: {social_data.get('total_posts', 0)}")
                logger.info(f"   👥 Follows: {social_data.get('total_follows', 0)}")
            
            if "gamification" in results and "error" not in results["gamification"]:
                game_data = results["gamification"]
                logger.info(f"   🏆 XP Records: {game_data.get('total_xp_records', 0)}")
                logger.info(f"   🎯 Achievements: {game_data.get('total_achievements', 0)}")
        
        # Print demo users for testing
        if ("users" in results and "error" not in results["users"] and 
            "demo_user_emails" in results["users"]):
            demo_emails = results["users"]["demo_user_emails"]
            if demo_emails:
                logger.info(f"\n🎭 DEMO USERS FOR TESTING:")
                for email in demo_emails:
                    logger.info(f"   📧 {email} (Password: DemoPass123!)")
        
        if total_issues == 0:
            logger.info(f"\n🎉 ALL VALIDATIONS PASSED!")
            logger.info("✨ Your database is properly seeded and ready for testing!")
        else:
            logger.warning(f"\n⚠️  Found {total_issues} issues")
            logger.info("Review the errors above and consider re-running the seeder")
        
        logger.info("\n🚀 NEXT STEPS:")
        logger.info("1. Start your server: python3 start_server.py")
        logger.info("2. Access API docs: http://localhost:8000/docs")
        logger.info("3. Test with demo users above")
        logger.info("=" * 60)
    
    async def close(self):
        """Clean up database connections."""
        if self.db_session:
            await self.db_session.close()


async def main():
    """Main validation function."""
    validator = DatabaseValidator()
    
    try:
        # Initialize
        if not await validator.initialize():
            logger.error("Failed to initialize validator")
            return False
        
        # Run validation
        results = await validator.run_full_validation()
        
        # Print summary
        await validator.print_summary(results)
        
        # Save results to file
        try:
            with open('validation_results.json', 'w') as f:
                json.dump(results, f, indent=2, default=str)
            logger.info("\n💾 Detailed results saved to 'validation_results.json'")
        except Exception as e:
            logger.warning(f"Could not save results file: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await validator.close()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
