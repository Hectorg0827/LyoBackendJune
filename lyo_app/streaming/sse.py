"""
Server-Sent Events (SSE) Infrastructure
Real-time streaming for Lyo's AI Classroom

Provides YouTube/Netflix-like streaming experience for:
- AI text generation (word by word)
- Course generation progress
- Lesson content delivery
- Quiz interactions
"""

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """SSE Event types for the AI classroom"""
    
    # Chat/Message events
    MESSAGE_START = "message_start"
    MESSAGE_DELTA = "message_delta"
    MESSAGE_COMPLETE = "message_complete"
    
    # Course generation events
    COURSE_START = "course_start"
    COURSE_PROGRESS = "course_progress"
    COURSE_STEP = "course_step"
    COURSE_COMPLETE = "course_complete"
    
    # Lesson events
    LESSON_START = "lesson_start"
    LESSON_CONTENT = "lesson_content"
    LESSON_COMPLETE = "lesson_complete"
    
    # Media events
    AUDIO_READY = "audio_ready"
    IMAGE_READY = "image_ready"
    
    # Quiz events
    QUIZ_QUESTION = "quiz_question"
    QUIZ_FEEDBACK = "quiz_feedback"
    QUIZ_COMPLETE = "quiz_complete"
    
    # System events
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    DONE = "done"


@dataclass
class StreamEvent:
    """
    SSE Event structure
    
    Follows SSE spec:
    event: <event_type>
    data: <json_data>
    id: <event_id>
    """
    event: EventType
    data: Dict[str, Any]
    id: Optional[str] = None
    retry: Optional[int] = None  # Reconnection time in ms
    
    def __post_init__(self):
        if self.id is None:
            self.id = str(uuid.uuid4())[:8]
            
    def to_sse(self) -> str:
        """Format as SSE string"""
        lines = []
        
        if self.retry:
            lines.append(f"retry: {self.retry}")
            
        lines.append(f"event: {self.event.value}")
        lines.append(f"id: {self.id}")
        lines.append(f"data: {json.dumps(self.data)}")
        lines.append("")  # Empty line to end event
        
        return "\n".join(lines) + "\n"


@dataclass
class StreamSession:
    """Active streaming session"""
    session_id: str
    user_id: Optional[str]
    started_at: datetime = field(default_factory=datetime.utcnow)
    last_event_at: Optional[datetime] = None
    event_count: int = 0
    is_active: bool = True


