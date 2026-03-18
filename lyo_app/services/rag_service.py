import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_, text, and_
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.learning.models import Course, Lesson
from lyo_app.personalization.models import MemoryInsight
from lyo_app.core.database import get_db_session
from lyo_app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

class RAGService:
    """
    RAG Retrieval Service for Lyo 2.0.
    Uses pgvector for semantic search with keyword fallback.
    """
    
    def __init__(self, db: AsyncSession = None):
        self._db = db

    async def retrieve(self, query: str, limit: int = 5, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Retrieves relevant content chunks based on semantic similarity.
        """
        if not self._db:
            session = await get_db_session()
            async with session:
                return await self._execute_search(session, query, limit, filters)
        else:
            return await self._execute_search(self._db, query, limit, filters)

    async def _execute_search(self, db: AsyncSession, query: str, limit: int, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        results = []
        
        # 1. Generate Query Embedding
        try:
            query_vector = await embedding_service.embed_query(query)
        except Exception as e:
            logger.warning(f"Embedding generation failed, falling back to keyword search: {e}")
            query_vector = None
        
        # Check dialect: SQLite does not support pgvector operators
        dialect = db.bind.dialect.name if db.bind else db.get_bind().dialect.name
        if dialect == "sqlite":
            logger.warning("SQLite dialect detected, falling back to keyword search since pgvector is not supported")
            return await self._execute_keyword_search(db, query, limit)
            
        # 2. Semantic Search (Courses) using Cosine Distance (<-> operator)
        course_stmt = select(Course).order_by(
            Course.embedding.cosine_distance(query_vector)
        ).limit(limit)
        
        course_res = await db.execute(course_stmt)
        courses = course_res.scalars().all()
        for course in courses:
            # Capture properties early to avoid greenlet errors later
            c_id = getattr(course, "id", None)
            c_title = getattr(course, "title", "Untitled")
            c_desc = getattr(course, "description", None) or getattr(course, "summary", "")
            results.append({
                "id": str(c_id),
                "type": "course",
                "title": c_title,
                "content": c_desc,
                "score": 0.95
            })
            
        # 3. Semantic Search (Lessons)
        lesson_stmt = select(Lesson).order_by(
            Lesson.embedding.cosine_distance(query_vector)
        ).limit(limit)
        
        lesson_res = await db.execute(lesson_stmt)
        lessons = lesson_res.scalars().all()
        for lesson in lessons:
            l_id = getattr(lesson, "id", None)
            l_title = getattr(lesson, "title", "Untitled")
            l_content = getattr(lesson, "content", None) or getattr(lesson, "summary", "")
            results.append({
                "id": str(l_id),
                "type": "lesson",
                "title": l_title,
                "content": l_content,
                "score": 0.95
            })
            
        # Limit total results
        return results[:limit]

    async def _execute_keyword_search(self, db: AsyncSession, query: str, limit: int) -> List[Dict[str, Any]]:
        """Legacy keyword search fallback."""
        results = []
        
        # 1. Search Courses
        course_stmt = select(Course).where(
            or_(
                Course.title.ilike(f"%{query}%"),
                Course.description.ilike(f"%{query}%"),
                Course.topic.ilike(f"%{query}%")
            )
        ).limit(limit)
        
        course_res = await db.execute(course_stmt)
        for course in course_res.scalars().all():
            results.append({
                "id": str(course.id),
                "type": "course",
                "title": course.title,
                "content": course.description or course.summary,
                "score": 0.8  # Mock score for keyword match
            })
            
        # 2. Search Lessons
        lesson_stmt = select(Lesson).where(
            or_(
                Lesson.title.ilike(f"%{query}%"),
                Lesson.content.ilike(f"%{query}%"),
                Lesson.topic.ilike(f"%{query}%")
            )
        ).limit(limit)
        
        lesson_res = await db.execute(lesson_stmt)
        lessons = lesson_res.scalars().all()
        for lesson in lessons:
            l_id = getattr(lesson, "id", None)
            l_title = getattr(lesson, "title", "Untitled")
            l_content = getattr(lesson, "content", None) or getattr(lesson, "summary", "")
            results.append({
                "id": str(l_id),
                "type": "lesson",
                "title": l_title,
                "content": l_content,
                "score": 0.9 if query.lower() in l_title.lower() else 0.7
            })
            
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    async def retrieve_user_memory(self, user_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves relevant personal insights for a user using vector search.
        """
        if not self._db:
            session = await get_db_session()
            async with session:
                return await self._execute_user_memory_search(session, user_id, query, limit)
        else:
            return await self._execute_user_memory_search(self._db, user_id, query, limit)

    async def _execute_user_memory_search(self, db: AsyncSession, user_id: int, query: str, limit: int) -> List[Dict[str, Any]]:
        try:
            query_vector = await embedding_service.embed_query(query)
            if not query_vector:
                return []
        except Exception as e:
            logger.error(f"Failed to generate query embedding for user memory: {e}")
            return []

        # Check dialect
        dialect = db.bind.dialect.name if db.bind else db.get_bind().dialect.name
        if dialect == "sqlite":
            # Fallback to simple keyword search for SQLite
            stmt = select(MemoryInsight).where(
                and_(
                    MemoryInsight.user_id == user_id,
                    MemoryInsight.insight_text.ilike(f"%{query}%")
                )
            ).limit(limit)
        else:
            # Semantic search using pgvector
            stmt = select(MemoryInsight).where(
                MemoryInsight.user_id == user_id
            ).order_by(
                MemoryInsight.embedding.cosine_distance(query_vector)
            ).limit(limit)

        try:
            result = await db.execute(stmt)
            insights = result.scalars().all()
        except Exception as e:
            logger.warning(f"User memory search failed (table/pgvector may not exist): {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            return []

        return [
            {
                "category": getattr(insight, "category", "general"),
                "insight": getattr(insight, "insight_text", ""),
                "confidence": getattr(insight, "confidence", 0.0),
                "created_at": getattr(insight, "created_at", datetime.utcnow()).isoformat()
            }
            for insight in insights
        ]
