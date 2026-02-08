import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from lyo_app.learning.models import Course, Lesson
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
            async with get_db_session() as session:
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
        
        if not query_vector:
            logger.warning("Failed to generate embedding, falling back to keyword search")
            return await self._execute_keyword_search(db, query, limit)
            
        # 2. Semantic Search (Courses) using Cosine Distance (<-> operator)
        course_stmt = select(Course).order_by(
            Course.embedding.cosine_distance(query_vector)
        ).limit(limit)
        
        course_res = await db.execute(course_stmt)
        for course in course_res.scalars().all():
            # Calculate mock score (1 - distance approximation)
            results.append({
                "id": str(course.id),
                "type": "course",
                "title": course.title,
                "content": course.description or course.summary,
                "score": 0.95 # Placeholder, real distance calc requires raw SQL or specific attribute selection
            })
            
        # 3. Semantic Search (Lessons)
        lesson_stmt = select(Lesson).order_by(
            Lesson.embedding.cosine_distance(query_vector)
        ).limit(limit)
        
        lesson_res = await db.execute(lesson_stmt)
        for lesson in lesson_res.scalars().all():
            results.append({
                "id": str(lesson.id),
                "type": "lesson",
                "title": lesson.title,
                "content": lesson.content or lesson.summary,
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
        for lesson in lesson_res.scalars().all():
            results.append({
                "id": str(lesson.id),
                "type": "lesson",
                "title": lesson.title,
                "content": lesson.content or lesson.summary,
                "score": 0.9 if query.lower() in lesson.title.lower() else 0.7
            })
            
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
