"""
Production models proxy - Redirects to enhanced models to avoid redundancy.
"""
from lyo_app.core.database import Base
from lyo_app.models.enhanced import (
    Course, Lesson, ContentItem as CourseItem, Task, 
    PushDevice, GamificationProfile as UserProfile, Badge,
    CourseStatus, TaskState, ContentType
)
from lyo_app.feeds.models import FeedItem, FeedItemType
# Note: User is imported from auth models in enhanced.py
from lyo_app.auth.models import User

# Add any missing models or aliases expected by legacy code
__all__ = [
    "Base", "User", "Course", "Lesson", "CourseItem", "Task", 
    "PushDevice", "UserProfile", "Badge", "FeedItem",
    "CourseStatus", "TaskState", "ContentType", "FeedItemType"
]
