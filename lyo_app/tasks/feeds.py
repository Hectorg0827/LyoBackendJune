"""
Feed management tasks.
Handles community feed updates and content curation.
"""

import logging
from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime, timedelta

from celery import current_task
from sqlalchemy.orm import Session
from sqlalchemy import desc

from lyo_app.core.celery_app import celery_app
from lyo_app.tasks.course_generation import get_sync_db
from lyo_app.auth.models import User
from lyo_app.models.production import FeedItem, UserProfile, FeedItemType

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def create_feed_item_task(
    self,
    user_id: Optional[str],
    item_type: str,
    title: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
    image_url: Optional[str] = None,
    link_url: Optional[str] = None,
    is_public: bool = True,
    is_featured: bool = False
):
    """
    Create a new feed item.
    """
    db = get_sync_db()
    
    try:
        # Calculate priority score based on type and metadata
        priority_score = calculate_priority_score(item_type, metadata)
        
        # Create feed item
        feed_item = FeedItem(
            user_id=uuid.UUID(user_id) if user_id else None,
            type=item_type,
            title=title,
            content=content,
            metadata=metadata or {},
            image_url=image_url,
            link_url=link_url,
            is_public=is_public,
            is_featured=is_featured,
            priority_score=priority_score
        )
        
        db.add(feed_item)
        db.commit()
        
        logger.info(f"Created feed item: {title} (type: {item_type})")
        
        # Update user engagement if applicable
        if user_id:
            update_user_engagement_task.delay(user_id, "feed_post_created")
        
        return str(feed_item.id)
        
    except Exception as e:
        logger.exception(f"Failed to create feed item")
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True)
def update_feed_task(self, user_id: str, action: str, details: Dict[str, Any]):
    """
    Update user's feed based on actions.
    """
    db = get_sync_db()
    
    try:
        if action == "course_completed":
            course_id = details.get("course_id")
            course_title = details.get("course_title", "Unknown Course")
            
            # Create achievement feed item
            create_feed_item_task.delay(
                user_id=user_id,
                item_type=FeedItemType.ACHIEVEMENT.value,
                title="Course Completed! 🎓",
                content=f"Just finished '{course_title}' and gained valuable knowledge!",
                metadata={
                    "achievement_type": "course_completion",
                    "course_id": course_id,
                    "course_title": course_title,
                    "completion_date": datetime.utcnow().isoformat()
                },
                is_public=True
            )
        
        elif action == "milestone_reached":
            milestone_type = details.get("milestone_type")
            milestone_value = details.get("milestone_value")
            
            # Create milestone feed item
            create_feed_item_task.delay(
                user_id=user_id,
                item_type=FeedItemType.MILESTONE.value,
                title=f"Milestone Achieved! 🏆",
                content=f"Reached {milestone_value} {milestone_type}!",
                metadata={
                    "milestone_type": milestone_type,
                    "milestone_value": milestone_value,
                    "achievement_date": datetime.utcnow().isoformat()
                },
                is_public=True,
                is_featured=True  # Milestones are featured
            )
        
        elif action == "streak_milestone":
            streak_days = details.get("streak_days")
            
            if streak_days >= 7:  # Weekly milestones
                create_feed_item_task.delay(
                    user_id=user_id,
                    item_type=FeedItemType.MILESTONE.value,
                    title=f"{streak_days}-Day Streak! 🔥",
                    content=f"Maintained a {streak_days}-day learning streak!",
                    metadata={
                        "milestone_type": "streak",
                        "streak_days": streak_days,
                        "achievement_date": datetime.utcnow().isoformat()
                    },
                    is_public=True,
                    is_featured=streak_days >= 30  # Month+ streaks are featured
                )
        
        logger.info(f"Updated feed for user {user_id} with action: {action}")
        
    except Exception as e:
        logger.exception(f"Failed to update feed for user {user_id}")
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True) 
def update_user_engagement_task(self, user_id: str, action: str):
    """
    Update user engagement metrics and trigger achievements.
    """
    db = get_sync_db()
    
    try:
        user_profile = db.query(UserProfile).filter(
            UserProfile.user_id == uuid.UUID(user_id)
        ).first()
        
        if not user_profile:
            logger.warning(f"No user profile found for user {user_id}")
            return
        
        # Update engagement metrics
        if action == "course_completed":
            user_profile.courses_completed += 1
            
            # Check for milestones
            if user_profile.courses_completed in [5, 10, 25, 50, 100]:
                update_feed_task.delay(
                    user_id=user_id,
                    action="milestone_reached",
                    details={
                        "milestone_type": "courses_completed",
                        "milestone_value": user_profile.courses_completed
                    }
                )
        
        elif action == "lesson_completed":
            user_profile.lessons_completed += 1
            
            # Check for lesson milestones
            if user_profile.lessons_completed % 50 == 0:  # Every 50 lessons
                update_feed_task.delay(
                    user_id=user_id,
                    action="milestone_reached",
                    details={
                        "milestone_type": "lessons_completed",
                        "milestone_value": user_profile.lessons_completed
                    }
                )
        
        elif action == "daily_activity":
            # Update streak
            today = datetime.utcnow().date()
            
            if user_profile.last_activity_date == today - timedelta(days=1):
                # Continuing streak
                user_profile.current_streak += 1
                
                # Update longest streak if needed
                if user_profile.current_streak > user_profile.longest_streak:
                    user_profile.longest_streak = user_profile.current_streak
                
                # Check for streak milestones
                if user_profile.current_streak % 7 == 0:  # Weekly streaks
                    update_feed_task.delay(
                        user_id=user_id,
                        action="streak_milestone",
                        details={"streak_days": user_profile.current_streak}
                    )
            
            elif user_profile.last_activity_date != today:
                # New streak or broken streak
                user_profile.current_streak = 1
            
            user_profile.last_activity_date = today
        
        elif action == "study_time":
            # Would be called with actual study time
            pass
        
        db.commit()
        logger.info(f"Updated engagement for user {user_id}: {action}")
        
    except Exception as e:
        logger.exception(f"Failed to update user engagement")
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True)
def curate_personalized_feed_task(self, user_id: str):
    """
    Generate personalized feed recommendations for user.
    """
    db = get_sync_db()
    
    try:
        user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
        if not user:
            return
        
        user_profile = db.query(UserProfile).filter(
            UserProfile.user_id == uuid.UUID(user_id)
        ).first()
        
        # Generate recommendation based on user's interests and progress
        recommendations = generate_recommendations(user, user_profile, db)
        
        for rec in recommendations:
            create_feed_item_task.delay(
                user_id=None,  # System-generated
                item_type=FeedItemType.RECOMMENDATION.value,
                title=rec["title"],
                content=rec["content"],
                metadata={
                    "recommendation_type": rec["type"],
                    "target_user": user_id,
                    "relevance_score": rec["score"],
                    **rec.get("metadata", {})
                },
                is_public=False  # Personalized recommendations are private
            )
        
        logger.info(f"Generated {len(recommendations)} recommendations for user {user_id}")
        
    except Exception as e:
        logger.exception(f"Failed to curate personalized feed")
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True)
def cleanup_old_feed_items_task(self, days_old: int = 90):
    """
    Clean up old feed items to manage database size.
    """
    db = get_sync_db()
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        # Delete old non-featured items
        old_items = db.query(FeedItem).filter(
            FeedItem.created_at < cutoff_date,
            FeedItem.is_featured == False,
            FeedItem.like_count < 5  # Keep popular items longer
        ).all()
        
        for item in old_items:
            db.delete(item)
        
        db.commit()
        
        logger.info(f"Cleaned up {len(old_items)} old feed items")
        
    except Exception as e:
        logger.exception("Failed to cleanup old feed items")
        raise
    
    finally:
        db.close()