class SSEManager:
    """
    Server-Sent Events Manager
    
    Features:
    - Connection management
    - Automatic heartbeats
    - Reconnection support
    - Event buffering
    - Session tracking
    """
    
    def __init__(
        self,
        heartbeat_interval: int = 15,  # seconds
        max_reconnect_time: int = 3000,  # ms
        buffer_size: int = 100
    ):
        self.heartbeat_interval = heartbeat_interval
        self.max_reconnect_time = max_reconnect_time
        self.buffer_size = buffer_size
        self._sessions: Dict[str, StreamSession] = {}
        self._event_buffer: Dict[str, List[StreamEvent]] = {}
        
    def create_session(self, user_id: Optional[str] = None) -> str:
        """Create a new streaming session"""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = StreamSession(
            session_id=session_id,
            user_id=user_id
        )
        self._event_buffer[session_id] = []
        logger.debug(f"Created streaming session: {session_id}")
        return session_id
        
    def end_session(self, session_id: str):
        """End a streaming session"""
        if session_id in self._sessions:
            self._sessions[session_id].is_active = False
            del self._sessions[session_id]
        if session_id in self._event_buffer:
            del self._event_buffer[session_id]
        logger.debug(f"Ended streaming session: {session_id}")
        
    def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get session info"""
        return self._sessions.get(session_id)
        
    async def stream_text_generation(
        self,
        generator: AsyncGenerator[str, None],
        session_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream AI text generation word by word
        
        Provides a typing effect like ChatGPT
        """
        session_id = session_id or self.create_session()
        
        # Send start event
        yield StreamEvent(
            event=EventType.MESSAGE_START,
            data={"session_id": session_id, "timestamp": time.time()},
            retry=self.max_reconnect_time
        ).to_sse()
        
        full_content = ""
        chunk_count = 0
        
        try:
            async for chunk in generator:
                full_content += chunk
                chunk_count += 1
                
                yield StreamEvent(
                    event=EventType.MESSAGE_DELTA,
                    data={
                        "content": chunk,
                        "chunk_index": chunk_count
                    }
                ).to_sse()
                
                # Small delay for natural feeling
                await asyncio.sleep(0.02)
                
        except Exception as e:
            yield StreamEvent(
                event=EventType.ERROR,
                data={"error": str(e)}
            ).to_sse()
            
        # Send completion
        yield StreamEvent(
            event=EventType.MESSAGE_COMPLETE,
            data={
                "full_content": full_content,
                "total_chunks": chunk_count,
                "timestamp": time.time()
            }
        ).to_sse()
        
        yield StreamEvent(event=EventType.DONE, data={}).to_sse()
        
    async def stream_course_generation(
        self,
        course_generator: Callable[..., AsyncGenerator[Dict[str, Any], None]],
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        Stream course generation progress
        
        Shows each step: Intent -> Curriculum -> Content -> Assessment -> QA
        """
        session_id = self.create_session()
        
        yield StreamEvent(
            event=EventType.COURSE_START,
            data={
                "session_id": session_id,
                "timestamp": time.time(),
                "steps": [
                    "Analyzing your request",
                    "Designing curriculum",
                    "Creating content",
                    "Building assessments",
                    "Quality review"
                ]
            },
            retry=self.max_reconnect_time
        ).to_sse()
        
        try:
            step_count = 0
            async for progress in course_generator(**kwargs):
                step_count += 1
                
                event_type = EventType.COURSE_PROGRESS
                if progress.get("step_complete"):
                    event_type = EventType.COURSE_STEP
                    
                yield StreamEvent(
                    event=event_type,
                    data={
                        "step": step_count,
                        "step_name": progress.get("step_name", ""),
                        "progress_percent": progress.get("progress", 0),
                        "message": progress.get("message", ""),
                        "data": progress.get("data")
                    }
                ).to_sse()
                
                # Heartbeat every few events
                if step_count % 5 == 0:
                    yield StreamEvent(
                        event=EventType.HEARTBEAT,
                        data={"timestamp": time.time()}
                    ).to_sse()
                    
        except Exception as e:
            logger.error(f"Course generation stream error: {e}")
            yield StreamEvent(
                event=EventType.ERROR,
                data={"error": str(e), "step": step_count}
            ).to_sse()
            
        yield StreamEvent(
            event=EventType.COURSE_COMPLETE,
            data={"timestamp": time.time(), "total_steps": step_count}
        ).to_sse()
        
        yield StreamEvent(event=EventType.DONE, data={}).to_sse()
        self.end_session(session_id)
        
    async def stream_lesson_content(
        self,
        lesson_data: Dict[str, Any],
        include_audio: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Stream lesson content piece by piece
        
        Creates engaging, paced delivery like a real classroom
        """
        session_id = self.create_session()
        
        yield StreamEvent(
            event=EventType.LESSON_START,
            data={
                "session_id": session_id,
                "title": lesson_data.get("title", ""),
                "type": lesson_data.get("lesson_type", ""),
                "timestamp": time.time()
            },
            retry=self.max_reconnect_time
        ).to_sse()
        
        # Stream introduction
        if "introduction" in lesson_data:
            for word in lesson_data["introduction"].split():
                yield StreamEvent(
                    event=EventType.LESSON_CONTENT,
                    data={
                        "section": "introduction",
                        "content": word + " ",
                        "type": "text"
                    }
                ).to_sse()
                await asyncio.sleep(0.03)  # Reading pace
                
        # Stream content blocks
        for i, block in enumerate(lesson_data.get("content_blocks", [])):
            block_type = block.get("block_type", "text")
            
            yield StreamEvent(
                event=EventType.LESSON_CONTENT,
                data={
                    "section": f"block_{i}",
                    "block_type": block_type,
                    "content": block,
                    "type": "block"
                }
            ).to_sse()
            
            # Pause between blocks
            await asyncio.sleep(0.1)
            
        # Stream summary
        if "summary" in lesson_data:
            yield StreamEvent(
                event=EventType.LESSON_CONTENT,
                data={
                    "section": "summary",
                    "content": lesson_data["summary"],
                    "type": "text"
                }
            ).to_sse()
            
        yield StreamEvent(
            event=EventType.LESSON_COMPLETE,
            data={
                "title": lesson_data.get("title", ""),
                "timestamp": time.time()
            }
        ).to_sse()
        
        yield StreamEvent(event=EventType.DONE, data={}).to_sse()
        self.end_session(session_id)
        
    async def stream_quiz(
        self,
        questions: List[Dict[str, Any]],
        answer_handler: Callable[[str, str], Awaitable[Dict[str, Any]]]
    ) -> AsyncGenerator[str, None]:
        """
        Stream interactive quiz experience
        
        Delivers questions one at a time with feedback
        """
        session_id = self.create_session()
        
        for i, question in enumerate(questions):
            yield StreamEvent(
                event=EventType.QUIZ_QUESTION,
                data={
                    "question_number": i + 1,
                    "total_questions": len(questions),
                    "question": question,
                    "session_id": session_id
                }
            ).to_sse()
            
            # Wait for answer (in real implementation, this would be event-driven)
            # For now, we just send questions
            
        yield StreamEvent(
            event=EventType.QUIZ_COMPLETE,
            data={
                "total_questions": len(questions),
                "timestamp": time.time()
            }
        ).to_sse()
        
        yield StreamEvent(event=EventType.DONE, data={}).to_sse()
        
    async def heartbeat_generator(
        self,
        session_id: str
    ) -> AsyncGenerator[str, None]:
        """Generate heartbeat events to keep connection alive"""
        while True:
            session = self.get_session(session_id)
            if not session or not session.is_active:
                break
                
            yield StreamEvent(
                event=EventType.HEARTBEAT,
                data={"timestamp": time.time(), "session_id": session_id}
            ).to_sse()
            
            await asyncio.sleep(self.heartbeat_interval)


# Singleton instance
_sse_manager: Optional[SSEManager] = None


def get_sse_manager() -> SSEManager:
    """Get or create the SSE manager singleton"""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager


def stream_response(
    generator: AsyncGenerator[str, None],
    media_type: str = "text/event-stream"
) -> StreamingResponse:
    """
    Create a StreamingResponse for SSE
    
    Convenience function for FastAPI endpoints
    """
    return StreamingResponse(
        generator,
        media_type=media_type,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Content-Type": "text/event-stream"
        }
    )
