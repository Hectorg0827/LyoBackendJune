"""
Learning service implementation.
Handles course, lesson, and enrollment management operations.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lyo_app.learning.models import (
    Course, Lesson, CourseEnrollment, LessonCompletion,
    DifficultyLevel, ContentType
)
from lyo_app.learning.schemas import (
    CourseCreate, CourseUpdate, LessonCreate, LessonUpdate,
    CourseEnrollmentCreate, LessonCompletionCreate
)
from lyo_app.services.embedding_service import embedding_service


class LearningService:
    """Service class for learning management operations."""

    async def create_course(self, db: AsyncSession, course_data: CourseCreate) -> Course:
        """
        Create a new course.
        
        Args:
            db: Database session
            course_data: Course creation data
            
        Returns:
            Created course instance
        """
        # Convert tags list to JSON string if provided
        tags_json = None
        if course_data.tags:
            import json
            tags_json = json.dumps(course_data.tags)
        
        db_course = Course(
            title=course_data.title,
            description=course_data.description,
            short_description=course_data.short_description,
            thumbnail_url=course_data.thumbnail_url,
            difficulty_level=course_data.difficulty_level,
            estimated_duration_hours=course_data.estimated_duration_hours,
            category=course_data.category,
            tags=tags_json,
            instructor_id=course_data.instructor_id,
            is_published=False,
            is_featured=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(db_course)
        
        # Generate embedding
        embed_text = f"{course_data.title} {course_data.description or ''} {course_data.short_description or ''}"
        db_course.embedding = await embedding_service.embed_text(embed_text.strip())
        
        await db.commit()
        await db.refresh(db_course)
        
        return db_course

    async def get_course_by_id(self, db: AsyncSession, course_id: int) -> Optional[Course]:
        """
        Get course by ID.
        
        Args:
            db: Database session
            course_id: Course ID to search for
            
        Returns:
            Course instance if found, None otherwise
        """
        result = await db.execute(
            select(Course)
            .options(selectinload(Course.lessons))
            .where(Course.id == course_id)
        )
        return result.scalar_one_or_none()

    async def get_courses_by_instructor(
        self, 
        db: AsyncSession, 
        instructor_id: int
    ) -> List[Course]:
        """
        Get all courses by instructor ID.
        
        Args:
            db: Database session
            instructor_id: Instructor user ID
            
        Returns:
            List of courses by the instructor
        """
        result = await db.execute(
            select(Course)
            .where(Course.instructor_id == instructor_id)
            .order_by(Course.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_published_courses(
        self, 
        db: AsyncSession, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[Course]:
        """
        Get published courses with pagination.
        
        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of published courses
        """
        result = await db.execute(
            select(Course)
            .where(Course.is_published == True)
            .order_by(Course.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def publish_course(self, db: AsyncSession, course_id: int) -> Course:
        """
        Publish a course (make it available for enrollment).
        
        Args:
            db: Database session
            course_id: Course ID to publish
            
        Returns:
            Updated course instance
            
        Raises:
            ValueError: If course not found
        """
        course = await self.get_course_by_id(db, course_id)
        if not course:
            raise ValueError("Course not found")
        
        course.is_published = True
        course.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(course)
        
        return course

    async def create_lesson(self, db: AsyncSession, lesson_data: LessonCreate) -> Lesson:
        """
        Create a new lesson.
        
        Args:
            db: Database session
            lesson_data: Lesson creation data
            
        Returns:
            Created lesson instance
        """
        db_lesson = Lesson(
            title=lesson_data.title,
            description=lesson_data.description,
            content=lesson_data.content,
            content_type=lesson_data.content_type,
            course_id=lesson_data.course_id,
            order_index=lesson_data.order_index,
            duration_minutes=lesson_data.duration_minutes,
            video_url=lesson_data.video_url,
            resources_url=lesson_data.resources_url,
            is_published=False,
            is_preview=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        db.add(db_lesson)

        # Generate embedding
        embed_text = f"{lesson_data.title} {lesson_data.description or ''} {lesson_data.content or ''}"
        db_lesson.embedding = await embedding_service.embed_text(embed_text.strip())

        await db.commit()
        await db.refresh(db_lesson)
        
        return db_lesson

    async def get_lessons_by_course(
        self, 
        db: AsyncSession, 
        course_id: int
    ) -> List[Lesson]:
        """
        Get all lessons for a course, ordered by order_index.
        
        Args:
            db: Database session
            course_id: Course ID
            
        Returns:
            List of lessons ordered by order_index
        """
        result = await db.execute(
            select(Lesson)
            .where(Lesson.course_id == course_id)
            .order_by(Lesson.order_index)
        )
        return list(result.scalars().all())

    async def publish_lesson(self, db: AsyncSession, lesson_id: int) -> Lesson:
        """
        Publish a lesson (make it available for students).
        
        Args:
            db: Database session
            lesson_id: Lesson ID to publish
            
        Returns:
            Updated lesson instance
            
        Raises:
            ValueError: If lesson not found
        """
        result = await db.execute(select(Lesson).where(Lesson.id == lesson_id))
        lesson = result.scalar_one_or_none()
        
        if not lesson:
            raise ValueError("Lesson not found")
        
        lesson.is_published = True
        lesson.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(lesson)
        
        return lesson

    async def enroll_in_course(
        self, 
        db: AsyncSession, 
        user_id: int, 
        enrollment_data: CourseEnrollmentCreate
    ) -> CourseEnrollment:
        """
        Enroll a user in a course.
        
        Args:
            db: Database session
            user_id: User ID to enroll
            enrollment_data: Enrollment data
            
        Returns:
            Created enrollment instance
            
        Raises:
            ValueError: If course not found, not published, or user already enrolled
        """
        # Check if course exists and is published
        course = await self.get_course_by_id(db, enrollment_data.course_id)
        if not course:
            raise ValueError("Course not found")
        
        if not course.is_published:
            raise ValueError("Course is not published")
        
        # Check if user is already enrolled
        existing_enrollment = await self.get_user_enrollment(
            db, user_id, enrollment_data.course_id
        )
        if existing_enrollment and existing_enrollment.is_active:
            raise ValueError("User is already enrolled in this course")
        
        # Create enrollment
        db_enrollment = CourseEnrollment(
            user_id=user_id,
            course_id=enrollment_data.course_id,
            enrolled_at=datetime.utcnow(),
            progress_percentage=0,
            is_active=True,
        )
        
        db.add(db_enrollment)
        await db.commit()
        await db.refresh(db_enrollment)
        
        return db_enrollment

    async def get_user_enrollment(
        self, 
        db: AsyncSession, 
        user_id: int, 
        course_id: int
    ) -> Optional[CourseEnrollment]:
        """
        Get user's enrollment for a specific course.
        
        Args:
            db: Database session
            user_id: User ID
            course_id: Course ID
            
        Returns:
            Enrollment instance if found, None otherwise
        """
        result = await db.execute(
            select(CourseEnrollment)
            .where(
                and_(
                    CourseEnrollment.user_id == user_id,
                    CourseEnrollment.course_id == course_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def complete_lesson(
        self, 
        db: AsyncSession, 
        user_id: int, 
        completion_data: LessonCompletionCreate
    ) -> LessonCompletion:
        """
        Mark a lesson as completed by a user.
        
        Args:
            db: Database session
            user_id: User ID completing the lesson
            completion_data: Lesson completion data
            
        Returns:
            Created lesson completion instance
            
        Raises:
            ValueError: If lesson not found, not published, or user not enrolled
        """
        # Get lesson and verify it exists and is published
        result = await db.execute(select(Lesson).where(Lesson.id == completion_data.lesson_id))
        lesson = result.scalar_one_or_none()
        
        if not lesson:
            raise ValueError("Lesson not found")
        
        if not lesson.is_published:
            raise ValueError("Lesson is not published")
        
        # Verify user is enrolled in the course
        enrollment = await self.get_user_enrollment(db, user_id, lesson.course_id)
        if not enrollment or not enrollment.is_active:
            raise ValueError("User is not enrolled in this course")
        
        # Check if lesson is already completed
        existing_completion = await self.get_lesson_completion(
            db, user_id, completion_data.lesson_id
        )
        if existing_completion:
            raise ValueError("Lesson already completed")
        
        # Create completion record
        db_completion = LessonCompletion(
            user_id=user_id,
            lesson_id=completion_data.lesson_id,
            completed_at=datetime.utcnow(),
            time_spent_minutes=completion_data.time_spent_minutes,
        )
        
        db.add(db_completion)
        await db.commit()
        await db.refresh(db_completion)
        
        # Update course progress
        await self._update_course_progress(db, user_id, lesson.course_id)
        
        return db_completion

    async def get_lesson_completion(
        self, 
        db: AsyncSession, 
        user_id: int, 
        lesson_id: int
    ) -> Optional[LessonCompletion]:
        """
        Get lesson completion record for a user.
        
        Args:
            db: Database session
            user_id: User ID
            lesson_id: Lesson ID
            
        Returns:
            Lesson completion instance if found, None otherwise
        """
        result = await db.execute(
            select(LessonCompletion)
            .where(
                and_(
                    LessonCompletion.user_id == user_id,
                    LessonCompletion.lesson_id == lesson_id
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_user_course_progress(
        self, 
        db: AsyncSession, 
        user_id: int, 
        course_id: int
    ) -> Optional[CourseEnrollment]:
        """
        Get user's progress in a specific course.
        
        Args:
            db: Database session
            user_id: User ID
            course_id: Course ID
            
        Returns:
            Course enrollment with updated progress
        """
        enrollment = await self.get_user_enrollment(db, user_id, course_id)
        if not enrollment:
            return None
        
        # Ensure progress is up to date
        await self._update_course_progress(db, user_id, course_id)
        await db.refresh(enrollment)
        
        return enrollment

    async def _update_course_progress(
        self, 
        db: AsyncSession, 
        user_id: int, 
        course_id: int
    ) -> None:
        """
        Update the progress percentage for a user's course enrollment.
        
        Args:
            db: Database session
            user_id: User ID
            course_id: Course ID
        """
        # Get total published lessons in the course
        total_lessons_result = await db.execute(
            select(func.count(Lesson.id))
            .where(
                and_(
                    Lesson.course_id == course_id,
                    Lesson.is_published == True
                )
            )
        )
        total_lessons = total_lessons_result.scalar()
        
        if total_lessons == 0:
            return  # No lessons to complete
        
        # Get completed lessons count
        completed_lessons_result = await db.execute(
            select(func.count(LessonCompletion.id))
            .join(Lesson, Lesson.id == LessonCompletion.lesson_id)
            .where(
                and_(
                    LessonCompletion.user_id == user_id,
                    Lesson.course_id == course_id,
                    Lesson.is_published == True
                )
            )
        )
        completed_lessons = completed_lessons_result.scalar()
        
        # Calculate progress percentage
        progress_percentage = int((completed_lessons / total_lessons) * 100)
        
        # Update enrollment
        enrollment = await self.get_user_enrollment(db, user_id, course_id)
        if enrollment:
            enrollment.progress_percentage = progress_percentage
            
            # Mark as completed if 100%
            if progress_percentage == 100 and not enrollment.completed_at:
                enrollment.completed_at = datetime.utcnow()
            
            await db.commit()
