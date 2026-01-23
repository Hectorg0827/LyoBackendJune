"""
Real-time Synchronization System for AI Classroom
Handles real-time updates for learning progress, collaborative features, and live content
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Set, Callable
from datetime import datetime, timedelta
from enum import Enum
import logging
from pydantic import BaseModel, Field
import uuid

logger = logging.getLogger(__name__)

class SyncEventType(str, Enum):
    """Types of synchronization events"""
    PROGRESS_UPDATE = "progress_update"
    CONTENT_CHANGE = "content_change"
    USER_JOIN = "user_join"
    USER_LEAVE = "user_leave"
    LESSON_START = "lesson_start"
    LESSON_COMPLETE = "lesson_complete"
    QUIZ_SUBMIT = "quiz_submit"
    NOTE_ADDED = "note_added"
    COLLABORATION_UPDATE = "collaboration_update"
    ADAPTIVE_SUGGESTION = "adaptive_suggestion"

class SyncEvent(BaseModel):
    """Real-time synchronization event"""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: SyncEventType
    user_id: str
    course_id: str
    lesson_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 1  # 1=high, 2=medium, 3=low

class UserSession(BaseModel):
    """User session tracking for real-time sync"""
    user_id: str
    session_id: str
    course_id: str
    current_lesson_id: Optional[str] = None
    join_time: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    websocket_id: Optional[str] = None
    device_type: str = "unknown"
    is_active: bool = True

class RealTimeSync:
    """Real-time synchronization engine for AI Classroom"""

    def __init__(self):
        self.active_sessions: Dict[str, UserSession] = {}
        self.course_rooms: Dict[str, Set[str]] = {}  # course_id -> set of user_ids
        self.event_handlers: Dict[SyncEventType, List[Callable]] = {}
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.processing_task: Optional[asyncio.Task] = None
        self.websocket_connections: Dict[str, Any] = {}  # session_id -> websocket

    async def start_sync_engine(self):
        """Start the real-time synchronization engine"""
        logger.info("Starting real-time sync engine")
        self.processing_task = asyncio.create_task(self._process_events())

    async def stop_sync_engine(self):
        """Stop the real-time synchronization engine"""
        logger.info("Stopping real-time sync engine")
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass

    async def join_session(self, user_id: str, course_id: str, websocket=None, **kwargs) -> UserSession:
        """User joins a learning session"""
        session_id = str(uuid.uuid4())

        session = UserSession(
            user_id=user_id,
            session_id=session_id,
            course_id=course_id,
            websocket_id=session_id if websocket else None,
            device_type=kwargs.get('device_type', 'unknown')
        )

        self.active_sessions[session_id] = session

        # Add to course room
        if course_id not in self.course_rooms:
            self.course_rooms[course_id] = set()
        self.course_rooms[course_id].add(user_id)

        # Store websocket connection
        if websocket:
            self.websocket_connections[session_id] = websocket

        # Emit join event
        await self._emit_event(SyncEvent(
            event_type=SyncEventType.USER_JOIN,
            user_id=user_id,
            course_id=course_id,
            payload={
                "session_id": session_id,
                "device_type": session.device_type,
                "join_time": session.join_time.isoformat()
            }
        ))

        logger.info(f"User {user_id} joined course {course_id} (session: {session_id})")
        return session

    async def leave_session(self, session_id: str):
        """User leaves a learning session"""
        session = self.active_sessions.get(session_id)
        if not session:
            return

        user_id = session.user_id
        course_id = session.course_id

        # Remove from course room
        if course_id in self.course_rooms:
            self.course_rooms[course_id].discard(user_id)
            if not self.course_rooms[course_id]:
                del self.course_rooms[course_id]

        # Remove websocket connection
        self.websocket_connections.pop(session_id, None)

        # Remove session
        del self.active_sessions[session_id]

        # Emit leave event
        await self._emit_event(SyncEvent(
            event_type=SyncEventType.USER_LEAVE,
            user_id=user_id,
            course_id=course_id,
            payload={"session_id": session_id}
        ))

        logger.info(f"User {user_id} left course {course_id} (session: {session_id})")

    async def update_progress(self, user_id: str, course_id: str, lesson_id: str,
                            progress_data: Dict[str, Any]):
        """Update learning progress with real-time sync"""
        await self._emit_event(SyncEvent(
            event_type=SyncEventType.PROGRESS_UPDATE,
            user_id=user_id,
            course_id=course_id,
            lesson_id=lesson_id,
            payload=progress_data,
            priority=1  # High priority
        ))

    async def start_lesson(self, user_id: str, course_id: str, lesson_id: str,
                          lesson_data: Dict[str, Any]):
        """Start a lesson with real-time tracking"""
        # Update session with current lesson
        for session in self.active_sessions.values():
            if session.user_id == user_id and session.course_id == course_id:
                session.current_lesson_id = lesson_id
                session.last_activity = datetime.now()
                break

        await self._emit_event(SyncEvent(
            event_type=SyncEventType.LESSON_START,
            user_id=user_id,
            course_id=course_id,
            lesson_id=lesson_id,
            payload=lesson_data
        ))

    async def complete_lesson(self, user_id: str, course_id: str, lesson_id: str,
                             completion_data: Dict[str, Any]):
        """Complete a lesson with real-time updates"""
        await self._emit_event(SyncEvent(
            event_type=SyncEventType.LESSON_COMPLETE,
            user_id=user_id,
            course_id=course_id,
            lesson_id=lesson_id,
            payload=completion_data,
            priority=1  # High priority
        ))

    async def submit_quiz(self, user_id: str, course_id: str, lesson_id: str,
                         quiz_data: Dict[str, Any]):
        """Submit quiz with real-time processing"""
        await self._emit_event(SyncEvent(
            event_type=SyncEventType.QUIZ_SUBMIT,
            user_id=user_id,
            course_id=course_id,
            lesson_id=lesson_id,
            payload=quiz_data,
            priority=1
        ))

    async def add_note(self, user_id: str, course_id: str, lesson_id: str,
                      note_data: Dict[str, Any]):
        """Add note with real-time sync"""
        await self._emit_event(SyncEvent(
            event_type=SyncEventType.NOTE_ADDED,
            user_id=user_id,
            course_id=course_id,
            lesson_id=lesson_id,
            payload=note_data,
            priority=2
        ))

    async def send_adaptive_suggestion(self, user_id: str, course_id: str,
                                     suggestion_data: Dict[str, Any]):
        """Send adaptive learning suggestion"""
        await self._emit_event(SyncEvent(
            event_type=SyncEventType.ADAPTIVE_SUGGESTION,
            user_id=user_id,
            course_id=course_id,
            payload=suggestion_data,
            priority=1
        ))

    def register_event_handler(self, event_type: SyncEventType, handler: Callable):
        """Register event handler for specific event type"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    async def _emit_event(self, event: SyncEvent):
        """Emit event to processing queue"""
        await self.event_queue.put(event)

    async def _process_events(self):
        """Process events from the queue"""
        while True:
            try:
                event = await self.event_queue.get()
                await self._handle_event(event)
                self.event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing event: {e}")

    async def _handle_event(self, event: SyncEvent):
        """Handle individual sync event"""
        try:
            # Call registered handlers
            handlers = self.event_handlers.get(event.event_type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler for {event.event_type}: {e}")

            # Broadcast to relevant users
            await self._broadcast_event(event)

            logger.debug(f"Processed event {event.event_type} for user {event.user_id}")

        except Exception as e:
            logger.error(f"Error handling event {event.event_id}: {e}")

    async def _broadcast_event(self, event: SyncEvent):
        """Broadcast event to relevant connected users"""
        if event.course_id not in self.course_rooms:
            return

        # Get users in the same course
        course_users = self.course_rooms[event.course_id]

        # Find active sessions for these users
        target_sessions = []
        for session in self.active_sessions.values():
            if (session.user_id in course_users and
                session.course_id == event.course_id and
                session.is_active):
                target_sessions.append(session)

        # Send to websocket connections
        event_data = {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "user_id": event.user_id,
            "course_id": event.course_id,
            "lesson_id": event.lesson_id,
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload
        }

        for session in target_sessions:
            websocket = self.websocket_connections.get(session.session_id)
            if websocket:
                try:
                    await websocket.send(json.dumps(event_data))
                except Exception as e:
                    logger.error(f"Error sending event to session {session.session_id}: {e}")
                    # Mark session as inactive
                    session.is_active = False

    def get_active_users(self, course_id: str) -> List[Dict[str, Any]]:
        """Get list of active users in a course"""
        if course_id not in self.course_rooms:
            return []

        active_users = []
        for session in self.active_sessions.values():
            if (session.course_id == course_id and
                session.is_active and
                session.user_id in self.course_rooms[course_id]):

                active_users.append({
                    "user_id": session.user_id,
                    "session_id": session.session_id,
                    "current_lesson": session.current_lesson_id,
                    "join_time": session.join_time.isoformat(),
                    "last_activity": session.last_activity.isoformat(),
                    "device_type": session.device_type
                })

        return active_users

    def get_session_stats(self) -> Dict[str, Any]:
        """Get real-time session statistics"""
        active_sessions = sum(1 for s in self.active_sessions.values() if s.is_active)
        total_courses = len(self.course_rooms)

        device_breakdown = {}
        for session in self.active_sessions.values():
            if session.is_active:
                device = session.device_type
                device_breakdown[device] = device_breakdown.get(device, 0) + 1

        return {
            "active_sessions": active_sessions,
            "total_sessions": len(self.active_sessions),
            "active_courses": total_courses,
            "device_breakdown": device_breakdown,
            "events_queued": self.event_queue.qsize()
        }

    async def cleanup_inactive_sessions(self, timeout_minutes: int = 30):
        """Clean up inactive sessions"""
        cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)
        sessions_to_remove = []

        for session_id, session in self.active_sessions.items():
            if session.last_activity < cutoff_time:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            await self.leave_session(session_id)

        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} inactive sessions")

# Global instance
realtime_sync = RealTimeSync()