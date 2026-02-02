
"""
A2UI Router
Handles WebSocket connections for real-time AI UI streaming.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Optional
from lyo_app.streaming.ws import manager
import logging
import json

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/a2ui/{user_id}")
async def a2ui_websocket(websocket: WebSocket, user_id: str):
    """
    Bi-directional WebSocket for A2UI State Sync & Streaming.
    
    Protocol:
    - Connect: Server accepts connection.
    - Client -> Server: {"type": "state_sync", "payload": {...}} (User Context)
    - Client -> Server: {"type": "action", "payload": {...}} (User Interaction)
    - Server -> Client: {"type": "a2ui_stream_update", "streamId": "...", "chunk": "..."}
    """
    
    # Session ID allows multiple tabs/devices per user if needed
    # For now, we use user_id as session_id for simplicity, or generate one
    session_id = f"{user_id}_{id(websocket)}"
    
    await manager.connect(websocket, session_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await manager.handle_client_message(session_id, message)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from {session_id}: {data}")
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.error(f"WebSocket error in {session_id}: {e}")
        manager.disconnect(websocket, session_id)
