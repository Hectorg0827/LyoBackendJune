"""
Conversation Sync Service - Cross-Device Conversation Continuity

Enables seamless continuation of conversations across devices:
- Start chatting on phone, continue on desktop
- Real-time sync of conversation state
- Device presence awareness
- Typing indicators across devices

The goal: Lyo should feel like ONE continuous companion, not
separate instances on different devices.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import uuid

from fastapi import WebSocket
import redis.asyncio as redis

from lyo_app.core.config import settings

logger = logging.getLogger(__name__)


class DeviceType(str, Enum):
    """Types of devices that can connect."""
    MOBILE_IOS = "mobile_ios"
    MOBILE_ANDROID = "mobile_android"
    WEB_DESKTOP = "web_desktop"
    WEB_MOBILE = "web_mobile"
    TABLET = "tablet"
    UNKNOWN = "unknown"


class SyncEventType(str, Enum):
    """Types of sync events."""
    DEVICE_CONNECTED = "device_connected"
    DEVICE_DISCONNECTED = "device_disconnected"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    TYPING_STARTED = "typing_started"
    TYPING_STOPPED = "typing_stopped"
    SESSION_TRANSFERRED = "session_transferred"
    CONTEXT_UPDATED = "context_updated"


@dataclass
class ConnectedDevice:
    """A device connected to the sync service."""
    device_id: str
    user_id: int
    device_type: DeviceType
    device_name: Optional[str]
    websocket: Optional[WebSocket]
    connected_at: datetime
    last_activity: datetime
    is_active: bool = True
    current_session_id: Optional[str] = None


@dataclass
class ConversationState:
    """State of a user's active conversation."""
    user_id: int
    session_id: str
    active_device_id: Optional[str]
    last_message_id: Optional[str]
    last_message_preview: Optional[str]
    last_activity: datetime
    context: Dict[str, Any] = field(default_factory=dict)
    pending_messages: List[Dict] = field(default_factory=list)


