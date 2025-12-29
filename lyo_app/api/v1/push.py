"""
Production push notifications API routes.
Device registration and notification management.
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from lyo_app.core.database import get_db
from lyo_app.auth.models import User
from lyo_app.models.production import PushDevice
from lyo_app.auth.production import require_user
from lyo_app.tasks.push_notifications import send_push_notification

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models
class DeviceRegistrationRequest(BaseModel):
    device_token: str = Field(..., min_length=1)
    device_type: str = Field(..., pattern="^(ios|android)$")
    app_version: str = Field(None, max_length=20)
    os_version: str = Field(None, max_length=20)


class PushDeviceResponse(BaseModel):
    id: str
    device_token: str
    device_type: str
    app_version: str = None
    os_version: str = None
    is_active: bool
    registered_at: str
    
    model_config = {
        "from_attributes": True
    }


class PushNotificationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=1, max_length=200)
    data: Dict[str, Any] = Field(default_factory=dict)
    badge_count: int = Field(None, ge=0)
    sound: str = Field("default")


class NotificationPreferencesRequest(BaseModel):
    course_reminders: bool = True
    achievement_notifications: bool = True
    feed_updates: bool = True
    marketing_notifications: bool = False
    quiet_hours_start: str = Field(None, pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    quiet_hours_end: str = Field(None, pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]$")
    timezone: str = Field("UTC", max_length=50)


class NotificationPreferencesResponse(BaseModel):
    course_reminders: bool = True
    achievement_notifications: bool = True
    feed_updates: bool = True
    marketing_notifications: bool = False
    quiet_hours_start: str = None
    quiet_hours_end: str = None
    timezone: str = "UTC"


@router.post("/devices/register", response_model=PushDeviceResponse)
async def register_device(
    request: DeviceRegistrationRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Register a device for push notifications.
    """
    try:
        # Check if device already exists
        query = select(PushDevice).where(
            PushDevice.user_id == current_user.id,
            PushDevice.device_token == request.device_token
        )
        
        result = await db.execute(query)
        existing_device = result.scalar_one_or_none()
        
        if existing_device:
            # Update existing device
            existing_device.device_type = request.device_type
            existing_device.app_version = request.app_version
            existing_device.os_version = request.os_version
            existing_device.is_active = True
            
            await db.commit()
            await db.refresh(existing_device)
            
            device = existing_device
            logger.info(f"Updated device registration for user: {current_user.email}")
            
        else:
            # Create new device registration
            device = PushDevice(
                user_id=current_user.id,
                device_token=request.device_token,
                device_type=request.device_type,
                app_version=request.app_version,
                os_version=request.os_version
            )
            
            db.add(device)
            await db.commit()
            await db.refresh(device)
            
            logger.info(f"New device registered for user: {current_user.email}")
        
        return PushDeviceResponse(
            id=str(device.id),
            device_token=device.device_token,
            device_type=device.device_type,
            app_version=device.app_version,
            os_version=device.os_version,
            is_active=device.is_active,
            registered_at=device.registered_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Device registration error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Device registration failed")


@router.get("/devices", response_model=List[PushDeviceResponse])
async def list_user_devices(
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List user's registered devices.
    """
    try:
        query = select(PushDevice).where(
            PushDevice.user_id == current_user.id
        ).order_by(PushDevice.registered_at.desc())
        
        result = await db.execute(query)
        devices = result.scalars().all()
        
        device_responses = []
        for device in devices:
            device_responses.append(PushDeviceResponse(
                id=str(device.id),
                device_token=device.device_token,
                device_type=device.device_type,
                app_version=device.app_version,
                os_version=device.os_version,
                is_active=device.is_active,
                registered_at=device.registered_at.isoformat()
            ))
        
        return device_responses
        
    except Exception as e:
        logger.error(f"Device listing error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list devices")


@router.delete("/devices/{device_id}")
async def unregister_device(
    device_id: UUID,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Unregister a device.
    """
    try:
        query = select(PushDevice).where(
            PushDevice.id == device_id,
            PushDevice.user_id == current_user.id
        )
        
        result = await db.execute(query)
        device = result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Mark as inactive instead of deleting
        device.is_active = False
        await db.commit()
        
        logger.info(f"Device unregistered for user: {current_user.email}")
        
        return {"message": "Device unregistered successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Device unregistration error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Device unregistration failed")


@router.post("/test")
async def send_test_notification(
    request: PushNotificationRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send a test push notification to user's devices.
    """
    try:
        # Get user's active devices
        query = select(PushDevice).where(
            PushDevice.user_id == current_user.id,
            PushDevice.is_active == True
        )
        
        result = await db.execute(query)
        devices = result.scalars().all()
        
        if not devices:
            raise HTTPException(status_code=400, detail="No active devices found")
        
        # Send test notification
        for device in devices:
            send_push_notification.delay(
                user_id=str(current_user.id),
                title=request.title,
                body=request.body,
                data=request.data,
                badge_count=request.badge_count,
                sound=request.sound,
                device_token=device.device_token,
                device_type=device.device_type
            )
        
        logger.info(f"Test notification sent to {len(devices)} devices for user: {current_user.email}")
        
        return {
            "message": f"Test notification sent to {len(devices)} devices",
            "devices_count": len(devices)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test notification error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test notification")


@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_notification_preferences(
    current_user: User = Depends(require_user)
):
    """
    Get user's notification preferences.
    """
    try:
        # Get preferences from user profile or return defaults
        preferences = getattr(current_user, 'notification_preferences', {})
        
        return NotificationPreferencesResponse(
            course_reminders=preferences.get('course_reminders', True),
            achievement_notifications=preferences.get('achievement_notifications', True),
            feed_updates=preferences.get('feed_updates', True),
            marketing_notifications=preferences.get('marketing_notifications', False),
            quiet_hours_start=preferences.get('quiet_hours_start'),
            quiet_hours_end=preferences.get('quiet_hours_end'),
            timezone=preferences.get('timezone', 'UTC')
        )
        
    except Exception as e:
        logger.error(f"Get preferences error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get preferences")


@router.put("/preferences", response_model=NotificationPreferencesResponse)
async def update_notification_preferences(
    request: NotificationPreferencesRequest,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update user's notification preferences.
    """
    try:
        # Update user's notification preferences
        preferences = {
            'course_reminders': request.course_reminders,
            'achievement_notifications': request.achievement_notifications,
            'feed_updates': request.feed_updates,
            'marketing_notifications': request.marketing_notifications,
            'quiet_hours_start': request.quiet_hours_start,
            'quiet_hours_end': request.quiet_hours_end,
            'timezone': request.timezone
        }
        
        # Store in user metadata or profile
        if not current_user.metadata:
            current_user.metadata = {}
        current_user.metadata['notification_preferences'] = preferences
        
        await db.commit()
        
        logger.info(f"Notification preferences updated for user: {current_user.email}")
        
        return NotificationPreferencesResponse(**preferences)
        
    except Exception as e:
        logger.error(f"Update preferences error: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update preferences")
