"""
Test cases for learning endpoints.
Tests course management, lesson access, enrollment, and progress tracking.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import AsyncTestCase, assert_successful_response, assert_error_response, assert_pagination_response


class TestCourseManagement(AsyncTestCase):
    """Test course management endpoints."""

    async def test_create_course_as_instructor(self, async_test_client: AsyncClient):
        """Test creating a course as an instructor."""
        # First create an instructor user
        instructor_data = {
            "email": "instructor@example.com",
            "username": "instructor",
            "password": "password123",
            "full_name": "Course Instructor",
            "role": "instructor"
        }

        await async_test_client.post("/api/v1/auth/register", json=instructor_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": instructor_data["email"],
            "password": instructor_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create course
        course_data = {
            "title": "Advanced Python Programming",
            "description": "Learn advanced Python concepts and best practices",
            "instructor": instructor_data["full_name"],
            "duration": 240,  # 4 hours
            "difficulty": "advanced",
            "category": "programming",
            "tags": ["python", "advanced", "programming"],
            "thumbnail_url": "https://example.com/course-thumbnail.jpg",
            "prerequisites": ["Basic Python knowledge"],
            "learning_objectives": [
                "Master advanced Python features",
                "Understand design patterns",
                "Write efficient and maintainable code"
            ]
        }

        response = await async_test_client.post("/api/v1/learning/courses", json=course_data, headers=headers)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["title"] == course_data["title"]
        assert data["description"] == course_data["description"]
        assert data["instructor"] == course_data["instructor"]
        assert data["difficulty"] == course_data["difficulty"]
        assert data["duration"] == course_data["duration"]

    async def test_create_course_as_student_fails(self, async_test_client: AsyncClient):
        """Test that students cannot create courses."""
        # Create a student user
        student_data = {
            "email": "student@example.com",
            "username": "student",
            "password": "password123",
            "full_name": "Regular Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to create course
        course_data = {
            "title": "Unauthorized Course",
            "description": "This should fail",
            "instructor": student_data["full_name"],
            "duration": 60,
            "difficulty": "beginner"
        }

        response = await async_test_client.post("/api/v1/learning/courses", json=course_data, headers=headers)

        assert_error_response(response, 403, "INSUFFICIENT_PERMISSIONS")

    async def test_get_course_list(self, async_test_client: AsyncClient):
        """Test getting list of courses."""
        response = await async_test_client.get("/api/v1/learning/courses")

        assert_successful_response(response, 200)
        data = response.json()

        # Should have pagination structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    async def test_get_course_details(self, async_test_client: AsyncClient):
        """Test getting specific course details."""
        # First create a course
        course = await self.create_test_course(
            title="Test Course Details",
            description="Course for testing details view",
            instructor="Test Instructor"
        )

        response = await async_test_client.get(f"/api/v1/learning/courses/{course.id}")

        assert_successful_response(response, 200)
        data = response.json()

        assert data["id"] == course.id
        assert data["title"] == course.title
        assert data["description"] == course.description
        assert data["instructor"] == course.instructor

    async def test_update_course(self, async_test_client: AsyncClient):
        """Test updating course information."""
        # Create instructor and course
        instructor_data = {
            "email": "update_instructor@example.com",
            "username": "update_instructor",
            "password": "password123",
            "full_name": "Update Instructor"
        }

        await async_test_client.post("/api/v1/auth/register", json=instructor_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": instructor_data["email"],
            "password": instructor_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create course
        course_data = {
            "title": "Original Course",
            "description": "Original description",
            "instructor": instructor_data["full_name"],
            "duration": 120,
            "difficulty": "intermediate"
        }

        create_response = await async_test_client.post("/api/v1/learning/courses", json=course_data, headers=headers)
        course_id = create_response.json()["id"]

        # Update course
        update_data = {
            "title": "Updated Course Title",
            "description": "Updated description",
            "duration": 180,
            "difficulty": "advanced"
        }

        response = await async_test_client.put(f"/api/v1/learning/courses/{course_id}", json=update_data, headers=headers)

        assert_successful_response(response, 200)
        data = response.json()

        assert data["title"] == update_data["title"]
        assert data["description"] == update_data["description"]
        assert data["duration"] == update_data["duration"]
        assert data["difficulty"] == update_data["difficulty"]

    async def test_delete_course(self, async_test_client: AsyncClient):
        """Test deleting a course."""
        # Create instructor and course
        instructor_data = {
            "email": "delete_instructor@example.com",
            "username": "delete_instructor",
            "password": "password123",
            "full_name": "Delete Instructor"
        }

        await async_test_client.post("/api/v1/auth/register", json=instructor_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": instructor_data["email"],
            "password": instructor_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create course
        course_data = {
            "title": "Course to Delete",
            "description": "This course will be deleted",
            "instructor": instructor_data["full_name"],
            "duration": 60,
            "difficulty": "beginner"
        }

        create_response = await async_test_client.post("/api/v1/learning/courses", json=course_data, headers=headers)
        course_id = create_response.json()["id"]

        # Delete course
        response = await async_test_client.delete(f"/api/v1/learning/courses/{course_id}", headers=headers)

        assert_successful_response(response, 204)

        # Verify course is deleted
        get_response = await async_test_client.get(f"/api/v1/learning/courses/{course_id}")
        assert_error_response(get_response, 404, "COURSE_NOT_FOUND")


class TestCourseEnrollment(AsyncTestCase):
    """Test course enrollment functionality."""

    async def test_enroll_in_course(self, async_test_client: AsyncClient):
        """Test enrolling in a course."""
        # Create student user
        student_data = {
            "email": "enroll_student@example.com",
            "username": "enroll_student",
            "password": "password123",
            "full_name": "Enroll Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a course first
        course = await self.create_test_course()

        # Enroll in course
        response = await async_test_client.post(f"/api/v1/learning/courses/{course.id}/enroll", headers=headers)

        assert_successful_response(response, 201)
        data = response.json()

        assert "enrollment_id" in data
        assert data["course_id"] == course.id
        assert data["status"] == "enrolled"

    async def test_enroll_in_nonexistent_course(self, async_test_client: AsyncClient):
        """Test enrolling in a course that doesn't exist."""
        # Create student user
        student_data = {
            "email": "enroll_fake_student@example.com",
            "username": "enroll_fake_student",
            "password": "password123",
            "full_name": "Fake Enroll Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Try to enroll in non-existent course
        response = await async_test_client.post("/api/v1/learning/courses/fake-course-id/enroll", headers=headers)

        assert_error_response(response, 404, "COURSE_NOT_FOUND")

    async def test_duplicate_enrollment_fails(self, async_test_client: AsyncClient):
        """Test that duplicate enrollment fails."""
        # Create student user
        student_data = {
            "email": "duplicate_enroll@example.com",
            "username": "duplicate_enroll",
            "password": "password123",
            "full_name": "Duplicate Enroll Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a course
        course = await self.create_test_course()

        # Enroll once
        await async_test_client.post(f"/api/v1/learning/courses/{course.id}/enroll", headers=headers)

        # Try to enroll again
        response = await async_test_client.post(f"/api/v1/learning/courses/{course.id}/enroll", headers=headers)

        assert_error_response(response, 400, "ALREADY_ENROLLED")

    async def test_get_enrolled_courses(self, async_test_client: AsyncClient):
        """Test getting list of enrolled courses."""
        # Create student user
        student_data = {
            "email": "my_courses_student@example.com",
            "username": "my_courses_student",
            "password": "password123",
            "full_name": "My Courses Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create and enroll in multiple courses
        for i in range(3):
            course = await self.create_test_course(title=f"Course {i+1}")
            await async_test_client.post(f"/api/v1/learning/courses/{course.id}/enroll", headers=headers)

        # Get enrolled courses
        response = await async_test_client.get("/api/v1/learning/my-courses", headers=headers)

        assert_successful_response(response, 200)
        data = response.json()

        assert len(data["items"]) == 3
        assert_pagination_response(response, 3)


class TestLessonManagement(AsyncTestCase):
    """Test lesson management and access."""

    async def test_create_lesson(self, async_test_client: AsyncClient):
        """Test creating a lesson for a course."""
        # Create instructor
        instructor_data = {
            "email": "lesson_instructor@example.com",
            "username": "lesson_instructor",
            "password": "password123",
            "full_name": "Lesson Instructor"
        }

        await async_test_client.post("/api/v1/auth/register", json=instructor_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": instructor_data["email"],
            "password": instructor_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create course
        course_data = {
            "title": "Course with Lessons",
            "description": "Course for lesson testing",
            "instructor": instructor_data["full_name"],
            "duration": 120,
            "difficulty": "intermediate"
        }

        course_response = await async_test_client.post("/api/v1/learning/courses", json=course_data, headers=headers)
        course_id = course_response.json()["id"]

        # Create lesson
        lesson_data = {
            "title": "Introduction to the Course",
            "description": "Welcome and overview",
            "content": "This is the first lesson content...",
            "video_url": "https://example.com/lesson1-video.mp4",
            "duration": 30,
            "order": 1,
            "is_preview": True
        }

        response = await async_test_client.post(f"/api/v1/learning/courses/{course_id}/lessons", json=lesson_data, headers=headers)

        assert_successful_response(response, 201)
        data = response.json()

        assert data["title"] == lesson_data["title"]
        assert data["description"] == lesson_data["description"]
        assert data["order"] == lesson_data["order"]
        assert data["is_preview"] == lesson_data["is_preview"]

    async def test_access_lesson_without_enrollment(self, async_test_client: AsyncClient):
        """Test accessing lesson content without enrollment."""
        # Create student
        student_data = {
            "email": "no_enroll_student@example.com",
            "username": "no_enroll_student",
            "password": "password123",
            "full_name": "No Enroll Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create course and lesson
        course = await self.create_test_course()
        lesson = await self.create_test_lesson(course.id)

        # Try to access lesson content
        response = await async_test_client.get(f"/api/v1/learning/courses/{course.id}/lessons/{lesson.id}", headers=headers)

        assert_error_response(response, 403, "NOT_ENROLLED")

    async def test_access_preview_lesson_without_enrollment(self, async_test_client: AsyncClient):
        """Test accessing preview lesson without enrollment."""
        # Create course and preview lesson
        course = await self.create_test_course()
        lesson = await self.create_test_lesson(course.id, is_preview=True)

        # Access preview lesson without authentication
        response = await async_test_client.get(f"/api/v1/learning/courses/{course.id}/lessons/{lesson.id}")

        assert_successful_response(response, 200)
        data = response.json()

        assert data["title"] == lesson.title
        assert data["is_preview"] == True

    async def test_mark_lesson_complete(self, async_test_client: AsyncClient):
        """Test marking a lesson as completed."""
        # Create student and enroll in course
        student_data = {
            "email": "complete_student@example.com",
            "username": "complete_student",
            "password": "password123",
            "full_name": "Complete Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create course and lesson, then enroll
        course = await self.create_test_course()
        lesson = await self.create_test_lesson(course.id)
        await async_test_client.post(f"/api/v1/learning/courses/{course.id}/enroll", headers=headers)

        # Mark lesson as complete
        response = await async_test_client.post(
            f"/api/v1/learning/courses/{course.id}/lessons/{lesson.id}/complete",
            headers=headers
        )

        assert_successful_response(response, 200)
        data = response.json()

        assert data["completed"] == True
        assert "completed_at" in data

    async def test_get_course_progress(self, async_test_client: AsyncClient):
        """Test getting course progress for enrolled student."""
        # Create student and enroll in course
        student_data = {
            "email": "progress_student@example.com",
            "username": "progress_student",
            "password": "password123",
            "full_name": "Progress Student"
        }

        await async_test_client.post("/api/v1/auth/register", json=student_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": student_data["email"],
            "password": student_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create course with multiple lessons and enroll
        course = await self.create_test_course()
        lesson1 = await self.create_test_lesson(course.id, title="Lesson 1")
        lesson2 = await self.create_test_lesson(course.id, title="Lesson 2")
        lesson3 = await self.create_test_lesson(course.id, title="Lesson 3")

        await async_test_client.post(f"/api/v1/learning/courses/{course.id}/enroll", headers=headers)

        # Complete 2 out of 3 lessons
        await async_test_client.post(f"/api/v1/learning/courses/{course.id}/lessons/{lesson1.id}/complete", headers=headers)
        await async_test_client.post(f"/api/v1/learning/courses/{course.id}/lessons/{lesson2.id}/complete", headers=headers)

        # Get progress
        response = await async_test_client.get(f"/api/v1/learning/courses/{course.id}/progress", headers=headers)

        assert_successful_response(response, 200)
        data = response.json()

        assert data["total_lessons"] == 3
        assert data["completed_lessons"] == 2
        assert data["progress_percentage"] == 66.67  # 2/3 * 100

    async def create_test_lesson(self, course_id: str, title: str = "Test Lesson", is_preview: bool = False):
        """Helper method to create a test lesson."""
        from lyo_app.learning.models import Lesson

        lesson = Lesson(
            id="test-lesson-id",
            course_id=course_id,
            title=title,
            description="Test lesson description",
            content="Test lesson content",
            duration=30,
            order=1,
            is_preview=is_preview
        )

        self.db.add(lesson)
        await self.db.commit()
        await self.db.refresh(lesson)
        return lesson
