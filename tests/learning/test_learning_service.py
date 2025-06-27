"""
Unit tests for the learning service.
Following TDD principles - tests are written before implementation.
"""

import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.learning.schemas import CourseCreate, LessonCreate, CourseEnrollmentCreate, LessonCompletionCreate
from lyo_app.learning.service import LearningService
from lyo_app.learning.models import Course, Lesson, DifficultyLevel, ContentType
from lyo_app.auth.models import User
from lyo_app.auth.service import AuthService
from lyo_app.auth.schemas import UserCreate


class TestLearningService:
    """Test cases for LearningService following TDD principles."""

    @pytest.fixture
    async def learning_service(self) -> LearningService:
        """Create a LearningService instance for testing."""
        return LearningService()

    @pytest.fixture
    async def auth_service(self) -> AuthService:
        """Create an AuthService instance for testing."""
        return AuthService()

    @pytest.fixture
    async def test_instructor(
        self, 
        auth_service: AuthService,
        db_session: AsyncSession
    ) -> User:
        """Create a test instructor user."""
        user_data = UserCreate(
            email="instructor@example.com",
            username="instructor",
            password="password123",
            confirm_password="password123",
            first_name="Test",
            last_name="Instructor"
        )
        return await auth_service.register_user(db_session, user_data)

    @pytest.fixture
    async def test_student(
        self, 
        auth_service: AuthService,
        db_session: AsyncSession
    ) -> User:
        """Create a test student user."""
        user_data = UserCreate(
            email="student@example.com",
            username="student",
            password="password123",
            confirm_password="password123",
            first_name="Test",
            last_name="Student"
        )
        return await auth_service.register_user(db_session, user_data)

    @pytest.fixture
    def valid_course_data(self, test_instructor: User) -> CourseCreate:
        """Create valid course creation data."""
        return CourseCreate(
            title="Introduction to Python",
            description="Learn Python programming from scratch",
            short_description="Python basics for beginners",
            difficulty_level=DifficultyLevel.BEGINNER,
            estimated_duration_hours=20,
            category="Programming",
            tags=["python", "programming", "beginner"],
            instructor_id=test_instructor.id
        )

    async def test_create_course_success(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        db_session: AsyncSession
    ):
        """
        Test successful course creation.
        Should create a new course with correct data.
        """
        course = await learning_service.create_course(db_session, valid_course_data)
        
        assert course is not None
        assert course.title == valid_course_data.title
        assert course.description == valid_course_data.description
        assert course.difficulty_level == valid_course_data.difficulty_level
        assert course.instructor_id == valid_course_data.instructor_id
        assert course.is_published is False  # Default to unpublished
        assert course.created_at is not None

    async def test_get_course_by_id(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        db_session: AsyncSession
    ):
        """
        Test retrieving course by ID.
        """
        created_course = await learning_service.create_course(db_session, valid_course_data)
        
        retrieved_course = await learning_service.get_course_by_id(db_session, created_course.id)
        
        assert retrieved_course is not None
        assert retrieved_course.id == created_course.id
        assert retrieved_course.title == created_course.title

    async def test_get_courses_by_instructor(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        db_session: AsyncSession
    ):
        """
        Test retrieving courses by instructor ID.
        """
        # Create two courses for the same instructor
        course1 = await learning_service.create_course(db_session, valid_course_data)
        
        course_data_2 = valid_course_data.copy()
        course_data_2.title = "Advanced Python"
        course2 = await learning_service.create_course(db_session, course_data_2)
        
        # Retrieve courses by instructor
        courses = await learning_service.get_courses_by_instructor(
            db_session, 
            valid_course_data.instructor_id
        )
        
        assert len(courses) == 2
        course_ids = [course.id for course in courses]
        assert course1.id in course_ids
        assert course2.id in course_ids

    async def test_create_lesson_success(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        db_session: AsyncSession
    ):
        """
        Test successful lesson creation.
        """
        # First create a course
        course = await learning_service.create_course(db_session, valid_course_data)
        
        # Create lesson data
        lesson_data = LessonCreate(
            title="Variables and Data Types",
            description="Learn about Python variables",
            content="Python variables store data values...",
            content_type=ContentType.TEXT,
            course_id=course.id,
            order_index=1,
            duration_minutes=30
        )
        
        lesson = await learning_service.create_lesson(db_session, lesson_data)
        
        assert lesson is not None
        assert lesson.title == lesson_data.title
        assert lesson.course_id == course.id
        assert lesson.order_index == 1
        assert lesson.is_published is False  # Default to unpublished

    async def test_get_lessons_by_course(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        db_session: AsyncSession
    ):
        """
        Test retrieving lessons by course ID.
        """
        # Create course
        course = await learning_service.create_course(db_session, valid_course_data)
        
        # Create multiple lessons
        lesson1_data = LessonCreate(
            title="Introduction",
            content_type=ContentType.VIDEO,
            course_id=course.id,
            order_index=1
        )
        lesson2_data = LessonCreate(
            title="Variables",
            content_type=ContentType.TEXT,
            course_id=course.id,
            order_index=2
        )
        
        lesson1 = await learning_service.create_lesson(db_session, lesson1_data)
        lesson2 = await learning_service.create_lesson(db_session, lesson2_data)
        
        # Retrieve lessons
        lessons = await learning_service.get_lessons_by_course(db_session, course.id)
        
        assert len(lessons) == 2
        # Should be ordered by order_index
        assert lessons[0].order_index < lessons[1].order_index

    async def test_enroll_in_course_success(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        test_student: User,
        db_session: AsyncSession
    ):
        """
        Test successful course enrollment.
        """
        # Create and publish a course
        course = await learning_service.create_course(db_session, valid_course_data)
        await learning_service.publish_course(db_session, course.id)
        
        # Enroll student
        enrollment_data = CourseEnrollmentCreate(course_id=course.id)
        enrollment = await learning_service.enroll_in_course(
            db_session, 
            test_student.id, 
            enrollment_data
        )
        
        assert enrollment is not None
        assert enrollment.user_id == test_student.id
        assert enrollment.course_id == course.id
        assert enrollment.progress_percentage == 0
        assert enrollment.is_active is True

    async def test_enroll_in_unpublished_course_fails(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        test_student: User,
        db_session: AsyncSession
    ):
        """
        Test that enrolling in unpublished course fails.
        """
        # Create unpublished course
        course = await learning_service.create_course(db_session, valid_course_data)
        
        # Try to enroll
        enrollment_data = CourseEnrollmentCreate(course_id=course.id)
        
        with pytest.raises(ValueError, match="Course is not published"):
            await learning_service.enroll_in_course(
                db_session, 
                test_student.id, 
                enrollment_data
            )

    async def test_complete_lesson_success(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        test_student: User,
        db_session: AsyncSession
    ):
        """
        Test successful lesson completion.
        """
        # Create course and lesson
        course = await learning_service.create_course(db_session, valid_course_data)
        await learning_service.publish_course(db_session, course.id)
        
        lesson_data = LessonCreate(
            title="Test Lesson",
            content_type=ContentType.TEXT,
            course_id=course.id,
            order_index=1
        )
        lesson = await learning_service.create_lesson(db_session, lesson_data)
        await learning_service.publish_lesson(db_session, lesson.id)
        
        # Enroll student
        enrollment_data = CourseEnrollmentCreate(course_id=course.id)
        await learning_service.enroll_in_course(db_session, test_student.id, enrollment_data)
        
        # Complete lesson
        completion_data = LessonCompletionCreate(
            lesson_id=lesson.id,
            time_spent_minutes=25
        )
        completion = await learning_service.complete_lesson(
            db_session, 
            test_student.id, 
            completion_data
        )
        
        assert completion is not None
        assert completion.user_id == test_student.id
        assert completion.lesson_id == lesson.id
        assert completion.time_spent_minutes == 25

    async def test_calculate_course_progress(
        self,
        learning_service: LearningService,
        valid_course_data: CourseCreate,
        test_student: User,
        db_session: AsyncSession
    ):
        """
        Test course progress calculation.
        """
        # Create course with 2 lessons
        course = await learning_service.create_course(db_session, valid_course_data)
        await learning_service.publish_course(db_session, course.id)
        
        lesson1_data = LessonCreate(
            title="Lesson 1",
            content_type=ContentType.TEXT,
            course_id=course.id,
            order_index=1
        )
        lesson2_data = LessonCreate(
            title="Lesson 2",
            content_type=ContentType.TEXT,
            course_id=course.id,
            order_index=2
        )
        
        lesson1 = await learning_service.create_lesson(db_session, lesson1_data)
        lesson2 = await learning_service.create_lesson(db_session, lesson2_data)
        await learning_service.publish_lesson(db_session, lesson1.id)
        await learning_service.publish_lesson(db_session, lesson2.id)
        
        # Enroll student
        enrollment_data = CourseEnrollmentCreate(course_id=course.id)
        await learning_service.enroll_in_course(db_session, test_student.id, enrollment_data)
        
        # Complete first lesson
        completion_data = LessonCompletionCreate(lesson_id=lesson1.id)
        await learning_service.complete_lesson(db_session, test_student.id, completion_data)
        
        # Check progress
        progress = await learning_service.get_user_course_progress(
            db_session, 
            test_student.id, 
            course.id
        )
        
        assert progress is not None
        assert progress.progress_percentage == 50  # 1 out of 2 lessons completed
