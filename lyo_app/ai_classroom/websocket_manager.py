"""
Lyo AI Classroom - WebSocket Manager for Real-Time Scene Streaming
=================================================================

Real-time, bidirectional streaming infrastructure for the "Living Classroom" architecture.
Replaces the current SSE (Server-Sent Events) with full WebSocket support for:

- Scene-by-scene streaming from Classroom Director
- Real-time user action feedback
- Typing indicators and progressive reveals
- Adaptive UI state synchronization

Architecture: Scene Lifecycle Engine → WebSocket Manager → iOS Client
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Set, List, Optional, Any, Callable
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from lyo_app.ai_classroom.sdui_models import (
    WebSocketPayload, WebSocketEventType, SceneStreamPayload,
    ComponentRenderPayload, UserActionPayload, SystemStatePayload,
    Component, Scene, ActionIntent
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════════
# 🌐 CONNECTION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════════

class ConnectionState(str, Enum):
    """WebSocket connection states"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ACTIVE = "active"           # Actively streaming scenes
    IDLE = "idle"               # Connected but no active streaming
    DISCONNECTING = "disconnecting"
    DISCONNECTED = "disconnected"


class ClientConnection(BaseModel):
    """Individual client WebSocket connection"""

    connection_id: str = Field(default_factory=lambda: str(uuid4()))
    websocket: Optional[WebSocket] = None

    # Session identification
    user_id: str
    session_id: str
    device_id: Optional[str] = None

    # Connection state
    state: ConnectionState = ConnectionState.CONNECTING
    connected_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)

    # Streaming state
    current_scene_id: Optional[str] = None
    streaming_active: bool = False

    # Client capabilities
    supported_events: Set[str] = Field(default_factory=set)
    max_component_batch_size: int = 5
    supports_progressive_rendering: bool = True

    # Performance metrics
    latency_ms: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0

    class Config:
        arbitrary_types_allowed = True  # For WebSocket object


class ConnectionRoom:
    """Group related connections (future: multi-user classrooms)"""

    def __init__(self, room_id: str):
        self.room_id = room_id
        self.connections: Dict[str, ClientConnection] = {}
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()

    def add_connection(self, connection: ClientConnection):
        """Add connection to room"""
        self.connections[connection.connection_id] = connection
        self.last_activity = datetime.utcnow()
        logger.info(f"🏠 Connection {connection.connection_id} joined room {self.room_id}")

    def remove_connection(self, connection_id: str):
        """Remove connection from room"""
        if connection_id in self.connections:
            del self.connections[connection_id]
            self.last_activity = datetime.utcnow()
            logger.info(f"🚪 Connection {connection_id} left room {self.room_id}")

    def get_active_connections(self) -> List[ClientConnection]:
        """Get all active connections in room"""
        return [
            conn for conn in self.connections.values()
            if conn.state in [ConnectionState.AUTHENTICATED, ConnectionState.ACTIVE]
        ]

    def is_empty(self) -> bool:
        """Check if room has no active connections"""
        return len(self.get_active_connections()) == 0


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 MESSAGE ROUTING & DELIVERY
# ═══════════════════════════════════════════════════════════════════════════════════

class MessageQueue:
    """Per-connection message queue with delivery guarantees"""

    def __init__(self, connection_id: str, max_size: int = 100):
        self.connection_id = connection_id
        self.max_size = max_size
        self.queue: List[WebSocketPayload] = []
        self.delivered_count = 0
        self.failed_count = 0

    def enqueue(self, payload: WebSocketPayload) -> bool:
        """Add message to queue"""
        if len(self.queue) >= self.max_size:
            # Remove oldest message to make space
            self.queue.pop(0)
            logger.warning(f"⚠️ Message queue full for {self.connection_id}, dropping oldest")

        self.queue.append(payload)
        return True

    def peek_next(self) -> Optional[WebSocketPayload]:
        """Get next message without removing"""
        return self.queue[0] if self.queue else None

    def dequeue(self) -> Optional[WebSocketPayload]:
        """Remove and return next message"""
        if self.queue:
            self.delivered_count += 1
            return self.queue.pop(0)
        return None

    def mark_failed(self):
        """Mark current delivery as failed"""
        self.failed_count += 1

    def size(self) -> int:
        """Get queue size"""
        return len(self.queue)


