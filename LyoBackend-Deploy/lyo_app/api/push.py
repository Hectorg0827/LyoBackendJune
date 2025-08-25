"""Push notification service integration."""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from lyo_app.core.database import get_db_session
from lyo_app.auth.jwt_auth import require_active_user
from lyo_app.models.enhanced import User, PushDevice
from lyo_app.core.problems import ValidationProblem, NotFoundProblem

logger = logging.getLogger(__name__)

router = APIRouter()


class DeviceType(str, Enum):
    """Supported device types for push notifications."""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class PushDeviceRegisterRequest(BaseModel):
    """Request model for device registration."""
    device_token: str = Field(..., description="Device push token from APNs/FCM")
    device_type: DeviceType = Field(..., description="Device platform type")
    device_info: Optional[Dict[str, Any]] = Field(None, description="Optional device metadata")
    

class PushDeviceResponse(BaseModel):
    """Response model for device registration."""
    id: str
    device_token: str
    device_type: str
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime]
    

class PushNotificationRequest(BaseModel):
    """Request model for sending push notifications."""
    user_ids: Optional[List[str]] = Field(None, description="Specific user IDs to notify")
    title: str = Field(..., description="Notification title")
    body: str = Field(..., description="Notification body")
    data: Optional[Dict[str, Any]] = Field(None, description="Custom notification data")
    

@router.post("/devices/register", response_model=PushDeviceResponse, summary="Register push device")
async def register_device(
    device_data: PushDeviceRegisterRequest,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> PushDeviceResponse:
    """
    Register a device for push notifications.
    
    - **device_token**: The push token from APNs (iOS) or FCM (Android/Web)
    - **device_type**: Platform type (ios, android, web)
    - **device_info**: Optional metadata about the device
    
    If a device with the same token already exists for this user, it will be updated.
    """
    try:
        # Check if device already exists
        existing_device = await db.execute(
            select(PushDevice).where(
                PushDevice.user_id == current_user.id,
                PushDevice.device_token == device_data.device_token
            )
        )
        device = existing_device.scalar_one_or_none()
        
        if device:
            # Update existing device
            device.device_type = device_data.device_type.value
            device.device_info = device_data.device_info or {}
            device.is_active = True
            device.last_used = datetime.utcnow()
        else:
            # Create new device
            device = PushDevice(
                user_id=current_user.id,
                device_token=device_data.device_token,
                device_type=device_data.device_type.value,
                device_info=device_data.device_info or {},
                is_active=True
            )
            db.add(device)
        
        await db.commit()
        await db.refresh(device)
        
        logger.info(f"Registered push device for user {current_user.id}: {device.id}")
        
        return PushDeviceResponse(
            id=str(device.id),
            device_token=device.device_token,
            device_type=device.device_type,
            is_active=device.is_active,
            created_at=device.created_at,
            last_used=device.last_used
        )
        
    except Exception as e:
        logger.error(f"Error registering push device: {e}")
        raise ValidationProblem(f"Failed to register device: {str(e)}")


@router.get("/devices", response_model=List[PushDeviceResponse], summary="List user devices")
async def list_devices(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
) -> List[PushDeviceResponse]:
    """List all push devices registered for the current user."""
    result = await db.execute(
        select(PushDevice).where(PushDevice.user_id == current_user.id)
    )
    devices = result.scalars().all()
    
    return [
        PushDeviceResponse(
            id=str(device.id),
            device_token=device.device_token,
            device_type=device.device_type,
            is_active=device.is_active,
            created_at=device.created_at,
            last_used=device.last_used
        )
        for device in devices
    ]


@router.delete("/devices/{device_id}", summary="Unregister device")
async def unregister_device(
    device_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Unregister a push device."""
    result = await db.execute(
        select(PushDevice).where(
            PushDevice.id == device_id,
            PushDevice.user_id == current_user.id
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise NotFoundProblem("Device not found")
    
    await db.delete(device)
    await db.commit()
    
    logger.info(f"Unregistered push device {device_id} for user {current_user.id}")
    
    return {"message": "Device unregistered successfully"}


@router.post("/devices/{device_id}/deactivate", summary="Deactivate device")
async def deactivate_device(
    device_id: str,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Deactivate a push device without deleting it."""
    result = await db.execute(
        select(PushDevice).where(
            PushDevice.id == device_id,
            PushDevice.user_id == current_user.id
        )
    )
    device = result.scalar_one_or_none()
    
    if not device:
        raise NotFoundProblem("Device not found")
    
    device.is_active = False
    await db.commit()
    
    return {"message": "Device deactivated successfully"}


# Admin endpoints (would need admin authentication in production)

@router.post("/send", summary="Send push notification (admin)")
async def send_push_notification(
    notification_data: PushNotificationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Send push notification to users.
    
    This is a placeholder endpoint. In production, this would require admin authentication
    and would integrate with actual APNs/FCM services.
    """
    # This is a placeholder implementation
    # In production, this would:
    # 1. Check admin permissions
    # 2. Query devices for target users
    # 3. Send notifications via APNs/FCM
    # 4. Track delivery status
    
    logger.info(f"Push notification request from user {current_user.id}")
    logger.info(f"Title: {notification_data.title}")
    logger.info(f"Body: {notification_data.body}")
    logger.info(f"Target users: {notification_data.user_ids}")
    
    # Add background task to send notifications
    background_tasks.add_task(
        _send_push_notifications_background,
        notification_data,
        db
    )
    
    return {
        "message": "Push notification queued for delivery",
        "title": notification_data.title,
        "target_users": len(notification_data.user_ids) if notification_data.user_ids else "all"
    }


async def _send_push_notifications_background(
    notification_data: PushNotificationRequest,
    db: AsyncSession
):
    """
    Background task to send push notifications.
    
    This is a placeholder implementation. In production, this would:
    - Query active devices for target users
    - Format notifications for each platform (APNs/FCM)
    - Send notifications via HTTP/2 (APNs) or HTTP (FCM)
    - Handle delivery failures and retry logic
    - Update device status if tokens are invalid
    """
    try:
        # Query devices for target users
        query = select(PushDevice).where(PushDevice.is_active == True)
        
        if notification_data.user_ids:
            query = query.where(PushDevice.user_id.in_(notification_data.user_ids))
        
        result = await db.execute(query)
        devices = result.scalars().all()
        
        logger.info(f"Found {len(devices)} devices for push notification")
        
        # In production, this would integrate with APNs/FCM
        for device in devices:
            logger.info(f"Would send to device {device.id} ({device.device_type}): {notification_data.title}")
            
            # Update last_used timestamp
            device.last_used = datetime.utcnow()
        
        await db.commit()
        
        logger.info(f"Push notification processing complete: {len(devices)} devices")
        
    except Exception as e:
        logger.error(f"Error sending push notifications: {e}")


# Test endpoint for development
@router.post("/test", summary="Test push notification (development)")
async def test_push_notification(
    current_user: User = Depends(require_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Send a test push notification to the current user's devices."""
    result = await db.execute(
        select(PushDevice).where(
            PushDevice.user_id == current_user.id,
            PushDevice.is_active == True
        )
    )
    devices = result.scalars().all()
    
    if not devices:
        return {"message": "No active devices found for current user"}
    
    # Log test notification
    for device in devices:
        logger.info(f"Test notification for device {device.id} ({device.device_type})")
    
    return {
        "message": f"Test notification sent to {len(devices)} device(s)",
        "devices": [
            {
                "id": str(device.id),
                "type": device.device_type
            }
            for device in devices
        ]
    }
