"""
WebSocket Connection Manager for Real-time AI Communication

Handles WebSocket connections for real-time AI interactions including:
- Connection lifecycle management
- Message broadcasting
- Heartbeat/health monitoring
- Connection security and validation
- Message queuing and delivery
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from fastapi import WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import weakref

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Production-ready WebSocket connection manager with enterprise features:
    - Connection pooling and lifecycle management
    - Heartbeat monitoring and automatic reconnection detection
    - Message queuing for offline users
    - Security validation and rate limiting
    - Comprehensive logging and monitoring
    """
    
    def __init__(self, heartbeat_interval: int = 30, max_connections: int = 1000):
        # Active connections: user_id -> WebSocket
        self.active_connections: Dict[int, WebSocket] = {}
        
        # Connection metadata
        self.connection_metadata: Dict[int, Dict[str, Any]] = {}
        
        # Heartbeat tasks for monitoring
        self.heartbeat_tasks: Dict[int, asyncio.Task] = {}
        
        # Message queues for offline users
        self.message_queues: Dict[int, List[Dict[str, Any]]] = {}
        
        # Configuration
        self.heartbeat_interval = heartbeat_interval
        self.max_connections = max_connections
        
        # Statistics
        self.total_connections = 0
        self.connection_count_by_time: Dict[str, int] = {}
        self.last_cleanup = time.time()
        
        # Security: Rate limiting per user
        self.user_message_counts: Dict[int, List[float]] = {}
        self.rate_limit_window = 60  # 1 minute
        self.rate_limit_max_messages = 30  # 30 messages per minute
        
        logger.info(f"ConnectionManager initialized with max_connections={max_connections}")

    async def connect(self, user_id: int, websocket: WebSocket, client_info: Optional[Dict] = None) -> bool:
        """
        Establish a new WebSocket connection with comprehensive validation.
        
        Args:
            user_id: User identifier
            websocket: WebSocket connection object
            client_info: Optional client metadata (IP, user agent, etc.)
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        try:
            # Check connection limits
            if len(self.active_connections) >= self.max_connections:
                logger.warning(f"Connection rejected for user {user_id}: max connections reached")
                await websocket.close(code=1008, reason="Server at capacity")
                return False
            
            # Close existing connection if any
            if user_id in self.active_connections:
                logger.info(f"Closing existing connection for user {user_id}")
                await self.disconnect(user_id)
            
            # Accept the new connection
            await websocket.accept()
            
            # Store connection and metadata
            self.active_connections[user_id] = websocket
            self.connection_metadata[user_id] = {
                "connected_at": datetime.utcnow(),
                "last_heartbeat": time.time(),
                "client_info": client_info or {},
                "message_count": 0,
                "connection_id": str(uuid.uuid4())
            }
            
            # Start heartbeat monitoring
            self.heartbeat_tasks[user_id] = asyncio.create_task(
                self._heartbeat_monitor(user_id, websocket)
            )
            
            # Send queued messages if any
            await self._deliver_queued_messages(user_id)
            
            # Update statistics
            self.total_connections += 1
            hour_key = datetime.utcnow().strftime("%Y-%m-%d-%H")
            self.connection_count_by_time[hour_key] = self.connection_count_by_time.get(hour_key, 0) + 1
            
            logger.info(f"WebSocket connected for user {user_id}. Total active: {len(self.active_connections)}")
            
            # Send welcome message
            await self.send_personal_message(
                json.dumps({
                    "type": "connection_established",
                    "message": "AI mentor is ready to help!",
                    "timestamp": datetime.utcnow().isoformat(),
                    "connection_id": self.connection_metadata[user_id]["connection_id"]
                }),
                user_id
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to establish connection for user {user_id}: {e}")
            return False

    async def disconnect(self, user_id: int) -> None:
        """
        Safely disconnect a user and clean up resources.
        
        Args:
            user_id: User identifier to disconnect
        """
        try:
            # Cancel heartbeat task
            if user_id in self.heartbeat_tasks:
                self.heartbeat_tasks[user_id].cancel()
                del self.heartbeat_tasks[user_id]
            
            # Close WebSocket connection
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                try:
                    await websocket.close()
                except Exception:
                    pass  # Connection might already be closed
                del self.active_connections[user_id]
            
            # Clean up metadata
            if user_id in self.connection_metadata:
                metadata = self.connection_metadata[user_id]
                connection_duration = (datetime.utcnow() - metadata["connected_at"]).total_seconds()
                logger.info(f"User {user_id} disconnected after {connection_duration:.1f}s")
                del self.connection_metadata[user_id]
            
            # Clean up rate limiting data
            if user_id in self.user_message_counts:
                del self.user_message_counts[user_id]
                
        except Exception as e:
            logger.error(f"Error during disconnect for user {user_id}: {e}")

    async def send_personal_message(self, message: str, user_id: int, message_type: str = "message") -> bool:
        """
        Send a message to a specific user with comprehensive error handling.
        
        Args:
            message: Message content (should be JSON string)
            user_id: Target user ID
            message_type: Type of message for categorization
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        try:
            if user_id in self.active_connections:
                websocket = self.active_connections[user_id]
                
                # Validate message format
                try:
                    parsed_message = json.loads(message) if isinstance(message, str) else message
                    if "timestamp" not in parsed_message:
                        parsed_message["timestamp"] = datetime.utcnow().isoformat()
                    if "type" not in parsed_message:
                        parsed_message["type"] = message_type
                    message = json.dumps(parsed_message)
                except (json.JSONDecodeError, TypeError):
                    # If message is not JSON, wrap it
                    message = json.dumps({
                        "type": message_type,
                        "content": str(message),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                # Send message
                await websocket.send_text(message)
                
                # Update metadata
                if user_id in self.connection_metadata:
                    self.connection_metadata[user_id]["message_count"] += 1
                
                logger.debug(f"Message sent to user {user_id}: {message_type}")
                return True
            else:
                # Queue message for offline user
                await self._queue_message(user_id, message, message_type)
                logger.debug(f"Message queued for offline user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            # Try to disconnect on error
            await self.disconnect(user_id)
            return False

    async def broadcast_to_multiple(self, message: str, user_ids: List[int], message_type: str = "broadcast") -> Dict[int, bool]:
        """
        Send a message to multiple users efficiently.
        
        Args:
            message: Message content
            user_ids: List of target user IDs
            message_type: Type of message
            
        Returns:
            Dict mapping user_id to success status
        """
        results = {}
        
        # Send to all users concurrently
        tasks = [
            self.send_personal_message(message, user_id, message_type)
            for user_id in user_ids
        ]
        
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        for user_id, result in zip(user_ids, results_list):
            results[user_id] = result if not isinstance(result, Exception) else False
        
        logger.info(f"Broadcast to {len(user_ids)} users: {sum(results.values())} successful")
        return results

    async def _heartbeat_monitor(self, user_id: int, websocket: WebSocket) -> None:
        """
        Monitor connection health with heartbeat mechanism.
        
        Args:
            user_id: User identifier
            websocket: WebSocket connection
        """
        try:
            while user_id in self.active_connections:
                await asyncio.sleep(self.heartbeat_interval)
                
                # Send ping
                try:
                    await websocket.send_text(json.dumps({
                        "type": "ping",
                        "timestamp": datetime.utcnow().isoformat()
                    }))
                    
                    # Update last heartbeat
                    if user_id in self.connection_metadata:
                        self.connection_metadata[user_id]["last_heartbeat"] = time.time()
                        
                except Exception:
                    # Connection is dead, clean up
                    logger.warning(f"Heartbeat failed for user {user_id}, disconnecting")
                    await self.disconnect(user_id)
                    break
                    
        except asyncio.CancelledError:
            logger.debug(f"Heartbeat monitor cancelled for user {user_id}")
        except Exception as e:
            logger.error(f"Heartbeat monitor error for user {user_id}: {e}")
            await self.disconnect(user_id)

    async def _queue_message(self, user_id: int, message: str, message_type: str) -> None:
        """
        Queue a message for an offline user.
        
        Args:
            user_id: Target user ID
            message: Message content
            message_type: Message type
        """
        if user_id not in self.message_queues:
            self.message_queues[user_id] = []
        
        # Limit queue size to prevent memory issues
        max_queue_size = 50
        if len(self.message_queues[user_id]) >= max_queue_size:
            self.message_queues[user_id].pop(0)  # Remove oldest message
        
        self.message_queues[user_id].append({
            "message": message,
            "type": message_type,
            "queued_at": datetime.utcnow().isoformat()
        })

    async def _deliver_queued_messages(self, user_id: int) -> None:
        """
        Deliver queued messages to a newly connected user.
        
        Args:
            user_id: User identifier
        """
        if user_id in self.message_queues and self.message_queues[user_id]:
            logger.info(f"Delivering {len(self.message_queues[user_id])} queued messages to user {user_id}")
            
            for queued_message in self.message_queues[user_id]:
                await self.send_personal_message(
                    queued_message["message"],
                    user_id,
                    queued_message["type"]
                )
            
            # Clear the queue
            del self.message_queues[user_id]

    def is_rate_limited(self, user_id: int) -> bool:
        """
        Check if a user is rate limited.
        
        Args:
            user_id: User identifier
            
        Returns:
            bool: True if user is rate limited
        """
        now = time.time()
        
        # Initialize if not exists
        if user_id not in self.user_message_counts:
            self.user_message_counts[user_id] = []
        
        # Clean old entries
        self.user_message_counts[user_id] = [
            timestamp for timestamp in self.user_message_counts[user_id]
            if now - timestamp < self.rate_limit_window
        ]
        
        # Check if over limit
        if len(self.user_message_counts[user_id]) >= self.rate_limit_max_messages:
            return True
        
        # Add current timestamp
        self.user_message_counts[user_id].append(now)
        return False

    def get_connection_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive connection statistics.
        
        Returns:
            Dict containing various connection statistics
        """
        now = time.time()
        active_connections = len(self.active_connections)
        
        # Calculate average connection duration
        total_duration = 0
        for metadata in self.connection_metadata.values():
            duration = (datetime.utcnow() - metadata["connected_at"]).total_seconds()
            total_duration += duration
        
        avg_duration = total_duration / active_connections if active_connections > 0 else 0
        
        return {
            "active_connections": active_connections,
            "total_connections_served": self.total_connections,
            "average_connection_duration_seconds": avg_duration,
            "queued_messages_count": sum(len(queue) for queue in self.message_queues.values()),
            "heartbeat_tasks_running": len(self.heartbeat_tasks),
            "connection_count_by_hour": self.connection_count_by_time,
            "last_cleanup": self.last_cleanup
        }

    async def cleanup_stale_connections(self) -> None:
        """
        Clean up stale connections and perform maintenance.
        """
        now = time.time()
        stale_connections = []
        
        # Find stale connections (no heartbeat for 2x interval)
        stale_threshold = self.heartbeat_interval * 2
        
        for user_id, metadata in self.connection_metadata.items():
            if now - metadata["last_heartbeat"] > stale_threshold:
                stale_connections.append(user_id)
        
        # Clean up stale connections
        for user_id in stale_connections:
            logger.warning(f"Cleaning up stale connection for user {user_id}")
            await self.disconnect(user_id)
        
        # Clean up old hourly statistics (keep last 24 hours)
        current_hour = datetime.utcnow().strftime("%Y-%m-%d-%H")
        hours_to_keep = 24
        old_hours = [
            hour for hour in self.connection_count_by_time.keys()
            if hour < current_hour
        ]
        
        if len(old_hours) > hours_to_keep:
            for hour in old_hours[:-hours_to_keep]:
                del self.connection_count_by_time[hour]
        
        self.last_cleanup = now
        logger.info(f"Cleanup completed. Removed {len(stale_connections)} stale connections")


# Global connection manager instance
connection_manager = ConnectionManager()


# Context manager for safe WebSocket handling
@asynccontextmanager
async def websocket_connection(user_id: int, websocket: WebSocket, client_info: Optional[Dict] = None):
    """
    Context manager for safe WebSocket connection handling.
    
    Args:
        user_id: User identifier
        websocket: WebSocket connection
        client_info: Optional client metadata
    """
    connected = False
    try:
        connected = await connection_manager.connect(user_id, websocket, client_info)
        if connected:
            yield connection_manager
        else:
            raise Exception("Failed to establish connection")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        if connected:
            await connection_manager.disconnect(user_id)
