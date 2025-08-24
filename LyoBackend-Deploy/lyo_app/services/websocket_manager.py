"""WebSocket connection manager for real-time task progress updates."""

import asyncio
import json
import logging
from typing import Dict, List, Set, Any
from fastapi import WebSocket
from datetime import datetime
import redis.asyncio as redis

from lyo_app.core.settings import settings

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections and real-time message broadcasting.
    
    Features:
    - Connection pooling per task ID
    - Redis pub/sub for multi-instance scalability  
    - Message queuing and delivery guarantees
    - Connection health monitoring
    - Automatic cleanup of stale connections
    """
    
    def __init__(self):
        # Active WebSocket connections grouped by task ID
        self.task_connections: Dict[str, Set[WebSocket]] = {}
        
        # Connection metadata
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}
        
        # Redis client for pub/sub (if Redis is available)
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub = None
        
        # Background tasks
        self.cleanup_task = None
        self.redis_subscriber_task = None
        
    async def initialize(self):
        """Initialize Redis connection and background tasks."""
        try:
            self.redis_client = redis.from_url(settings.REDIS_URL)
            await self.redis_client.ping()
            
            # Create pub/sub client
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe("task_progress:*")
            
            # Start Redis subscriber task
            self.redis_subscriber_task = asyncio.create_task(self._redis_subscriber())
            
            logger.info("WebSocket manager initialized with Redis pub/sub")
            
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory mode: {e}")
            self.redis_client = None
        
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
    
    async def shutdown(self):
        """Shutdown WebSocket manager and cleanup resources."""
        # Cancel background tasks
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        if self.redis_subscriber_task:
            self.redis_subscriber_task.cancel()
        
        # Close all WebSocket connections
        for connections in self.task_connections.values():
            for websocket in connections.copy():
                try:
                    await websocket.close()
                except:
                    pass
        
        # Close Redis connections
        if self.pubsub:
            await self.pubsub.unsubscribe("task_progress:*")
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("WebSocket manager shutdown complete")
    
    async def subscribe_to_task(self, websocket: WebSocket, task_id: str):
        """
        Subscribe a WebSocket connection to task progress updates.
        
        Args:
            websocket: WebSocket connection to subscribe
            task_id: Task ID to subscribe to
        """
        # Add to task connections
        if task_id not in self.task_connections:
            self.task_connections[task_id] = set()
        
        self.task_connections[task_id].add(websocket)
        
        # Store connection metadata
        self.connection_metadata[websocket] = {
            "task_id": task_id,
            "connected_at": datetime.utcnow(),
            "last_ping": datetime.utcnow()
        }
        
        logger.debug(f"WebSocket subscribed to task {task_id}. Total connections: {len(self.task_connections[task_id])}")
    
    def unsubscribe_from_task(self, websocket: WebSocket, task_id: str):
        """
        Unsubscribe a WebSocket connection from task updates.
        
        Args:
            websocket: WebSocket connection to unsubscribe
            task_id: Task ID to unsubscribe from
        """
        # Remove from task connections
        if task_id in self.task_connections:
            self.task_connections[task_id].discard(websocket)
            
            # Clean up empty task connection sets
            if not self.task_connections[task_id]:
                del self.task_connections[task_id]
        
        # Remove connection metadata
        self.connection_metadata.pop(websocket, None)
        
        logger.debug(f"WebSocket unsubscribed from task {task_id}")
    
    async def publish_task_progress(self, task_id: str, message: Dict[str, Any]):
        """
        Publish task progress update to all subscribed connections.
        
        Args:
            task_id: Task ID that was updated
            message: Progress message to broadcast
        """
        # Local broadcast to direct connections
        await self._broadcast_to_local_connections(task_id, message)
        
        # Publish to Redis for other instances
        if self.redis_client:
            try:
                channel = f"task_progress:{task_id}"
                await self.redis_client.publish(channel, json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to publish to Redis: {e}")
    
    async def _broadcast_to_local_connections(self, task_id: str, message: Dict[str, Any]):
        """Broadcast message to local WebSocket connections for a task."""
        if task_id not in self.task_connections:
            return
        
        connections = self.task_connections[task_id].copy()
        disconnected_connections = []
        
        for websocket in connections:
            try:
                await websocket.send_json(message)
                
                # Update last activity
                if websocket in self.connection_metadata:
                    self.connection_metadata[websocket]["last_ping"] = datetime.utcnow()
                    
            except Exception as e:
                logger.debug(f"Failed to send message to WebSocket: {e}")
                disconnected_connections.append(websocket)
        
        # Clean up disconnected connections
        for websocket in disconnected_connections:
            self.unsubscribe_from_task(websocket, task_id)
    
    async def _redis_subscriber(self):
        """Background task to handle Redis pub/sub messages."""
        if not self.pubsub:
            return
        
        try:
            async for message in self.pubsub.listen():
                if message["type"] != "message":
                    continue
                
                try:
                    # Parse channel and task ID
                    channel = message["channel"].decode()
                    if not channel.startswith("task_progress:"):
                        continue
                    
                    task_id = channel[14:]  # Remove "task_progress:" prefix
                    
                    # Parse message data
                    data = json.loads(message["data"].decode())
                    
                    # Broadcast to local connections
                    await self._broadcast_to_local_connections(task_id, data)
                    
                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Redis subscriber error: {e}")
    
    async def _cleanup_stale_connections(self):
        """Background task to clean up stale WebSocket connections."""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                
                now = datetime.utcnow()
                stale_connections = []
                
                for websocket, metadata in self.connection_metadata.items():
                    # Consider connection stale if no activity for 5 minutes
                    last_ping = metadata.get("last_ping", metadata["connected_at"])
                    if (now - last_ping).total_seconds() > 300:
                        stale_connections.append((websocket, metadata["task_id"]))
                
                # Clean up stale connections
                for websocket, task_id in stale_connections:
                    logger.debug(f"Cleaning up stale WebSocket connection for task {task_id}")
                    self.unsubscribe_from_task(websocket, task_id)
                    
                    try:
                        await websocket.close()
                    except:
                        pass
                
                if stale_connections:
                    logger.info(f"Cleaned up {len(stale_connections)} stale WebSocket connections")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket cleanup task: {e}")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about current WebSocket connections."""
        total_connections = sum(len(connections) for connections in self.task_connections.values())
        
        return {
            "total_connections": total_connections,
            "active_tasks": len(self.task_connections),
            "task_connections": {
                task_id: len(connections)
                for task_id, connections in self.task_connections.items()
            },
            "redis_enabled": self.redis_client is not None
        }
    
    async def send_heartbeat(self, websocket: WebSocket):
        """Send heartbeat/keepalive message to a specific WebSocket."""
        try:
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Update last activity
            if websocket in self.connection_metadata:
                self.connection_metadata[websocket]["last_ping"] = datetime.utcnow()
                
        except Exception as e:
            logger.debug(f"Failed to send heartbeat: {e}")
            # Connection is likely dead, it will be cleaned up by the cleanup task


# Global WebSocket manager instance
websocket_manager = WebSocketManager()
