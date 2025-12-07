"""
Chat Module Stores

Data access layer for courses, notes, and cache management.
Provides async CRUD operations and intelligent caching.
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import uuid4

from sqlalchemy import select, func, and_, or_, desc, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.chat.models import (
    ChatCourse, ChatNote, ChatConversation, ChatMessage, 
    ChatTelemetry, ChatMode, ChipAction
)
from lyo_app.core.cache_manager import IntelligentCacheManager, CacheConfig, CacheStrategy

logger = logging.getLogger(__name__)


# =============================================================================
# COURSE STORE
# =============================================================================

class CourseStore:
    """
    Store for managing chat-generated courses.
    Handles CRUD operations with intelligent caching.
    """
    
    def __init__(self, cache_manager: Optional[IntelligentCacheManager] = None):
        self.cache = cache_manager
        self._cache_prefix = "chat:course"
        self._cache_ttl = 3600  # 1 hour
    
    async def create(
        self,
        db: AsyncSession,
        user_id: Optional[str],
        title: str,
        topic: str,
        description: Optional[str] = None,
        modules: Optional[List[Dict]] = None,
        difficulty: str = "intermediate",
        estimated_hours: Optional[float] = None,
        learning_objectives: Optional[List[str]] = None,
        prerequisites: Optional[List[str]] = None,
        source_conversation_id: Optional[str] = None,
        generated_by_mode: str = ChatMode.COURSE_PLANNER.value
    ) -> ChatCourse:
        """Create a new course from chat interaction"""
        course = ChatCourse(
            id=str(uuid4()),
            user_id=user_id,
            title=title,
            topic=topic,
            description=description,
            modules=modules,
            difficulty=difficulty,
            estimated_hours=estimated_hours,
            learning_objectives=learning_objectives,
            prerequisites=prerequisites,
            source_conversation_id=source_conversation_id,
            generated_by_mode=generated_by_mode
        )
        
        db.add(course)
        await db.commit()
        await db.refresh(course)
        
        # Invalidate user's course list cache
        if self.cache and user_id:
            await self.cache.delete(f"{self._cache_prefix}:user:{user_id}:list")
        
        logger.info(f"Created chat course: {course.id} for topic: {topic}")
        return course
    
    async def get_by_id(self, db: AsyncSession, course_id: str) -> Optional[ChatCourse]:
        """Get course by ID with caching"""
        cache_key = f"{self._cache_prefix}:{course_id}"
        
        # Try cache first
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return cached
        
        result = await db.execute(
            select(ChatCourse).where(ChatCourse.id == course_id)
        )
        course = result.scalar_one_or_none()
        
        # Cache the result
        if course and self.cache:
            await self.cache.set(cache_key, course, ttl=self._cache_ttl)
        
        return course
    
    async def get_by_user(
        self,
        db: AsyncSession,
        user_id: str,
        topic: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[ChatCourse]:
        """Get courses for a user with optional topic filter"""
        query = select(ChatCourse).where(
            and_(
                ChatCourse.user_id == user_id,
                ChatCourse.is_active == True
            )
        )
        
        if topic:
            query = query.where(ChatCourse.topic.ilike(f"%{topic}%"))
        
        query = query.order_by(desc(ChatCourse.created_at)).offset(offset).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_by_topic(
        self,
        db: AsyncSession,
        topic: str,
        user_id: Optional[str] = None,
        limit: int = 10
    ) -> List[ChatCourse]:
        """Get courses by topic, optionally filtered by user"""
        query = select(ChatCourse).where(
            and_(
                ChatCourse.topic.ilike(f"%{topic}%"),
                ChatCourse.is_active == True
            )
        )
        
        if user_id:
            query = query.where(ChatCourse.user_id == user_id)
        
        query = query.order_by(desc(ChatCourse.created_at)).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def update(
        self,
        db: AsyncSession,
        course_id: str,
        **updates
    ) -> Optional[ChatCourse]:
        """Update a course"""
        course = await self.get_by_id(db, course_id)
        if not course:
            return None
        
        for key, value in updates.items():
            if hasattr(course, key):
                setattr(course, key, value)
        
        await db.commit()
        await db.refresh(course)
        
        # Invalidate cache
        if self.cache:
            await self.cache.delete(f"{self._cache_prefix}:{course_id}")
        
        return course
    
    async def delete(self, db: AsyncSession, course_id: str) -> bool:
        """Soft delete a course"""
        course = await self.get_by_id(db, course_id)
        if not course:
            return False
        
        course.is_active = False
        await db.commit()
        
        # Invalidate cache
        if self.cache:
            await self.cache.delete(f"{self._cache_prefix}:{course_id}")
        
        return True


# =============================================================================
# NOTES STORE
# =============================================================================

class NotesStore:
    """
    Store for managing user notes created during chat.
    Supports tagging, search, and organization.
    """
    
    def __init__(self, cache_manager: Optional[IntelligentCacheManager] = None):
        self.cache = cache_manager
        self._cache_prefix = "chat:note"
        self._cache_ttl = 1800  # 30 minutes
    
    async def create(
        self,
        db: AsyncSession,
        user_id: str,
        title: str,
        content: str,
        topic: Optional[str] = None,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        note_type: str = "general",
        importance: int = 0,
        source_message_id: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        related_course_id: Optional[str] = None
    ) -> ChatNote:
        """Create a new note"""
        note = ChatNote(
            id=str(uuid4()),
            user_id=user_id,
            title=title,
            content=content,
            topic=topic,
            tags=tags or [],
            summary=summary,
            note_type=note_type,
            importance=importance,
            source_message_id=source_message_id,
            source_conversation_id=source_conversation_id,
            related_course_id=related_course_id
        )
        
        db.add(note)
        await db.commit()
        await db.refresh(note)
        
        logger.info(f"Created note: {note.id} for user: {user_id}")
        return note
    
    async def get_by_id(self, db: AsyncSession, note_id: str) -> Optional[ChatNote]:
        """Get note by ID"""
        result = await db.execute(
            select(ChatNote).where(ChatNote.id == note_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_user(
        self,
        db: AsyncSession,
        user_id: str,
        topic: Optional[str] = None,
        tags: Optional[List[str]] = None,
        favorites_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[ChatNote]:
        """Get notes for a user with filters"""
        query = select(ChatNote).where(
            and_(
                ChatNote.user_id == user_id,
                ChatNote.is_archived == False
            )
        )
        
        if topic:
            query = query.where(ChatNote.topic.ilike(f"%{topic}%"))
        
        if favorites_only:
            query = query.where(ChatNote.is_favorite == True)
        
        if tags:
            # Filter by any matching tag
            for tag in tags:
                query = query.where(ChatNote.tags.contains([tag]))
        
        query = query.order_by(desc(ChatNote.created_at)).offset(offset).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def search(
        self,
        db: AsyncSession,
        user_id: str,
        query_text: str,
        limit: int = 20
    ) -> List[ChatNote]:
        """Search notes by content and title"""
        query = select(ChatNote).where(
            and_(
                ChatNote.user_id == user_id,
                ChatNote.is_archived == False,
                or_(
                    ChatNote.title.ilike(f"%{query_text}%"),
                    ChatNote.content.ilike(f"%{query_text}%")
                )
            )
        ).order_by(desc(ChatNote.importance), desc(ChatNote.created_at)).limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def update(
        self,
        db: AsyncSession,
        note_id: str,
        **updates
    ) -> Optional[ChatNote]:
        """Update a note"""
        note = await self.get_by_id(db, note_id)
        if not note:
            return None
        
        for key, value in updates.items():
            if hasattr(note, key):
                setattr(note, key, value)
        
        await db.commit()
        await db.refresh(note)
        return note
    
    async def archive(self, db: AsyncSession, note_id: str) -> bool:
        """Archive a note"""
        note = await self.get_by_id(db, note_id)
        if not note:
            return False
        
        note.is_archived = True
        await db.commit()
        return True
    
    async def toggle_favorite(self, db: AsyncSession, note_id: str) -> Optional[bool]:
        """Toggle note favorite status"""
        note = await self.get_by_id(db, note_id)
        if not note:
            return None
        
        note.is_favorite = not note.is_favorite
        await db.commit()
        return note.is_favorite


# =============================================================================
# CONVERSATION STORE
# =============================================================================

class ConversationStore:
    """Store for managing chat conversations and messages"""
    
    def __init__(self, cache_manager: Optional[IntelligentCacheManager] = None):
        self.cache = cache_manager
        self._cache_prefix = "chat:conv"
        self._cache_ttl = 300  # 5 minutes
    
    async def create_conversation(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: Optional[str] = None,
        initial_mode: str = ChatMode.GENERAL.value,
        topic: Optional[str] = None,
        context_data: Optional[Dict] = None
    ) -> ChatConversation:
        """Create a new conversation"""
        conv = ChatConversation(
            id=str(uuid4()),
            session_id=session_id,
            user_id=user_id,
            initial_mode=initial_mode,
            current_mode=initial_mode,
            topic=topic,
            context_data=context_data or {}
        )
        
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
        
        return conv
    
    async def get_conversation(
        self,
        db: AsyncSession,
        conversation_id: str,
        include_messages: bool = False
    ) -> Optional[ChatConversation]:
        """Get conversation by ID"""
        query = select(ChatConversation).where(ChatConversation.id == conversation_id)
        
        if include_messages:
            query = query.options(selectinload(ChatConversation.messages))
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_active_conversation(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: Optional[str] = None
    ) -> Optional[ChatConversation]:
        """Get the most recent active conversation for a session"""
        query = select(ChatConversation).where(
            and_(
                ChatConversation.session_id == session_id,
                ChatConversation.is_active == True
            )
        )
        
        if user_id:
            query = query.where(ChatConversation.user_id == user_id)
        
        query = query.order_by(desc(ChatConversation.updated_at)).limit(1)
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def add_message(
        self,
        db: AsyncSession,
        conversation_id: str,
        role: str,
        content: str,
        mode_used: str = ChatMode.GENERAL.value,
        action_triggered: Optional[str] = None,
        tokens_used: Optional[int] = None,
        model_used: Optional[str] = None,
        latency_ms: Optional[int] = None,
        ctas: Optional[List[Dict]] = None,
        chip_actions: Optional[List[str]] = None,
        cache_hit: bool = False
    ) -> ChatMessage:
        """Add a message to a conversation"""
        message = ChatMessage(
            id=str(uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            mode_used=mode_used,
            action_triggered=action_triggered,
            tokens_used=tokens_used,
            model_used=model_used,
            latency_ms=latency_ms,
            ctas=ctas,
            chip_actions=chip_actions,
            cache_hit=cache_hit
        )
        
        db.add(message)
        
        # Update conversation
        result = await db.execute(
            select(ChatConversation).where(ChatConversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.message_count += 1
            conv.last_message_at = datetime.utcnow()
            conv.current_mode = mode_used
        
        await db.commit()
        await db.refresh(message)
        
        return message
    
    async def get_messages(
        self,
        db: AsyncSession,
        conversation_id: str,
        limit: int = 50,
        before_id: Optional[str] = None
    ) -> List[ChatMessage]:
        """Get messages for a conversation with pagination"""
        query = select(ChatMessage).where(
            ChatMessage.conversation_id == conversation_id
        )
        
        if before_id:
            # Get messages before a specific message
            subq = select(ChatMessage.created_at).where(ChatMessage.id == before_id).scalar_subquery()
            query = query.where(ChatMessage.created_at < subq)
        
        query = query.order_by(desc(ChatMessage.created_at)).limit(limit)
        
        result = await db.execute(query)
        messages = list(result.scalars().all())
        # Return in chronological order
        return list(reversed(messages))
    
    async def update_context(
        self,
        db: AsyncSession,
        conversation_id: str,
        context_data: Dict
    ) -> bool:
        """Update conversation context"""
        conv = await self.get_conversation(db, conversation_id)
        if not conv:
            return False
        
        existing = conv.context_data or {}
        existing.update(context_data)
        conv.context_data = existing
        
        await db.commit()
        return True


# =============================================================================
# RESPONSE CACHE
# =============================================================================

class ResponseCache:
    """
    Intelligent caching for AI responses.
    Uses content hashing for deduplication.
    """
    
    def __init__(self, cache_manager: IntelligentCacheManager):
        self.cache = cache_manager
        self._prefix = "chat:response"
        self._ttl = 1800  # 30 minutes default
    
    def _generate_key(
        self,
        message: str,
        mode: str,
        context_hash: Optional[str] = None
    ) -> str:
        """Generate a cache key based on normalized message content and context.
        
        Normalizes message to improve cache hit rates:
        - Lowercase conversion
        - Whitespace normalization
        - Punctuation cleanup for common variations
        """
        # Normalize message for better cache hit rates
        normalized_message = self._normalize_message(message)
        key_data = f"{mode}:{normalized_message}"
        if context_hash:
            key_data += f":{context_hash}"
        
        hash_value = hashlib.sha256(key_data.encode()).hexdigest()[:16]
        return f"{self._prefix}:{hash_value}"
    
    def _normalize_message(self, message: str) -> str:
        """Normalize message for cache key generation.
        
        Improves cache hit rates by treating similar queries as equivalent:
        - 'What is Python?' == 'what is python' == 'What is Python'
        """
        import re
        # Lowercase and strip whitespace
        normalized = message.lower().strip()
        # Normalize multiple spaces to single space
        normalized = re.sub(r'\s+', ' ', normalized)
        # Remove trailing punctuation that doesn't change meaning
        normalized = re.sub(r'[?!.]+$', '', normalized)
        return normalized
    
    async def get(
        self,
        message: str,
        mode: str,
        context_hash: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get cached response if available"""
        if not self.cache:
            return None
        
        key = self._generate_key(message, mode, context_hash)
        cached = await self.cache.get(key)
        
        if cached:
            logger.debug(f"Cache hit for key: {key[:20]}...")
            return cached
        
        return None
    
    async def set(
        self,
        message: str,
        mode: str,
        response: Dict[str, Any],
        context_hash: Optional[str] = None,
        ttl: Optional[int] = None
    ) -> bool:
        """Cache a response"""
        if not self.cache:
            return False
        
        key = self._generate_key(message, mode, context_hash)
        await self.cache.set(key, response, ttl=ttl or self._ttl)
        
        logger.debug(f"Cached response for key: {key[:20]}...")
        return True
    
    async def invalidate(
        self,
        message: str,
        mode: str,
        context_hash: Optional[str] = None
    ) -> bool:
        """Invalidate a cached response"""
        if not self.cache:
            return False
        
        key = self._generate_key(message, mode, context_hash)
        await self.cache.delete(key)
        return True