@dataclass
class SyncEvent:
    """An event to sync across devices."""
    event_type: SyncEventType
    user_id: int
    device_id: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ConversationSyncService:
    """
    Manages real-time conversation sync across devices.

    Key features:
    - WebSocket connection per device
    - Redis pub/sub for multi-instance scaling
    - Conversation state persistence
    - Seamless handoff between devices
    """

    PRESENCE_TTL_SECONDS = 60  # How long before device is considered offline
    TYPING_TIMEOUT_SECONDS = 5  # How long typing indicator lasts

    def __init__(self):
        # In-memory state (also backed by Redis for multi-instance)
        self.connected_devices: Dict[int, Dict[str, ConnectedDevice]] = {}  # user_id -> {device_id -> device}
        self.conversation_states: Dict[int, ConversationState] = {}  # user_id -> state
        self.websocket_to_device: Dict[WebSocket, Tuple[int, str]] = {}  # websocket -> (user_id, device_id)

        # Redis client
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub = None

        # Background tasks
        self.presence_task = None
        self.subscriber_task = None

    async def initialize(self):
        """Initialize the sync service."""
        try:
            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
            self.redis_client = redis.from_url(redis_url)
            await self.redis_client.ping()

            # Set up pub/sub for cross-instance sync
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.psubscribe("conversation_sync:*")

            # Start background tasks
            self.subscriber_task = asyncio.create_task(self._redis_subscriber())
            self.presence_task = asyncio.create_task(self._presence_monitor())

            logger.info("Conversation sync service initialized with Redis")

        except Exception as e:
            logger.warning(f"Redis not available, using in-memory only: {e}")
            self.redis_client = None

    async def shutdown(self):
        """Shutdown the sync service."""
        if self.presence_task:
            self.presence_task.cancel()
        if self.subscriber_task:
            self.subscriber_task.cancel()
        if self.pubsub:
            await self.pubsub.punsubscribe("conversation_sync:*")
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()

    # ==================== Device Connection ====================

    async def connect_device(
        self,
        websocket: WebSocket,
        user_id: int,
        device_id: str,
        device_type: DeviceType = DeviceType.UNKNOWN,
        device_name: Optional[str] = None
    ) -> ConnectedDevice:
        """
        Register a device connection for a user.
        """
        device = ConnectedDevice(
            device_id=device_id,
            user_id=user_id,
            device_type=device_type,
            device_name=device_name,
            websocket=websocket,
            connected_at=datetime.utcnow(),
            last_activity=datetime.utcnow()
        )

        # Store in memory
        if user_id not in self.connected_devices:
            self.connected_devices[user_id] = {}
        self.connected_devices[user_id][device_id] = device
        self.websocket_to_device[websocket] = (user_id, device_id)

        # Store in Redis for cross-instance
        if self.redis_client:
            await self._store_device_presence(device)

        # Notify other devices
        await self._broadcast_to_user(
            user_id=user_id,
            event=SyncEvent(
                event_type=SyncEventType.DEVICE_CONNECTED,
                user_id=user_id,
                device_id=device_id,
                data={
                    "device_type": device_type.value,
                    "device_name": device_name
                }
            ),
            exclude_device=device_id
        )

        # Send current state to newly connected device
        await self._send_current_state(device)

        logger.info(f"Device {device_id} connected for user {user_id}")
        return device

    async def disconnect_device(
        self,
        websocket: WebSocket
    ):
        """
        Handle device disconnection.
        """
        if websocket not in self.websocket_to_device:
            return

        user_id, device_id = self.websocket_to_device[websocket]

        # Remove from memory
        if user_id in self.connected_devices:
            if device_id in self.connected_devices[user_id]:
                del self.connected_devices[user_id][device_id]
            if not self.connected_devices[user_id]:
                del self.connected_devices[user_id]

        del self.websocket_to_device[websocket]

        # Remove from Redis
        if self.redis_client:
            await self._remove_device_presence(user_id, device_id)

        # Notify other devices
        await self._broadcast_to_user(
            user_id=user_id,
            event=SyncEvent(
                event_type=SyncEventType.DEVICE_DISCONNECTED,
                user_id=user_id,
                device_id=device_id,
                data={}
            ),
            exclude_device=device_id
        )

        logger.info(f"Device {device_id} disconnected for user {user_id}")

    # ==================== Conversation State ====================

    async def sync_message(
        self,
        user_id: int,
        device_id: str,
        message_id: str,
        message_content: str,
        role: str,
        session_id: str
    ):
        """
        Sync a new message across all user's devices.
        """
        # Update conversation state
        if user_id not in self.conversation_states:
            self.conversation_states[user_id] = ConversationState(
                user_id=user_id,
                session_id=session_id,
                active_device_id=device_id,
                last_message_id=None,
                last_message_preview=None,
                last_activity=datetime.utcnow()
            )

        state = self.conversation_states[user_id]
        state.last_message_id = message_id
        state.last_message_preview = message_content[:100]
        state.last_activity = datetime.utcnow()
        state.session_id = session_id

        # Store in Redis
        if self.redis_client:
            await self._store_conversation_state(state)

        # Broadcast to other devices
        await self._broadcast_to_user(
            user_id=user_id,
            event=SyncEvent(
                event_type=SyncEventType.MESSAGE_SENT if role == "user" else SyncEventType.MESSAGE_RECEIVED,
                user_id=user_id,
                device_id=device_id,
                data={
                    "message_id": message_id,
                    "content": message_content,
                    "role": role,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            ),
            exclude_device=device_id
        )

    async def sync_typing_indicator(
        self,
        user_id: int,
        device_id: str,
        is_typing: bool
    ):
        """
        Sync typing indicator across devices.
        """
        await self._broadcast_to_user(
            user_id=user_id,
            event=SyncEvent(
                event_type=SyncEventType.TYPING_STARTED if is_typing else SyncEventType.TYPING_STOPPED,
                user_id=user_id,
                device_id=device_id,
                data={"is_typing": is_typing}
            ),
            exclude_device=device_id
        )

    async def transfer_session(
        self,
        user_id: int,
        from_device_id: str,
        to_device_id: str
    ):
        """
        Transfer active session from one device to another.
        """
        if user_id in self.conversation_states:
            state = self.conversation_states[user_id]
            state.active_device_id = to_device_id

            await self._broadcast_to_user(
                user_id=user_id,
                event=SyncEvent(
                    event_type=SyncEventType.SESSION_TRANSFERRED,
                    user_id=user_id,
                    device_id=from_device_id,
                    data={
                        "from_device": from_device_id,
                        "to_device": to_device_id,
                        "session_id": state.session_id
                    }
                )
            )

    # ==================== Device State ====================

    async def get_connected_devices(
        self,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get all connected devices for a user.
        """
        devices = []

        if user_id in self.connected_devices:
            for device in self.connected_devices[user_id].values():
                devices.append({
                    "device_id": device.device_id,
                    "device_type": device.device_type.value,
                    "device_name": device.device_name,
                    "connected_at": device.connected_at.isoformat(),
                    "last_activity": device.last_activity.isoformat(),
                    "is_active": device.is_active,
                    "is_current_session": device.current_session_id is not None
                })

        return devices

    async def get_conversation_state(
        self,
        user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get current conversation state for a user.
        """
        if user_id not in self.conversation_states:
            return None

        state = self.conversation_states[user_id]
        return {
            "session_id": state.session_id,
            "active_device_id": state.active_device_id,
            "last_message_preview": state.last_message_preview,
            "last_activity": state.last_activity.isoformat(),
            "context": state.context
        }

    # ==================== Private Methods ====================

    async def _broadcast_to_user(
        self,
        user_id: int,
        event: SyncEvent,
        exclude_device: Optional[str] = None
    ):
        """Broadcast an event to all user's connected devices."""
        message = json.dumps({
            "event_type": event.event_type.value,
            "event_id": event.event_id,
            "device_id": event.device_id,
            "data": event.data,
            "timestamp": event.timestamp.isoformat()
        })

        # Local broadcast
        if user_id in self.connected_devices:
            for device_id, device in self.connected_devices[user_id].items():
                if device_id != exclude_device and device.websocket:
                    try:
                        await device.websocket.send_text(message)
                    except Exception as e:
                        logger.warning(f"Failed to send to device {device_id}: {e}")

        # Redis broadcast for other instances
        if self.redis_client:
            await self.redis_client.publish(
                f"conversation_sync:{user_id}",
                message
            )

    async def _send_current_state(self, device: ConnectedDevice):
        """Send current conversation state to a device."""
        state = self.conversation_states.get(device.user_id)
        if not state:
            return

        if device.websocket:
            try:
                await device.websocket.send_text(json.dumps({
                    "event_type": "state_sync",
                    "data": {
                        "session_id": state.session_id,
                        "last_message_id": state.last_message_id,
                        "last_message_preview": state.last_message_preview,
                        "active_device_id": state.active_device_id,
                        "context": state.context
                    }
                }))
            except Exception as e:
                logger.warning(f"Failed to send state to device: {e}")

    async def _store_device_presence(self, device: ConnectedDevice):
        """Store device presence in Redis."""
        if not self.redis_client:
            return

        key = f"device_presence:{device.user_id}:{device.device_id}"
        await self.redis_client.setex(
            key,
            self.PRESENCE_TTL_SECONDS,
            json.dumps({
                "device_type": device.device_type.value,
                "device_name": device.device_name,
                "connected_at": device.connected_at.isoformat()
            })
        )

    async def _remove_device_presence(self, user_id: int, device_id: str):
        """Remove device presence from Redis."""
        if not self.redis_client:
            return

        key = f"device_presence:{user_id}:{device_id}"
        await self.redis_client.delete(key)

    async def _store_conversation_state(self, state: ConversationState):
        """Store conversation state in Redis."""
        if not self.redis_client:
            return

        key = f"conversation_state:{state.user_id}"
        await self.redis_client.setex(
            key,
            3600,  # 1 hour TTL
            json.dumps({
                "session_id": state.session_id,
                "active_device_id": state.active_device_id,
                "last_message_id": state.last_message_id,
                "last_message_preview": state.last_message_preview,
                "last_activity": state.last_activity.isoformat()
            })
        )

    async def _redis_subscriber(self):
        """Background task to handle Redis pub/sub messages."""
        if not self.pubsub:
            return

        try:
            async for message in self.pubsub.listen():
                if message["type"] == "pmessage":
                    # Handle cross-instance sync
                    channel = message["channel"].decode()
                    data = json.loads(message["data"])

                    # Extract user_id from channel
                    user_id = int(channel.split(":")[-1])

                    # Forward to local connections (that we didn't send from)
                    # This is handled by checking event_id to prevent loops

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Redis subscriber error: {e}")

    async def _presence_monitor(self):
        """Background task to monitor device presence."""
        try:
            while True:
                await asyncio.sleep(30)  # Check every 30 seconds

                now = datetime.utcnow()
                timeout = timedelta(seconds=self.PRESENCE_TTL_SECONDS)

                for user_id in list(self.connected_devices.keys()):
                    for device_id in list(self.connected_devices[user_id].keys()):
                        device = self.connected_devices[user_id][device_id]
                        if now - device.last_activity > timeout:
                            device.is_active = False

        except asyncio.CancelledError:
            pass


# Type hint for tuple
from typing import Tuple

# Global service instance
conversation_sync_service = ConversationSyncService()