class DeliveryManager:
    """Manages reliable message delivery with retries"""

    def __init__(self):
        self.message_queues: Dict[str, MessageQueue] = {}
        self.delivery_tasks: Dict[str, asyncio.Task] = {}
        self.retry_delays = [0.1, 0.5, 1.0, 2.0, 5.0]  # Exponential backoff

    def get_queue(self, connection_id: str) -> MessageQueue:
        """Get or create message queue for connection"""
        if connection_id not in self.message_queues:
            self.message_queues[connection_id] = MessageQueue(connection_id)
        return self.message_queues[connection_id]

    async def queue_message(self, connection_id: str, payload: WebSocketPayload):
        """Queue message for reliable delivery"""
        queue = self.get_queue(connection_id)
        queue.enqueue(payload)

        # Start delivery task if not running
        if connection_id not in self.delivery_tasks:
            self.delivery_tasks[connection_id] = asyncio.create_task(
                self._delivery_worker(connection_id)
            )

    async def _delivery_worker(self, connection_id: str):
        """Background worker for message delivery"""
        queue = self.get_queue(connection_id)
        retry_count = 0

        while queue.size() > 0:
            try:
                payload = queue.peek_next()
                if not payload:
                    break

                # Attempt delivery (would be implemented by WebSocketManager)
                success = await self._attempt_delivery(connection_id, payload)

                if success:
                    queue.dequeue()  # Remove from queue
                    retry_count = 0
                else:
                    # Retry with exponential backoff
                    if retry_count < len(self.retry_delays):
                        await asyncio.sleep(self.retry_delays[retry_count])
                        retry_count += 1
                    else:
                        # Max retries reached, drop message
                        queue.dequeue()
                        queue.mark_failed()
                        retry_count = 0
                        logger.error(f"❌ Message delivery failed after max retries: {connection_id}")

            except Exception as e:
                logger.error(f"💥 Delivery worker error for {connection_id}: {e}")
                break

        # Clean up completed task
        if connection_id in self.delivery_tasks:
            del self.delivery_tasks[connection_id]

    async def _attempt_delivery(self, connection_id: str, payload: WebSocketPayload) -> bool:
        """Attempt to deliver message (implemented by WebSocketManager)"""
        # This will be overridden by WebSocketManager
        return False

    def cleanup_connection(self, connection_id: str):
        """Clean up resources for disconnected connection"""
        if connection_id in self.delivery_tasks:
            self.delivery_tasks[connection_id].cancel()
            del self.delivery_tasks[connection_id]

        if connection_id in self.message_queues:
            del self.message_queues[connection_id]


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎭 SCENE STREAMING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════════

class StreamingMode(str, Enum):
    """Scene streaming modes"""
    INSTANT = "instant"         # Send all components immediately
    PROGRESSIVE = "progressive"  # Stream components one by one with delays
    ADAPTIVE = "adaptive"       # Adjust based on client performance


