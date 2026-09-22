"""
Push Notification Service
Handles push notifications for iOS (APNs) and Android (FCM)
"""

import logging
import asyncio
import os
import time
from pathlib import Path
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
                    notification=PushNotification(notification.title, notification.message,
                        {**(notification.data or {}), "recipient_id": str(user_id)}, notification.badge, notification.sound),
                    platform=device.platform.value if hasattr(device.platform, 'value') else device.platform
                )
                if success:
                    device.last_used_at = datetime.utcnow()
                    sent_count += 1
            
            # The reminder worker owns its transaction and row locks.
            if close_db:
                await async_db.commit()
            else:
                await async_db.flush()
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
            if platform == "ios":
                return await self._dispatch_apns(device_token, notification)
            if platform in {"android", "web"}:
                return await self._dispatch_fcm(device_token, notification)
            return False
            
        except Exception as e:
            logger.error(f"Dispatch error: {e}")
            return False

    async def _dispatch_fcm(self, token: str, notification: PushNotification) -> bool:
        from firebase_admin import messaging
        from lyo_app.auth.firebase_utils import _init_firebase
        await asyncio.to_thread(_init_firebase)
        data = {str(k): str(v) for k, v in (notification.data or {}).items()}
        # Data messages let Android suppress account-bound reminders after logout.
        data.update(title=notification.title, body=notification.message)
        message = messaging.Message(token=token, data=data,
            android=messaging.AndroidConfig(priority="high", collapse_key=data.get("reminder_id")))
        result = await asyncio.to_thread(messaging.send, message)
        return bool(result)

    async def _dispatch_apns(self, token: str, notification: PushNotification) -> bool:
        import httpx
        from jose import jwt
        key = os.getenv("APNS_PRIVATE_KEY")
        key_file = os.getenv("APNS_KEY_FILE") or os.getenv("APNS_KEY_PATH")
        if not key and key_file:
            key = await asyncio.to_thread(Path(key_file).read_text)
        key_id, team_id, bundle_id = (os.getenv(k) for k in ("APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID"))
        if not all((key, key_id, team_id, bundle_id)):
            logger.warning("APNs credentials incomplete; notification was not sent")
            return False
        auth = jwt.encode({"iss": team_id, "iat": int(time.time())}, key,
            algorithm="ES256", headers={"kid": key_id})
        host = "api.sandbox.push.apple.com" if os.getenv("APNS_SANDBOX", "false").lower() == "true" else "api.push.apple.com"
        data = dict(notification.data or {})
        headers = {"authorization": f"bearer {auth}", "apns-topic": bundle_id,
                   "apns-push-type": "alert", "apns-priority": "10",
                   "apns-expiration": str(int(time.time()) + 3600)}
        if data.get("reminder_id"):
            headers["apns-collapse-id"] = str(data["reminder_id"])
        payload = {**data, "aps": {"alert": {"title": notification.title, "body": notification.message},
                    "sound": notification.sound or "default"}}
        async with httpx.AsyncClient(http2=True, timeout=15) as client:
            response = await client.post(f"https://{host}/3/device/{token}", headers=headers, json=payload)
        if response.status_code != 200:
            logger.warning("APNs rejected a notification: HTTP %s", response.status_code)
        return response.status_code == 200

# Global push service instance
push_service = PushNotificationService()

async def initialize_push_service():
    """Initialize the global push service"""
    await push_service.initialize()