def calculate_priority_score(item_type: str, metadata: Optional[Dict[str, Any]]) -> float:
    """Calculate priority score for feed item ranking."""
    
    base_scores = {
        FeedItemType.ACHIEVEMENT.value: 0.8,
        FeedItemType.MILESTONE.value: 0.9,
        FeedItemType.COURSE_COMPLETION.value: 0.7,
        FeedItemType.COMMUNITY_POST.value: 0.5,
        FeedItemType.RECOMMENDATION.value: 0.6
    }
    
    score = base_scores.get(item_type, 0.5)
    
    # Boost score based on metadata
    if metadata:
        if metadata.get("is_featured"):
            score += 0.2
        
        if metadata.get("achievement_type") == "course_completion":
            score += 0.1
        
        if "milestone" in item_type and metadata.get("milestone_value", 0) >= 50:
            score += 0.15
    
    return min(score, 1.0)


def generate_recommendations(user: User, profile: UserProfile, db: Session) -> List[Dict[str, Any]]:
    """Generate personalized recommendations for user."""
    
    recommendations = []
    
    # Course completion recommendations
    if profile.courses_completed < 3:
        recommendations.append({
            "type": "course_suggestion",
            "title": "Ready for Your Next Challenge?",
            "content": "Based on your progress, here are some courses that might interest you!",
            "score": 0.8,
            "metadata": {"suggestion_type": "next_course"}
        })
    
    # Streak encouragement
    if profile.current_streak > 0 and profile.current_streak < 7:
        recommendations.append({
            "type": "streak_encouragement", 
            "title": f"Keep Your {profile.current_streak}-Day Streak Going!",
            "content": "You're doing great! Complete a lesson today to maintain your streak.",
            "score": 0.9,
            "metadata": {"current_streak": profile.current_streak}
        })
    
    # Study time suggestions
    recommendations.append({
        "type": "study_tip",
        "title": "💡 Learning Tip of the Day",
        "content": "Try the Pomodoro Technique: 25 minutes of focused study, then a 5-minute break!",
        "score": 0.6,
        "metadata": {"tip_category": "study_method"}
    })
    
    return recommendations
