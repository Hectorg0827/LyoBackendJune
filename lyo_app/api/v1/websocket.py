"""
Production WebSocket endpoint for real-time updates.
Handles course generation progress, notifications, and live updates.
"""

import json
import logging
from typing import Dict, Any
from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.routing import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.database import get_db
from lyo_app.core.redis_production import RedisPubSub
from lyo_app.auth.production import AuthService, get_auth_service

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, list] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str, connection_id: str):
        """Accept and store new connection."""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(connection_id)
        
        logger.info(f"WebSocket connected: {connection_id} for user {user_id}")
    
    def disconnect(self, connection_id: str, user_id: str = None):
        """Remove connection."""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        if user_id and user_id in self.user_connections:
            if connection_id in self.user_connections[user_id]:
                self.user_connections[user_id].remove(connection_id)
            
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        logger.info(f"WebSocket disconnected: {connection_id}")
    
    async def send_personal_message(self, message: str, connection_id: str):
        """Send message to specific connection."""
        if connection_id in self.active_connections:
            try:
                await self.active_connections[connection_id].send_text(message)
            except Exception as e:
                logger.error(f"Error sending message to {connection_id}: {e}")
                self.disconnect(connection_id)
    
    async def send_user_message(self, message: str, user_id: str):
        """Send message to all user connections."""
        if user_id in self.user_connections:
            disconnected = []
            for connection_id in self.user_connections[user_id]:
                try:
                    await self.send_personal_message(message, connection_id)
                except Exception:
                    disconnected.append(connection_id)
            
            # Clean up disconnected connections
            for connection_id in disconnected:
                self.disconnect(connection_id, user_id)


# Global connection manager
manager = ConnectionManager()


async def get_websocket_user(
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service)
):
    """Validate WebSocket connection token and return user."""
    try:
        payload = await auth_service.verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get user from database
        user = await auth_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        return user
    except Exception as e:
        logger.error(f"WebSocket authentication error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.websocket("/")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    WebSocket endpoint for real-time updates.
    Requires authentication token as query parameter.
    """
    connection_id = None
    user_id = None
    
    try:
        # Authenticate user
        user = await get_websocket_user(token, auth_service)
        user_id = str(user.id)
        connection_id = f"{user_id}_{websocket.client.host}_{id(websocket)}"
        
        # Connect to WebSocket
        await manager.connect(websocket, user_id, connection_id)
        
        # Subscribe to Redis channels for this user
        redis_pubsub = RedisPubSub()
        channels = [
            f"course_generation_{user_id}",
            f"notifications_{user_id}",
            f"feeds_{user_id}"
        ]
        
        await redis_pubsub.subscribe_multiple(channels)
        
        # Send connection confirmation
        await manager.send_personal_message(json.dumps({
            "type": "connection",
            "status": "connected",
            "message": "WebSocket connection established",
            "user_id": user_id,
            "channels": channels
        }), connection_id)
        
        # Listen for Redis messages
        try:
            while True:
                try:
                    # Check for Redis messages
                    message = await redis_pubsub.get_message_nowait()
                    if message:
                        channel = message.get("channel", "")
                        data = message.get("data", {})
                        
                        # Send to WebSocket client
                        await manager.send_personal_message(json.dumps({
                            "type": "redis_update",
                            "channel": channel,
                            "data": data
                        }), connection_id)
                    
                    # Check for WebSocket messages (ping/pong, etc.)
                    try:
                        client_message = await websocket.receive_text()
                        client_data = json.loads(client_message)
                        
                        # Handle client messages
                        if client_data.get("type") == "ping":
                            await manager.send_personal_message(json.dumps({
                                "type": "pong",
                                "timestamp": client_data.get("timestamp")
                            }), connection_id)
                        
                    except WebSocketDisconnect:
                        break
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from client {connection_id}")
                    except Exception as e:
                        if "receive_text" in str(e):
                            break  # Client disconnected
                        logger.error(f"WebSocket message handling error: {e}")
                        
                except Exception as e:
                    if "disconnected" in str(e).lower():
                        break
                    logger.error(f"WebSocket loop error: {e}")
                    
        except Exception as e:
            logger.error(f"WebSocket main loop error: {e}")
        finally:
            # Clean up Redis subscription
            await redis_pubsub.unsubscribe_all()
            await redis_pubsub.close()
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1000)
        except:
            pass
    finally:
        # Clean up connection
        if connection_id and user_id:
            manager.disconnect(connection_id, user_id)


# Additional endpoint for connection testing
@router.get("/test")
async def websocket_test():
    """Test endpoint to verify WebSocket route is available."""
    return {
        "message": "WebSocket endpoint available at /api/v1/ws/",
        "authentication": "Required - pass JWT token as 'token' query parameter",
        "channels": [
            "course_generation_{user_id}",
            "notifications_{user_id}", 
            "feeds_{user_id}"
        ]
    }
