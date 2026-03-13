"""
Push Notification Service
Handles push notifications for iOS (APNs) and Android (FCM)
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.models.production import PushDevice, PushPlatform
from lyo_app.core.database import AsyncSessionLocal
from datetime import datetime

@dataclass
class PushNotification:
    """Push notification data structure"""
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    badge: Optional[int] = None
    sound: Optional[str] = "default"

class PushNotificationService:
    """Push notification service with database awareness and multi-platform support."""
    
    def __init__(self):
        self.initialized = True  # Ready to accept requests
        
    async def initialize(self):
        """Initialize external SDKs (FCM, APNs)"""
        # In production, initialize firebase_admin and APNs client here
        logger.info("Push notification service initialized")
    
    async def send_to_user(self, user_id: int, notification: PushNotification, db: Optional[AsyncSession] = None) -> int:
        """Fetch active devices for user and send notifications."""
        async_db = db or AsyncSessionLocal()
        close_db = db is None
        
        try:
            # Query active devices
            stmt = select(PushDevice).where(
                PushDevice.user_id == user_id,
                PushDevice.is_active == True
            )
            result = await async_db.execute(stmt)
            devices = result.scalars().all()
            
            if not devices:
                logger.info(f"No active push devices found for user {user_id}")
                return 0
                
            sent_count = 0
            for device in devices:
                success = await self.send_notification(
                    device_token=device.device_token,
                    notification=notification,
                    platform=device.platform.value if hasattr(device.platform, 'value') else device.platform
                )
                if success:
                    device.last_used_at = datetime.utcnow()
                    sent_count += 1
            
            await async_db.commit()
            logger.info(f"Sent {sent_count} notifications to user {user_id}")
            return sent_count
            
        except Exception as e:
            logger.error(f"Failed to send notifications to user {user_id}: {e}")
            return 0
        finally:
            if close_db:
                await async_db.close()

    async def send_notification(self, device_token: str, notification: PushNotification, platform: str = "ios") -> bool:
        """Low-level dispatch to FCM or APNs."""
        try:
            logger.info(f"Dispatching to {platform}: {device_token[:10]}... | {notification.title}")
            
            # TODO: Integrate with actual FCM (firebase-admin) or APNs (HTTP/2)
            # if platform == "ios":
            #     return await self._dispatch_apns(device_token, notification)
            # else:
            #     return await self._dispatch_fcm(device_token, notification)
            
            return True
            
        except Exception as e:
            logger.error(f"Dispatch error: {e}")
            return False

# Global push service instance
push_service = PushNotificationService()

async def initialize_push_service():
    """Initialize the global push service"""
    await push_service.initialize()
