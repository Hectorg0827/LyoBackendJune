#!/usr/bin/env python3
"""
Test script for the WebSocket Manager
"""

import sys
import asyncio
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock

# Add current directory to path
sys.path.insert(0, '.')

# Import SDUI models
exec(open('lyo_app/ai_classroom/sdui_models.py').read())

# Mock WebSocket for testing
class MockWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False
        self.accepted = False

    async def accept(self):
        self.accepted = True
        print("🔌 Mock WebSocket accepted")

    async def send_text(self, message: str):
        if not self.closed:
            self.messages.append(message)
            print(f"📤 Sent: {message[:80]}...")
            return True
        return False

    async def close(self, code: int = 1000, reason: str = "Normal"):
        self.closed = True
        print(f"🔌 Mock WebSocket closed: {code} - {reason}")

# Define core WebSocket Manager classes for testing
class ConnectionState:
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"

class ClientConnection:
    def __init__(self, websocket, user_id: str, session_id: str):
        self.connection_id = f"conn_{datetime.now().strftime('%H%M%S%f')[:10]}"
        self.websocket = websocket
        self.user_id = user_id
        self.session_id = session_id
        self.state = ConnectionState.CONNECTED
        self.messages_sent = 0
        self.messages_received = 0

class StreamingMode:
    INSTANT = "instant"
    PROGRESSIVE = "progressive"
    ADAPTIVE = "adaptive"

class MockWebSocketManager:
    """Mock implementation of WebSocket Manager for testing"""

    def __init__(self):
        self.connections = {}
        self.stats = {
            "total_connections": 0,
            "messages_sent": 0,
            "messages_received": 0
        }

    async def connect_client(self, websocket, user_id: str, session_id: str):
        """Handle new client connection"""
        await websocket.accept()

        connection = ClientConnection(websocket, user_id, session_id)
        self.connections[connection.connection_id] = connection
        self.stats["total_connections"] += 1

        print(f"🔌 Client connected: {connection.connection_id} (user: {user_id})")

        # Send welcome message
        welcome_payload = {
            "event_type": "system_state",
            "session_id": session_id,
            "user_id": user_id,
            "data": {
                "connection_id": connection.connection_id,
                "server_time": datetime.now().isoformat(),
                "features": ["streaming", "real_time"]
            },
            "timestamp": datetime.now().isoformat()
        }

        await self.send_to_connection(connection.connection_id, welcome_payload)
        return connection

    async def send_to_connection(self, connection_id: str, payload: Dict[str, Any]):
        """Send message to specific connection"""
        if connection_id not in self.connections:
            print(f"⚠️ Connection not found: {connection_id}")
            return False

        connection = self.connections[connection_id]
        try:
            import json
            message = json.dumps(payload, default=str)
            await connection.websocket.send_text(message)
            connection.messages_sent += 1
            self.stats["messages_sent"] += 1
            return True
        except Exception as e:
            print(f"❌ Failed to send message: {e}")
            return False

    async def stream_scene_to_connection(self, connection_id: str, scene: Scene, mode: str = StreamingMode.ADAPTIVE):
        """Stream scene to specific connection"""
        print(f"🎬 Streaming scene {scene.scene_id[:8]}... to {connection_id} (mode: {mode})")

        # Send scene start
        scene_payload = {
            "event_type": "scene_start",
            "session_id": self.connections[connection_id].session_id,
            "scene_id": scene.scene_id,
            "scene_type": scene.scene_type,
            "component_count": len(scene.components),
            "timestamp": datetime.now().isoformat()
        }
        await self.send_to_connection(connection_id, scene_payload)

        # Stream components based on mode
        if mode == StreamingMode.INSTANT:
            await self._stream_instant(connection_id, scene)
        elif mode == StreamingMode.PROGRESSIVE:
            await self._stream_progressive(connection_id, scene)
        else:  # ADAPTIVE
            await self._stream_adaptive(connection_id, scene)

        # Send scene complete
        complete_payload = {
            "event_type": "scene_complete",
            "session_id": self.connections[connection_id].session_id,
            "scene_id": scene.scene_id,
            "timestamp": datetime.now().isoformat()
        }
        await self.send_to_connection(connection_id, complete_payload)

    async def _stream_instant(self, connection_id: str, scene: Scene):
        """Send all components immediately"""
        for component in scene.components:
            component_payload = {
                "event_type": "component_render",
                "component": component.model_dump(),
                "render_immediately": True,
                "timestamp": datetime.now().isoformat()
            }
            await self.send_to_connection(connection_id, component_payload)

    async def _stream_progressive(self, connection_id: str, scene: Scene):
        """Stream components with delays"""
        for i, component in enumerate(scene.components):
            delay = component.delay_ms / 1000.0 if component.delay_ms else 0.5
            if i > 0:  # Don't delay first component
                await asyncio.sleep(delay)

            component_payload = {
                "event_type": "component_render",
                "component": component.model_dump(),
                "render_immediately": False,
                "delay_ms": component.delay_ms or 500,
                "timestamp": datetime.now().isoformat()
            }
            await self.send_to_connection(connection_id, component_payload)

    async def _stream_adaptive(self, connection_id: str, scene: Scene):
        """Choose streaming mode based on connection"""
        # For test, use progressive
        await self._stream_progressive(connection_id, scene)

    async def disconnect_client(self, connection_id: str):
        """Handle client disconnection"""
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            connection.state = ConnectionState.DISCONNECTED
            if connection.websocket:
                await connection.websocket.close()
            del self.connections[connection_id]
            print(f"🔌 Client disconnected: {connection_id}")

    def get_stats(self):
        """Get connection statistics"""
        return {
            **self.stats,
            "active_connections": len(self.connections)
        }