class SceneStreamer:
    """Handles progressive streaming of scenes to clients"""

    def __init__(self, websocket_manager: 'WebSocketManager'):
        self.websocket_manager = websocket_manager
        self.streaming_tasks: Dict[str, asyncio.Task] = {}

    async def stream_scene(
        self,
        scene: Scene,
        connection: ClientConnection,
        mode: StreamingMode = StreamingMode.ADAPTIVE
    ):
        """Stream scene components progressively"""

        logger.info(f"🎬 Streaming scene {scene.scene_id} to {connection.connection_id} (mode: {mode})")

        # Cancel any existing streaming for this connection
        await self._cancel_existing_stream(connection.connection_id)

        # Start streaming task
        self.streaming_tasks[connection.connection_id] = asyncio.create_task(
            self._progressive_stream_worker(scene, connection, mode)
        )

    async def _progressive_stream_worker(
        self,
        scene: Scene,
        connection: ClientConnection,
        mode: StreamingMode
    ):
        """Background worker for progressive scene streaming"""

        try:
            # Send scene start event
            start_payload = SceneStreamPayload(
                event_type=WebSocketEventType.SCENE_START,
                session_id=connection.session_id,
                user_id=connection.user_id,
                scene=scene,
                component_count=len(scene.components),
                is_final=False
            )

            await self.websocket_manager.send_to_connection(connection.connection_id, start_payload)

            # Stream components based on mode
            if mode == StreamingMode.INSTANT:
                await self._stream_instant(scene, connection)
            elif mode == StreamingMode.PROGRESSIVE:
                await self._stream_progressive(scene, connection)
            else:  # ADAPTIVE
                await self._stream_adaptive(scene, connection)

            # Send scene complete event
            complete_payload = WebSocketPayload(
                event_type=WebSocketEventType.SCENE_COMPLETE,
                session_id=connection.session_id,
                user_id=connection.user_id,
                data={"scene_id": scene.scene_id, "total_components": len(scene.components)}
            )

            await self.websocket_manager.send_to_connection(connection.connection_id, complete_payload)

            logger.info(f"✅ Scene streaming complete: {scene.scene_id}")

        except asyncio.CancelledError:
            logger.info(f"🛑 Scene streaming cancelled: {scene.scene_id}")
        except Exception as e:
            logger.error(f"❌ Scene streaming error: {e}")

    async def _stream_instant(self, scene: Scene, connection: ClientConnection):
        """Send all components immediately"""
        for i, component in enumerate(scene.components):
            payload = ComponentRenderPayload(
                event_type=WebSocketEventType.COMPONENT_RENDER,
                session_id=connection.session_id,
                user_id=connection.user_id,
                component=component,
                render_immediately=True,
                delay_after_previous_ms=0
            )

            await self.websocket_manager.send_to_connection(connection.connection_id, payload)

    async def _stream_progressive(self, scene: Scene, connection: ClientConnection):
        """Stream components with natural delays"""
        for i, component in enumerate(scene.components):
            # Calculate natural delay based on component type
            delay_ms = component.delay_ms or self._calculate_natural_delay(component)

            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

            payload = ComponentRenderPayload(
                event_type=WebSocketEventType.COMPONENT_RENDER,
                session_id=connection.session_id,
                user_id=connection.user_id,
                component=component,
                render_immediately=False,
                delay_after_previous_ms=delay_ms
            )

            await self.websocket_manager.send_to_connection(connection.connection_id, payload)

    async def _stream_adaptive(self, scene: Scene, connection: ClientConnection):
        """Adapt streaming based on connection performance"""
        # Use progressive if low latency, instant if high latency
        if connection.latency_ms < 200:
            await self._stream_progressive(scene, connection)
        else:
            await self._stream_instant(scene, connection)

    def _calculate_natural_delay(self, component: Component) -> int:
        """Calculate natural delay between components"""
        delays = {
            "TeacherMessage": 800,    # Time to "think"
            "StudentPrompt": 1200,    # Peer appears to think
            "QuizCard": 500,          # Quick transition
            "CTAButton": 200,         # Almost instant
            "Celebration": 100        # Immediate joy
        }
        return delays.get(component.type, 300)

    async def _cancel_existing_stream(self, connection_id: str):
        """Cancel any existing streaming task"""
        if connection_id in self.streaming_tasks:
            self.streaming_tasks[connection_id].cancel()
            try:
                await self.streaming_tasks[connection_id]
            except asyncio.CancelledError:
                pass
            del self.streaming_tasks[connection_id]


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 MASTER WEBSOCKET MANAGER
# ═══════════════════════════════════════════════════════════════════════════════════

