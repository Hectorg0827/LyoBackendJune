"""
Push notification tasks.
Handles APNs delivery and device management.
"""

import logging
from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime

from celery import current_task
from sqlalchemy.orm import Session

from lyo_app.core.celery_app import celery_app
from lyo_app.tasks.course_generation import get_sync_db
from lyo_app.models.production import PushDevice, Course

logger = logging.getLogger(__name__)


class APNsService:
    """Apple Push Notifications service."""
    
    def __init__(self):
        self.client = None
        self._initialize()
    
    def _initialize(self):
        """Initialize APNs client."""
        try:
            # TODO: Initialize actual APNs client
            # from aioapns import APNs, NotificationRequest, PushType
            # 
            # self.client = APNs(
            #     key=settings.APNS_PRIVATE_KEY_PATH,
            #     key_id=settings.APNS_KEY_ID,
            #     team_id=settings.APNS_TEAM_ID,
            #     topic=settings.APNS_BUNDLE_ID,
            #     use_sandbox=settings.APNS_USE_SANDBOX
            # )
            
            logger.info("APNs service initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize APNs service: {e}")
    
    async def send_notification(
        self,
        device_token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send push notification to device."""
        
        if not self.client:
            logger.warning("APNs client not available")
            return False
        
        try:
            # TODO: Send actual push notification
            # notification = NotificationRequest(
            #     device_token=device_token,
            #     message={
            #         "aps": {
            #             "alert": {
            #                 "title": title,
            #                 "body": body
            #             },
            #             "sound": "default",
            #             "badge": 1
            #         },
            #         **(data or {})
            #     }
            # )
            # 
            # response = await self.client.send_notification(notification)
            # return response.is_successful
            
            # Simulate successful notification for now
            logger.info(f"Sent notification to {device_token[:10]}...: {title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")
            return False


# Global APNs service
apns_service = APNsService()


@celery_app.task(bind=True)
def send_push_notification_task(
    self,
    user_id: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None
):
    """
    Send push notification to all user devices using PushNotificationService.
    """
    from lyo_app.services.push_notifications import push_service, PushNotification
    import asyncio

    # Helper to run async in sync Celery (copied from proactive_engagement.py if needed, 
    # or just use a simple local loop here)
    def run_async(coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    try:
        notification = PushNotification(
            title=title,
            message=body,
            data=data
        )
        
        # User ID is passed as string from dispatcher, convert to int for service if needed
        # (Assuming the service expects int based on earlier implementation)
        try:
            u_id = int(user_id)
        except ValueError:
            # Maybe it's a UUID? Check if we can handle it
            u_id = str(user_id) 

        sent_count = run_async(push_service.send_to_user(u_id, notification))
        
        logger.info(f"Task sent {sent_count} notifications to user {user_id}")
        return {"status": "success", "sent_count": sent_count}
        
    except Exception as e:
        logger.exception(f"Failed to send push notifications for user {user_id}")
        raise self.retry(exc=e, countdown=60, max_retries=3)


@celery_app.task(bind=True)
def notify_course_ready_task(self, user_id: str, course_id: str):
    """
    Notify user that their course is ready.
    """
    db = get_sync_db()
    
    try:
        # Get course details
        course = db.query(Course).filter(Course.id == uuid.UUID(course_id)).first()
        if not course:
            logger.error(f"Course {course_id} not found")
            return
        
        # Send push notification
        send_push_notification_task.delay(
            user_id=user_id,
            title="Your Course is Ready! 🎉",
            body=f"'{course.title}' is now available for learning",
            data={
                "type": "course_ready",
                "course_id": course_id,
                "action": "open_course"
            }
        )
        
        # Create feed item
        from lyo_app.tasks.feeds import create_feed_item_task
        create_feed_item_task.delay(
            user_id=user_id,
            item_type="course_completion",
            title=f"Course Generated: {course.title}",
            content=f"Your personalized course on {course.topic} is ready!",
            metadata={
                "course_id": course_id,
                "course_title": course.title,
                "course_topic": course.topic,
                "total_items": course.total_items
            }
        )
        
        logger.info(f"Sent course ready notification for course {course_id}")
        
    except Exception as e:
        logger.exception(f"Failed to send course ready notification")
        raise
    
    finally:
        db.close()


@celery_app.task(bind=True)
def cleanup_inactive_devices_task(self, days_inactive: int = 30):
    """
    Clean up push devices that haven't been used in specified days.
    """
    db = get_sync_db()
    
    try:
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days_inactive)
        
        # Mark old devices as inactive
        inactive_devices = db.query(PushDevice).filter(
            PushDevice.last_used < cutoff_date,
            PushDevice.active == True
        ).all()
        
        for device in inactive_devices:
            device.active = False
        
        db.commit()
        
        logger.info(f"Marked {len(inactive_devices)} devices as inactive")
        
    except Exception as e:
        logger.exception("Failed to cleanup inactive devices")
        raise
    
    finally:
        db.close()
