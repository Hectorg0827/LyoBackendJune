
"""
Real-time WebSocket Manager for A2UI
Handles bi-directional state synchronization and streaming UI updates.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections for A2UI sessions.
    
    Responsibilities:
    1. Connection Lifecycle (Connect/Disconnect)
    2. State Synchronization (Client -> Server)
    3. UI Streaming (Server -> Client)
    """
    
    def __init__(self):
        # Maps session_id -> List of active WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Stores latest client state per session
        self.client_states: Dict[str, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept connection and register session"""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, websocket: WebSocket, session_id: str):
        """Remove connection"""
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"WebSocket disconnected: {session_id}")

    async def broadcast(self, message: dict, session_id: str):
        """Send message to all sockets in a session"""
        if session_id in self.active_connections:
            json_msg = json.dumps(message)
            disconnected = []
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_text(json_msg)
                except Exception as e:
                    logger.error(f"Failed to send to socket: {e}")
                    disconnected.append(connection)
            
            # Clean up dead connections
            for dead in disconnected:
                self.disconnect(dead, session_id)

    async def handle_client_message(self, session_id: str, message: dict):
        """Process incoming messages from client"""
        msg_type = message.get("type")
        payload = message.get("payload", {})
        
        if msg_type == "state_sync":
            # Update server-side state cache
            # This is where we know what the user is looking at
            self.client_states[session_id] = payload
            logger.debug(f"State synced for {session_id}: {payload}")
            
            # Optionally trigger AI logic here if the state change warrants it
            # e.g. User scrolled to "Quiz" section -> Prepare quiz content
            
        elif msg_type == "action":
            # Handle user interaction (button click, etc)
            action_id = payload.get("actionId")
            logger.info(f"User action in {session_id}: {action_id}")
            # Dispatch to action handler...

    async def stream_ui_update(self, session_id: str, stream_id: str, chunk: str):
        """
        Push a partial UI update (e.g. text token) to a specific component.
        Matches A2UIStreamService on iOS.
        """
        message = {
            "type": "a2ui_stream_update",
            "streamId": stream_id,
            "chunk": chunk,
            "timestamp": datetime.now().isoformat()
        }
        await self.broadcast(message, session_id)

# Singleton
manager = ConnectionManager()