class WebSocketManager:
    """Master WebSocket manager for real-time scene streaming"""

    def __init__(self):
        # Connection management
        self.connections: Dict[str, ClientConnection] = {}
        self.rooms: Dict[str, ConnectionRoom] = {}

        # Message delivery
        self.delivery_manager = DeliveryManager()

        # Scene streaming
        self.scene_streamer = SceneStreamer(self)

        # Event handlers
        self.event_handlers: Dict[WebSocketEventType, List[Callable]] = {}

        # Performance tracking
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "scenes_streamed": 0
        }

        # Override delivery manager's attempt method
        self.delivery_manager._attempt_delivery = self._attempt_message_delivery

    # ═══════════════════════════════════════════════════════════════════════════════
    # CONNECTION LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════════════

    async def connect_client(
        self,
        websocket: WebSocket,
        user_id: str,
        session_id: str,
        device_id: Optional[str] = None
    ) -> ClientConnection:
        """Handle new client connection"""

        await websocket.accept()

        connection = ClientConnection(
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
            device_id=device_id,
            state=ConnectionState.CONNECTED
        )

        self.connections[connection.connection_id] = connection
        self.stats["total_connections"] += 1
        self.stats["active_connections"] = len(self._get_active_connections())

        # Add to session room
        await self._add_to_room(connection, session_id)

        logger.info(f"🔌 Client connected: {connection.connection_id} (user: {user_id}, session: {session_id})")

        # Send welcome message
        welcome_payload = WebSocketPayload(
            event_type=WebSocketEventType.SYSTEM_STATE,
            session_id=session_id,
            user_id=user_id,
            data={
                "connection_id": connection.connection_id,
                "server_time": datetime.utcnow().isoformat(),
                "supported_features": ["progressive_streaming", "real_time_updates", "reliable_delivery"]
            }
        )

        await self.send_to_connection(connection.connection_id, welcome_payload)

        # Promote state to ACTIVE so _get_active_connections() includes this client
        # and scenes can actually be streamed to it.
        connection.state = ConnectionState.ACTIVE

        return connection

    async def disconnect_client(self, connection_id: str):
        """Handle client disconnection"""

        if connection_id not in self.connections:
            return

        connection = self.connections[connection_id]
        connection.state = ConnectionState.DISCONNECTED

        # Cancel any streaming tasks
        await self.scene_streamer._cancel_existing_stream(connection_id)

        # Clean up delivery queue
        self.delivery_manager.cleanup_connection(connection_id)

        # Remove from room
        await self._remove_from_room(connection, connection.session_id)

        # Remove connection
        del self.connections[connection_id]
        self.stats["active_connections"] = len(self._get_active_connections())

        logger.info(f"🔌 Client disconnected: {connection_id}")

    async def _add_to_room(self, connection: ClientConnection, room_id: str):
        """Add connection to room"""
        if room_id not in self.rooms:
            self.rooms[room_id] = ConnectionRoom(room_id)

        self.rooms[room_id].add_connection(connection)

    async def _remove_from_room(self, connection: ClientConnection, room_id: str):
        """Remove connection from room"""
        if room_id in self.rooms:
            self.rooms[room_id].remove_connection(connection.connection_id)

            # Clean up empty rooms
            if self.rooms[room_id].is_empty():
                del self.rooms[room_id]
                logger.info(f"🏠 Cleaned up empty room: {room_id}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # MESSAGE HANDLING
    # ═══════════════════════════════════════════════════════════════════════════════

    async def handle_client_message(self, connection_id: str, raw_message: str):
        """Handle incoming message from client"""

        if connection_id not in self.connections:
            logger.warning(f"⚠️ Message from unknown connection: {connection_id}")
            return

        connection = self.connections[connection_id]
        connection.last_activity = datetime.utcnow()
        connection.messages_received += 1
        self.stats["messages_received"] += 1

        try:
            # Parse message
            message_data = json.loads(raw_message)
            event_type = WebSocketEventType(message_data.get("event_type", "user_action"))

            # Create appropriate payload
            if event_type == WebSocketEventType.USER_ACTION:
                payload = UserActionPayload(**message_data)
                await self._handle_user_action(payload, connection)
            else:
                # Handle other event types
                payload = WebSocketPayload(**message_data)
                await self._dispatch_event(payload, connection)

        except Exception as e:
            logger.error(f"❌ Error handling client message: {e}")
            # Send error response
            error_payload = WebSocketPayload(
                event_type=WebSocketEventType.ERROR,
                session_id=connection.session_id,
                user_id=connection.user_id,
                data={"error": "Invalid message format", "details": str(e)}
            )
            await self.send_to_connection(connection_id, error_payload)

    async def _handle_user_action(self, payload: UserActionPayload, connection: ClientConnection):
        """Handle user action payload"""
        # This would integrate with the Scene Lifecycle Engine
        logger.info(f"🎯 User action: {payload.action_intent} from {connection.connection_id}")

        # Emit to event handlers
        await self._emit_event("user_action", payload, connection)

    # ═══════════════════════════════════════════════════════════════════════════════
    # MESSAGE SENDING
    # ═══════════════════════════════════════════════════════════════════════════════

    async def send_to_connection(self, connection_id: str, payload: WebSocketPayload):
        """Send message to specific connection"""
        await self.delivery_manager.queue_message(connection_id, payload)

    async def send_to_session(self, session_id: str, payload: WebSocketPayload):
        """Send message to all connections in a session"""
        if session_id in self.rooms:
            room = self.rooms[session_id]
            active_connections = room.get_active_connections()

            for connection in active_connections:
                await self.send_to_connection(connection.connection_id, payload)

    async def send_to_user(self, user_id: str, payload: WebSocketPayload):
        """Send message to all connections for a user"""
        user_connections = [
            conn for conn in self.connections.values()
            if conn.user_id == user_id and conn.state in [ConnectionState.AUTHENTICATED, ConnectionState.ACTIVE]
        ]

        for connection in user_connections:
            await self.send_to_connection(connection.connection_id, payload)

    async def broadcast(self, payload: WebSocketPayload, exclude_connections: List[str] = None):
        """Broadcast message to all active connections"""
        exclude_set = set(exclude_connections or [])

        for connection in self._get_active_connections():
            if connection.connection_id not in exclude_set:
                await self.send_to_connection(connection.connection_id, payload)

    async def _attempt_message_delivery(self, connection_id: str, payload: WebSocketPayload) -> bool:
        """Attempt to deliver message to connection (implements DeliveryManager interface)"""
        if connection_id not in self.connections:
            return False

        connection = self.connections[connection_id]

        if not connection.websocket:
            return False

        try:
            message = json.dumps(payload.dict(), default=str)
            await connection.websocket.send_text(message)

            connection.messages_sent += 1
            self.stats["messages_sent"] += 1

            return True

        except Exception as e:
            logger.error(f"❌ Failed to send message to {connection_id}: {e}")
            return False

    # ═══════════════════════════════════════════════════════════════════════════════
    # SCENE STREAMING API
    # ═══════════════════════════════════════════════════════════════════════════════

    async def stream_scene_to_session(self, session_id: str, scene: Scene, mode: StreamingMode = StreamingMode.ADAPTIVE):
        """Stream scene to all connections in a session"""
        if session_id not in self.rooms:
            logger.warning(f"⚠️ No room found for session: {session_id}")
            return

        room = self.rooms[session_id]
        active_connections = room.get_active_connections()

        logger.info(f"🎬 Streaming scene {scene.scene_id} to {len(active_connections)} connections")

        # Stream to all active connections
        for connection in active_connections:
            await self.scene_streamer.stream_scene(scene, connection, mode)

        self.stats["scenes_streamed"] += 1

    async def stream_scene_to_connection(self, connection_id: str, scene: Scene, mode: StreamingMode = StreamingMode.ADAPTIVE):
        """Stream scene to specific connection"""
        if connection_id not in self.connections:
            logger.warning(f"⚠️ Connection not found: {connection_id}")
            return

        connection = self.connections[connection_id]
        await self.scene_streamer.stream_scene(scene, connection, mode)

    # ═══════════════════════════════════════════════════════════════════════════════
    # EVENT SYSTEM
    # ═══════════════════════════════════════════════════════════════════════════════

    def register_event_handler(self, event_type: str, handler: Callable):
        """Register handler for specific event type"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    async def _emit_event(self, event_type: str, payload: Any, connection: ClientConnection):
        """Emit event to registered handlers"""
        handlers = self.event_handlers.get(event_type, [])

        for handler in handlers:
            try:
                await handler(payload, connection)
            except Exception as e:
                logger.error(f"❌ Event handler error for {event_type}: {e}")

    async def _dispatch_event(self, payload: WebSocketPayload, connection: ClientConnection):
        """Dispatch WebSocket event to appropriate handler"""
        await self._emit_event(payload.event_type.value, payload, connection)

    # ═══════════════════════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════════════════════

    def _get_active_connections(self) -> List[ClientConnection]:
        """Get all active connections"""
        return [
            conn for conn in self.connections.values()
            if conn.state in [ConnectionState.AUTHENTICATED, ConnectionState.ACTIVE]
        ]

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        active_connections = self._get_active_connections()

        return {
            **self.stats,
            "active_connections": len(active_connections),
            "total_rooms": len(self.rooms),
            "average_latency_ms": sum(c.latency_ms for c in active_connections) / max(len(active_connections), 1),
            "streaming_tasks": len(self.scene_streamer.streaming_tasks)
        }

    async def cleanup(self):
        """Clean up resources"""
        # Cancel all streaming tasks
        for task in self.scene_streamer.streaming_tasks.values():
            task.cancel()

        # Cancel all delivery tasks
        for task in self.delivery_manager.delivery_tasks.values():
            task.cancel()

        # Close all connections
        for connection in self.connections.values():
            if connection.websocket:
                await connection.websocket.close()

        logger.info("🧹 WebSocket manager cleanup complete")


# ═══════════════════════════════════════════════════════════════════════════════════
# 🎯 FASTAPI INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════════

# Global instance
websocket_manager = WebSocketManager()

async def get_websocket_manager() -> WebSocketManager:
    """Get WebSocket manager instance"""
    return websocket_manager


__all__ = [
    "WebSocketManager",
    "ClientConnection",
    "ConnectionState",
    "StreamingMode",
    "websocket_manager",
    "get_websocket_manager"
]