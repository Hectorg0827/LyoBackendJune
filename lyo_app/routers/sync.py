"""
Multi-Device Sync API Routes

Endpoints for cross-device conversation continuity.
"""

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db as get_async_db
from lyo_app.auth.models import User
from lyo_app.auth.jwt_auth import get_current_user
from lyo_app.services.conversation_sync import (
    conversation_sync_service,
    DeviceType
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["Multi-Device Sync"])


# ==================== Schemas ====================

class DeviceInfo(BaseModel):
    """Information about a connected device."""
    device_id: str
    device_type: str
    device_name: Optional[str]
    connected_at: datetime
    last_activity: datetime
    is_active: bool
    is_current_session: bool


class ConversationStateResponse(BaseModel):
    """Current conversation state."""
    session_id: Optional[str]
    active_device_id: Optional[str]
    last_message_preview: Optional[str]
    last_activity: Optional[datetime]
    connected_devices: int


class RegisterDeviceRequest(BaseModel):
    """Request to register a device."""
    device_type: str = Field(..., description="Device type: mobile_ios, mobile_android, web_desktop, etc.")
    device_name: Optional[str] = Field(None, description="User-friendly device name")


class TransferSessionRequest(BaseModel):
    """Request to transfer session to this device."""
    from_device_id: Optional[str] = Field(None, description="Device to transfer from (optional)")


# ==================== REST Endpoints ====================

@router.get("/devices", response_model=List[DeviceInfo])
async def get_connected_devices(
    current_user: User = Depends(get_current_user)
):
    """
    Get all devices currently connected for this user.

    Shows which devices are online and can receive conversation updates.
    """
    try:
        devices = await conversation_sync_service.get_connected_devices(current_user.id)
        return [DeviceInfo(**d) for d in devices]

    except Exception as e:
        logger.exception(f"Failed to get devices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve connected devices"
        )


@router.get("/state", response_model=ConversationStateResponse)
async def get_conversation_state(
    current_user: User = Depends(get_current_user)
):
    """
    Get current conversation state.

    Shows the active session and which device is primary.
    """
    try:
        state = await conversation_sync_service.get_conversation_state(current_user.id)
        devices = await conversation_sync_service.get_connected_devices(current_user.id)

        if state:
            return ConversationStateResponse(
                session_id=state.get("session_id"),
                active_device_id=state.get("active_device_id"),
                last_message_preview=state.get("last_message_preview"),
                last_activity=datetime.fromisoformat(state["last_activity"]) if state.get("last_activity") else None,
                connected_devices=len(devices)
            )
        else:
            return ConversationStateResponse(
                session_id=None,
                active_device_id=None,
                last_message_preview=None,
                last_activity=None,
                connected_devices=len(devices)
            )

    except Exception as e:
        logger.exception(f"Failed to get state: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation state"
        )


@router.post("/transfer")
async def transfer_session_to_device(
    request: TransferSessionRequest,
    device_id: str = Query(..., description="Device ID to transfer to"),
    current_user: User = Depends(get_current_user)
):
    """
    Transfer the active session to a specific device.

    Use this when you want to continue the conversation on a different device.
    """
    try:
        state = await conversation_sync_service.get_conversation_state(current_user.id)
        from_device = request.from_device_id or (state.get("active_device_id") if state else None)

        await conversation_sync_service.transfer_session(
            user_id=current_user.id,
            from_device_id=from_device or "unknown",
            to_device_id=device_id
        )

        return {
            "status": "transferred",
            "to_device": device_id,
            "from_device": from_device,
            "message": "Session transferred. Continue on your new device!"
        }

    except Exception as e:
        logger.exception(f"Failed to transfer session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transfer session"
        )


# ==================== WebSocket Endpoint ====================

@router.websocket("/ws")
async def sync_websocket(
    websocket: WebSocket,
    token: str = Query(...),
    device_type: str = Query(default="unknown"),
    device_name: Optional[str] = Query(default=None)
):
    """
    WebSocket endpoint for real-time cross-device sync.

    Connect from each device to receive:
    - New messages in real-time
    - Typing indicators
    - Session transfer notifications
    - Device connect/disconnect events

    Query params:
    - token: JWT auth token
    - device_type: Type of device (mobile_ios, mobile_android, web_desktop, etc.)
    - device_name: User-friendly name for the device
    """
    await websocket.accept()

    # Validate token and get user
    try:
        from lyo_app.auth.jwt_auth import decode_token
        payload = decode_token(token)
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
        user_id = int(user_id)
    except Exception as e:
        logger.warning(f"WebSocket auth failed: {e}")
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Generate device ID
    device_id = str(uuid.uuid4())

    # Parse device type
    try:
        device_type_enum = DeviceType(device_type)
    except ValueError:
        device_type_enum = DeviceType.UNKNOWN

    try:
        # Register device
        device = await conversation_sync_service.connect_device(
            websocket=websocket,
            user_id=user_id,
            device_id=device_id,
            device_type=device_type_enum,
            device_name=device_name
        )

        # Send welcome message
        await websocket.send_json({
            "event_type": "connected",
            "device_id": device_id,
            "message": "Connected to sync service"
        })

        # Listen for messages
        while True:
            try:
                data = await websocket.receive_json()
                await handle_sync_message(user_id, device_id, data)

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning(f"Error handling message: {e}")
                await websocket.send_json({
                    "event_type": "error",
                    "message": str(e)
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
    finally:
        await conversation_sync_service.disconnect_device(websocket)


async def handle_sync_message(user_id: int, device_id: str, data: dict):
    """Handle incoming sync messages from WebSocket."""
    message_type = data.get("type")

    if message_type == "typing":
        await conversation_sync_service.sync_typing_indicator(
            user_id=user_id,
            device_id=device_id,
            is_typing=data.get("is_typing", False)
        )

    elif message_type == "heartbeat":
        # Update last activity
        if user_id in conversation_sync_service.connected_devices:
            if device_id in conversation_sync_service.connected_devices[user_id]:
                conversation_sync_service.connected_devices[user_id][device_id].last_activity = datetime.utcnow()

    elif message_type == "request_state":
        # Client requesting current state
        pass  # State is sent on connect

    else:
        logger.warning(f"Unknown message type: {message_type}")


# ==================== Health Check ====================

@router.get("/health")
async def sync_health():
    """
    Check sync service health.
    """
    redis_status = "connected" if conversation_sync_service.redis_client else "not_configured"
    total_devices = sum(
        len(devices)
        for devices in conversation_sync_service.connected_devices.values()
    )

    return {
        "status": "healthy",
        "redis": redis_status,
        "connected_devices": total_devices,
        "active_users": len(conversation_sync_service.connected_devices)
    }
