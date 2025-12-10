"""
Job Queue System for Asynchronous Course Generation.
Uses database for persistence - never lose progress.

MIT Architecture Engineering - Production Grade Job Management
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
import json
import logging

from sqlalchemy import Column, String, Text, DateTime, Integer, Float, Boolean, ForeignKey, JSON
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
# Use JSON instead of JSONB for SQLite compatibility; production uses PostgreSQL with JSONB benefits
JSONB = JSON  # Alias for compatibility
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import relationship

from lyo_app.core.database import Base

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job status enum - tracks progress through pipeline"""
    PENDING = "pending"
    RUNNING = "running"
    STEP_1_INTENT = "step_1_intent"
    STEP_2_CURRICULUM = "step_2_curriculum"
    STEP_3_CONTENT = "step_3_content"
    STEP_4_ASSESSMENT = "step_4_assessment"
    STEP_5_QA = "step_5_qa"
    STEP_6_FINALIZE = "step_6_finalize"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CourseGenerationJob(Base):
    """
    Database model for course generation jobs.
    Stores all intermediate results for resumability.
    """
    
    __tablename__ = "course_generation_jobs"
    
    # Primary key
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # User association
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Job status
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING, index=True)
    current_step = Column(String(50), default="pending")
    progress_percent = Column(Integer, default=0)
    
    # Input
    user_prompt = Column(Text, nullable=False)
    user_preferences = Column(JSONB, default={})
    
    # Intermediate results (JSONB for efficient querying)
    intent_result = Column(JSONB, nullable=True)
    curriculum_result = Column(JSONB, nullable=True)
    content_results = Column(JSONB, nullable=True)  # List of lesson contents
    assessment_result = Column(JSONB, nullable=True)
    qa_result = Column(JSONB, nullable=True)
    
    # Final result
    final_course = Column(JSONB, nullable=True)
    final_course_id = Column(PGUUID(as_uuid=True), nullable=True)
    
    # Error handling
    error_message = Column(Text, nullable=True)
    error_step = Column(String(50), nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Metrics
    total_tokens_used = Column(Integer, default=0)
    generation_time_seconds = Column(Float, default=0.0)
    estimated_cost_usd = Column(Float, default=0.0)
    
    # Configuration
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest
    is_premium = Column(Boolean, default=False)
    
    def __repr__(self):
        return f"<CourseGenerationJob {self.id} status={self.status}>"


class GeneratedCourseModel(Base):
    """
    Database model for storing completed generated courses.
    Separate from jobs for efficient querying of completed courses.
    """
    
    __tablename__ = "generated_courses"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id = Column(PGUUID(as_uuid=True), ForeignKey("course_generation_jobs.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Course metadata
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    topic = Column(String(200), nullable=False, index=True)
    difficulty = Column(String(20), nullable=False)
    duration_hours = Column(Float, nullable=False)
    
    # Course content (full JSON)
    course_data = Column(JSONB, nullable=False)
    
    # Quality metrics
    quality_score = Column(Float, nullable=True)
    is_approved = Column(Boolean, default=False)
    
    # Status
    is_published = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime, nullable=True)
    
    # Analytics
    view_count = Column(Integer, default=0)
    enrollment_count = Column(Integer, default=0)
    completion_count = Column(Integer, default=0)
    average_rating = Column(Float, nullable=True)
    
    # Version control
    version = Column(Integer, default=1)
    parent_course_id = Column(PGUUID(as_uuid=True), nullable=True)
    
    def __repr__(self):
        return f"<GeneratedCourse {self.id} title={self.title}>"


class JobManager:
    """
    Manages course generation jobs with full lifecycle support.
    Handles creation, updates, resumption, and completion.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_job(
        self, 
        user_id: int, 
        prompt: str,
        preferences: Dict[str, Any] = None,
        priority: int = 5,
        is_premium: bool = False
    ) -> CourseGenerationJob:
        """Create a new course generation job"""
        job = CourseGenerationJob(
            user_id=user_id,
            user_prompt=prompt,
            user_preferences=preferences or {},
            status=JobStatus.PENDING,
            priority=priority,
            is_premium=is_premium
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        
        logger.info(f"Created job {job.id} for user {user_id}")
        return job
    
    async def get_job(self, job_id: UUID) -> Optional[CourseGenerationJob]:
        """Get job by ID"""
        result = await self.db.execute(
            select(CourseGenerationJob).where(CourseGenerationJob.id == job_id)
        )
        return result.scalars().first()
    
    async def get_user_jobs(
        self, 
        user_id: int, 
        limit: int = 10,
        status: Optional[JobStatus] = None
    ) -> List[CourseGenerationJob]:
        """Get jobs for a user"""
        query = select(CourseGenerationJob).where(
            CourseGenerationJob.user_id == user_id
        )
        if status:
            query = query.where(CourseGenerationJob.status == status)
        query = query.order_by(CourseGenerationJob.created_at.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def update_job_status(
        self, 
        job_id: UUID, 
        status: JobStatus,
        progress: Optional[int] = None,
        current_step: Optional[str] = None,
        **kwargs
    ) -> Optional[CourseGenerationJob]:
        """Update job status and any additional fields"""
        job = await self.get_job(job_id)
        if not job:
            return None
        
        job.status = status
        if progress is not None:
            job.progress_percent = progress
        if current_step is not None:
            job.current_step = current_step
        
        # Handle special status updates
        if status == JobStatus.RUNNING and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status == JobStatus.COMPLETED:
            job.completed_at = datetime.utcnow()
            job.progress_percent = 100
        elif status == JobStatus.FAILED:
            job.completed_at = datetime.utcnow()
        
        # Update any additional fields
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        
        await self.db.commit()
        await self.db.refresh(job)
        
        logger.info(f"Updated job {job_id} to status {status}")
        return job
    
    async def save_step_result(
        self,
        job_id: UUID,
        step: str,
        result: Dict[str, Any],
        tokens_used: int = 0,
        time_seconds: float = 0.0
    ) -> bool:
        """Save intermediate step result"""
        job = await self.get_job(job_id)
        if not job:
            return False
        
        field_map = {
            "intent": "intent_result",
            "curriculum": "curriculum_result",
            "content": "content_results",
            "assessment": "assessment_result",
            "qa": "qa_result"
        }
        
        if step in field_map:
            setattr(job, field_map[step], result)
            job.total_tokens_used += tokens_used
            job.generation_time_seconds += time_seconds
            await self.db.commit()
            
            logger.info(f"Saved {step} result for job {job_id}")
            return True
        
        return False
    
    async def get_job_progress(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get job progress for polling"""
        job = await self.get_job(job_id)
        if not job:
            return None
        
        return {
            "job_id": str(job.id),
            "status": job.status.value,
            "progress_percent": job.progress_percent,
            "current_step": job.current_step,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error": job.error_message,
            "has_result": job.final_course is not None,
            "retry_count": job.retry_count,
            "tokens_used": job.total_tokens_used,
            "time_seconds": job.generation_time_seconds
        }
    
    async def get_resume_point(self, job_id: UUID) -> Optional[str]:
        """
        Determine where to resume a failed/interrupted job.
        Returns the step to resume from.
        """
        job = await self.get_job(job_id)
        if not job:
            return None
        
        # Determine resume point based on what's already saved
        if job.final_course:
            return "completed"
        elif job.qa_result:
            return "finalize"
        elif job.assessment_result:
            return "qa"
        elif job.content_results:
            return "assessment"
        elif job.curriculum_result:
            return "content"
        elif job.intent_result:
            return "curriculum"
        else:
            return "intent"
    
    async def mark_failed(
        self, 
        job_id: UUID, 
        error_message: str,
        error_step: str
    ) -> Optional[CourseGenerationJob]:
        """Mark job as failed with error details"""
        job = await self.get_job(job_id)
        if not job:
            return None
        
        job.status = JobStatus.FAILED
        job.error_message = error_message
        job.error_step = error_step
        job.completed_at = datetime.utcnow()
        job.retry_count += 1
        
        await self.db.commit()
        await self.db.refresh(job)
        
        logger.error(f"Job {job_id} failed at {error_step}: {error_message}")
        return job
    
    async def can_retry(self, job_id: UUID) -> bool:
        """Check if job can be retried"""
        job = await self.get_job(job_id)
        if not job:
            return False
        return job.retry_count < job.max_retries
    
    async def save_final_course(
        self,
        job_id: UUID,
        course_data: Dict[str, Any]
    ) -> Optional[GeneratedCourseModel]:
        """Save the final generated course"""
        job = await self.get_job(job_id)
        if not job:
            return None
        
        # Create the course record
        course = GeneratedCourseModel(
            job_id=job_id,
            user_id=job.user_id,
            title=course_data.get("curriculum", {}).get("course_title", "Untitled Course"),
            description=course_data.get("curriculum", {}).get("course_description", ""),
            topic=course_data.get("intent", {}).get("topic", "Unknown"),
            difficulty=course_data.get("intent", {}).get("target_audience", "intermediate"),
            duration_hours=course_data.get("intent", {}).get("estimated_duration_hours", 1),
            course_data=course_data,
            quality_score=course_data.get("quality_report", {}).get("overall_score"),
            is_approved=course_data.get("quality_report", {}).get("approved", False)
        )
        
        self.db.add(course)
        
        # Update job with final result
        job.final_course = course_data
        job.final_course_id = course.id
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.utcnow()
        job.progress_percent = 100
        
        await self.db.commit()
        await self.db.refresh(course)
        
        logger.info(f"Saved final course {course.id} for job {job_id}")
        return course
    
    async def get_pending_jobs(self, limit: int = 10) -> List[CourseGenerationJob]:
        """Get pending jobs for processing (for background workers)"""
        result = await self.db.execute(
            select(CourseGenerationJob)
            .where(CourseGenerationJob.status == JobStatus.PENDING)
            .order_by(CourseGenerationJob.priority, CourseGenerationJob.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def cleanup_stale_jobs(self, hours: int = 24) -> int:
        """Mark jobs running for too long as failed"""
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        result = await self.db.execute(
            select(CourseGenerationJob)
            .where(CourseGenerationJob.status == JobStatus.RUNNING)
            .where(CourseGenerationJob.started_at < cutoff)
        )
        stale_jobs = result.scalars().all()
        
        count = 0
        for job in stale_jobs:
            job.status = JobStatus.FAILED
            job.error_message = f"Job timed out after {hours} hours"
            job.completed_at = datetime.utcnow()
            count += 1
        
        if count > 0:
            await self.db.commit()
            logger.warning(f"Cleaned up {count} stale jobs")
        
        return count