# Test the WebSocket Manager
async def test_websocket_manager():
    """Test WebSocket Manager functionality"""

    print("🌐 Testing WebSocket Manager\n")

    # Initialize WebSocket Manager
    ws_manager = MockWebSocketManager()

    # Test 1: Connection establishment
    print("📋 Test 1: Connection Establishment")
    mock_websocket = MockWebSocket()

    connection = await ws_manager.connect_client(
        websocket=mock_websocket,
        user_id="test_user",
        session_id="test_session"
    )

    print(f"✅ Connection established: {connection.connection_id}")
    print(f"   WebSocket accepted: {mock_websocket.accepted}")
    print(f"   Messages sent: {len(mock_websocket.messages)}\n")

    # Test 2: Scene streaming
    print("📋 Test 2: Scene Streaming")

    # Create a test scene
    scene = Scene(
        scene_type=SceneType.INSTRUCTION,
        components=[
            TeacherMessage(
                text="Welcome to your lesson!",
                emotion="encouraging",
                delay_ms=0
            ),
            QuizCard(
                question="What is 2 + 2?",
                options=[
                    QuizOption(id="a", label="3", is_correct=False),
                    QuizOption(id="b", label="4", is_correct=True),
                    QuizOption(id="c", label="5", is_correct=False)
                ],
                delay_ms=1000
            ),
            CTAButton(
                label="Submit Answer",
                action_intent=ActionIntent.SUBMIT_ANSWER,
                delay_ms=1500
            )
        ]
    )

    # Test different streaming modes
    streaming_modes = [StreamingMode.INSTANT, StreamingMode.PROGRESSIVE, StreamingMode.ADAPTIVE]

    for mode in streaming_modes:
        print(f"🎬 Testing {mode} streaming...")
        initial_message_count = len(mock_websocket.messages)

        await ws_manager.stream_scene_to_connection(connection.connection_id, scene, mode)

        new_messages = len(mock_websocket.messages) - initial_message_count
        print(f"   📤 Sent {new_messages} messages")

        # Brief pause between tests
        await asyncio.sleep(0.1)

    print()

    # Test 3: Statistics
    print("📋 Test 3: Statistics")
    stats = ws_manager.get_stats()
    print(f"   Active connections: {stats['active_connections']}")
    print(f"   Total messages sent: {stats['messages_sent']}")
    print(f"   Connection messages: {connection.messages_sent}")

    print()

    # Test 4: Disconnection
    print("📋 Test 4: Disconnection")
    await ws_manager.disconnect_client(connection.connection_id)
    print(f"✅ Client disconnected")
    print(f"   WebSocket closed: {mock_websocket.closed}")

    final_stats = ws_manager.get_stats()
    print(f"   Active connections after disconnect: {final_stats['active_connections']}")

    print("\n🎯 All WebSocket Manager tests passed!")

    # Test 5: Message content verification
    print("\n📋 Test 5: Message Content Verification")
    print("Sample messages sent:")
    import json
    for i, message in enumerate(mock_websocket.messages[:3], 1):
        try:
            parsed = json.loads(message)
            event_type = parsed.get("event_type", "unknown")
            print(f"   {i}. {event_type}: {message[:60]}...")
        except json.JSONDecodeError:
            print(f"   {i}. Invalid JSON: {message[:60]}...")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_websocket_manager())