# =============================================================================
# TELEMETRY STORE
# =============================================================================

class TelemetryStore:
    """Store for recording and querying telemetry events"""
    
    def __init__(self):
        self._buffer: List[Dict] = []
        self._buffer_size = 100
    
    async def record(
        self,
        db: AsyncSession,
        event_type: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        mode_chosen: Optional[str] = None,
        tokens_used: Optional[int] = None,
        cache_hit: bool = False,
        cta_clicked: Optional[str] = None,
        chip_action_used: Optional[str] = None,
        latency_ms: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> ChatTelemetry:
        """Record a telemetry event"""
        event = ChatTelemetry(
            id=str(uuid4()),
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            conversation_id=conversation_id,
            message_id=message_id,
            mode_chosen=mode_chosen,
            tokens_used=tokens_used,
            cache_hit=cache_hit,
            cta_clicked=cta_clicked,
            chip_action_used=chip_action_used,
            latency_ms=latency_ms,
            metadata=metadata
        )
        
        db.add(event)
        await db.commit()
        
        return event
    
    async def get_stats(
        self,
        db: AsyncSession,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get aggregated telemetry statistics"""
        query = select(
            ChatTelemetry.mode_chosen,
            func.count(ChatTelemetry.id).label('count'),
            func.sum(ChatTelemetry.tokens_used).label('total_tokens'),
            func.sum(func.cast(ChatTelemetry.cache_hit, Integer)).label('cache_hits'),
            func.avg(ChatTelemetry.latency_ms).label('avg_latency')
        ).where(ChatTelemetry.event_type == 'chat_response')
        
        if user_id:
            query = query.where(ChatTelemetry.user_id == user_id)
        
        if start_time:
            query = query.where(ChatTelemetry.created_at >= start_time)
        
        if end_time:
            query = query.where(ChatTelemetry.created_at <= end_time)
        
        query = query.group_by(ChatTelemetry.mode_chosen)
        
        result = await db.execute(query)
        rows = result.fetchall()
        
        stats = {
            "by_mode": {},
            "totals": {
                "messages": 0,
                "tokens": 0,
                "cache_hits": 0,
                "avg_latency_ms": 0
            }
        }
        
        total_messages = 0
        total_latency = 0
        
        for row in rows:
            mode = row.mode_chosen or "unknown"
            stats["by_mode"][mode] = {
                "count": row.count,
                "tokens": row.total_tokens or 0,
                "cache_hits": row.cache_hits or 0,
                "avg_latency_ms": round(row.avg_latency or 0, 2)
            }
            stats["totals"]["messages"] += row.count
            stats["totals"]["tokens"] += row.total_tokens or 0
            stats["totals"]["cache_hits"] += row.cache_hits or 0
            total_messages += row.count
            total_latency += (row.avg_latency or 0) * row.count
        
        if total_messages > 0:
            stats["totals"]["avg_latency_ms"] = round(total_latency / total_messages, 2)
        
        # Get CTA click stats
        cta_query = select(
            ChatTelemetry.cta_clicked,
            func.count(ChatTelemetry.id).label('count')
        ).where(
            and_(
                ChatTelemetry.event_type == 'cta_click',
                ChatTelemetry.cta_clicked.isnot(None)
            )
        )
        
        if user_id:
            cta_query = cta_query.where(ChatTelemetry.user_id == user_id)
        
        cta_query = cta_query.group_by(ChatTelemetry.cta_clicked)
        
        cta_result = await db.execute(cta_query)
        stats["cta_clicks"] = {row.cta_clicked: row.count for row in cta_result.fetchall()}
        
        return stats


# =============================================================================
# STORE INSTANCES
# =============================================================================

# These will be initialized with the cache manager in app startup
course_store = CourseStore()
notes_store = NotesStore()
conversation_store = ConversationStore()
response_cache: Optional[ResponseCache] = None
telemetry_store = TelemetryStore()


def initialize_stores(cache_manager: IntelligentCacheManager):
    """Initialize stores with cache manager"""
    global course_store, notes_store, conversation_store, response_cache
    
    course_store = CourseStore(cache_manager)
    notes_store = NotesStore(cache_manager)
    conversation_store = ConversationStore(cache_manager)
    response_cache = ResponseCache(cache_manager)
    
    logger.info("Chat stores initialized with cache manager")
