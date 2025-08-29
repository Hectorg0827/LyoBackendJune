"""
Test utilities and helper functions for LyoBackend testing.
Provides common testing patterns and utilities.
Enhanced with comprehensive testing infrastructure.
"""

import asyncio
import json
import random
import string
import time
import uuid
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from lyo_app.core.enhanced_exceptions import APIError


class TestDataFactory:
    """Factory for creating test data."""

    @staticmethod
    def generate_random_string(length: int = 10) -> str:
        """Generate a random string of specified length."""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    @staticmethod
    def generate_uuid() -> str:
        """Generate a random UUID string."""
        return str(uuid.uuid4())

    @staticmethod
    def create_user_data(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create sample user data."""
        base_data = {
            "id": TestDataFactory.generate_uuid(),
            "username": f"testuser_{TestDataFactory.generate_random_string(8)}",
            "email": f"test_{TestDataFactory.generate_random_string(8)}@example.com",
            "password": "testpass123",
            "full_name": f"Test User {TestDataFactory.generate_random_string(5)}",
            "bio": "Test bio for testing purposes",
            "profile_image_url": f"https://example.com/avatar_{TestDataFactory.generate_random_string(5)}.jpg",
            "is_active": True,
            "is_verified": True,
            "role": "student",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if overrides:
            base_data.update(overrides)

        return base_data

    @staticmethod
    def create_course_data(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create sample course data."""
        base_data = {
            "id": TestDataFactory.generate_uuid(),
            "title": f"Test Course {TestDataFactory.generate_random_string(5)}",
            "description": f"Comprehensive test course about {TestDataFactory.generate_random_string(10)}",
            "instructor": f"Instructor {TestDataFactory.generate_random_string(5)}",
            "duration": random.randint(30, 240),
            "difficulty": random.choice(["beginner", "intermediate", "advanced"]),
            "category": random.choice(["programming", "data-science", "design", "business"]),
            "tags": [f"tag_{i}" for i in range(random.randint(1, 5))],
            "thumbnail_url": f"https://example.com/course_{TestDataFactory.generate_random_string(5)}.jpg",
            "prerequisites": [f"Prerequisite {i}" for i in range(random.randint(0, 3))],
            "learning_objectives": [f"Learn objective {i}" for i in range(random.randint(3, 8))],
            "is_published": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if overrides:
            base_data.update(overrides)

        return base_data

    @staticmethod
    def create_lesson_data(course_id: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create lesson data for testing."""
        base_data = {
            "id": TestDataFactory.generate_uuid(),
            "course_id": course_id,
            "title": f"Lesson {TestDataFactory.generate_random_string(5)}",
            "description": f"Lesson description about {TestDataFactory.generate_random_string(10)}",
            "content": f"Lesson content with detailed information about {TestDataFactory.generate_random_string(20)}",
            "video_url": f"https://example.com/video_{TestDataFactory.generate_random_string(5)}.mp4",
            "duration": random.randint(15, 90),
            "order": random.randint(1, 20),
            "is_preview": random.choice([True, False]),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if overrides:
            base_data.update(overrides)

        return base_data

    @staticmethod
    def create_post_data(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create sample post data."""
        base_data = {
            "id": TestDataFactory.generate_uuid(),
            "content": f"Test post content about {TestDataFactory.generate_random_string(15)}",
            "image_urls": [f"https://example.com/image_{i}.jpg" for i in range(random.randint(0, 3))],
            "video_url": random.choice([None, f"https://example.com/video_{TestDataFactory.generate_random_string(5)}.mp4"]),
            "tags": [f"tag_{i}" for i in range(random.randint(1, 5))],
            "is_public": random.choice([True, False]),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if overrides:
            base_data.update(overrides)

        return base_data

    @staticmethod
    def create_comment_data(post_id: str, author_id: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create comment data for testing."""
        base_data = {
            "id": TestDataFactory.generate_uuid(),
            "post_id": post_id,
            "author_id": author_id,
            "content": f"Test comment about {TestDataFactory.generate_random_string(10)}",
            "parent_id": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if overrides:
            base_data.update(overrides)

        return base_data

    @staticmethod
    def create_study_group_data(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create sample study group data."""
        base_data = {
            "id": TestDataFactory.generate_uuid(),
            "name": f"Study Group {TestDataFactory.generate_random_string(5)}",
            "description": f"Study group for {TestDataFactory.generate_random_string(10)}",
            "creator_id": TestDataFactory.generate_uuid(),
            "max_members": random.randint(5, 50),
            "is_private": random.choice([True, False]),
            "tags": [f"study_tag_{i}" for i in range(random.randint(1, 4))],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        if overrides:
            base_data.update(overrides)

        return base_data

    @staticmethod
    def create_bulk_users(count: int) -> List[Dict[str, Any]]:
        """Create multiple user data entries."""
        return [TestDataFactory.create_user_data() for _ in range(count)]

    @staticmethod
    def create_bulk_courses(count: int) -> List[Dict[str, Any]]:
        """Create multiple course data entries."""
        return [TestDataFactory.create_course_data() for _ in range(count)]


class APIResponseValidator:
    """Validator for API responses."""

    @staticmethod
    def validate_success_response(response_data: Dict[str, Any],
                                expected_fields: Optional[List[str]] = None) -> None:
        """Validate a successful API response."""
        assert "data" in response_data
        if expected_fields:
            for field in expected_fields:
                assert field in response_data["data"]

    @staticmethod
    def validate_error_response(response_data: Dict[str, Any],
                              expected_code: str,
                              expected_message: Optional[str] = None) -> None:
        """Validate an error API response."""
        assert "error" in response_data
        error = response_data["error"]
        assert error["code"] == expected_code
        if expected_message:
            assert expected_message in error["message"]

    @staticmethod
    def validate_pagination_response(response_data: Dict[str, Any],
                                   expected_fields: Optional[List[str]] = None) -> None:
        """Validate a paginated API response."""
        assert "data" in response_data
        assert "pagination" in response_data

        pagination = response_data["pagination"]
        required_pagination_fields = ["page", "per_page", "total", "total_pages"]
        for field in required_pagination_fields:
            assert field in pagination

        if expected_fields and response_data["data"]:
            for field in expected_fields:
                assert field in response_data["data"][0]

    @staticmethod
    def validate_user_response(user_data: Dict[str, Any]) -> None:
        """Validate user response data."""
        required_fields = ["id", "username", "email", "full_name"]
        for field in required_fields:
            assert field in user_data

    @staticmethod
    def validate_course_response(course_data: Dict[str, Any]) -> None:
        """Validate course response data."""
        required_fields = ["id", "title", "description", "instructor", "difficulty"]
        for field in required_fields:
            assert field in course_data

    @staticmethod
    def assert_success_response(response, expected_status: int = 200, required_keys: Optional[List[str]] = None):
        """Assert that API response is successful."""
        assert response.status_code == expected_status

        if required_keys:
            data = response.json()
            for key in required_keys:
                assert key in data, f"Required key '{key}' not found in response"

    @staticmethod
    def assert_error_response(response, expected_status: int = 400, expected_error_code: Optional[str] = None):
        """Assert that API response contains an error."""
        assert response.status_code == expected_status
        data = response.json()
        assert "error" in data

        if expected_error_code:
            assert data["error"]["code"] == expected_error_code

    @staticmethod
    def assert_paginated_response(
        response,
        expected_status: int = 200,
        min_items: Optional[int] = None,
        max_items: Optional[int] = None
    ):
        """Assert that response contains proper pagination data."""
        assert response.status_code == expected_status
        data = response.json()

        required_keys = ["items", "total", "page", "page_size", "has_next", "has_prev"]
        for key in required_keys:
            assert key in data, f"Required pagination key '{key}' not found"

        if min_items is not None:
            assert len(data["items"]) >= min_items

        if max_items is not None:
            assert len(data["items"]) <= max_items

    @staticmethod
    def assert_user_response(response, expected_user_data: Optional[Dict[str, Any]] = None):
        """Assert that response contains valid user data."""
        APIResponseValidator.assert_success_response(response)

        data = response.json()
        user_keys = ["id", "email", "username", "full_name"]

        if isinstance(data, dict) and "user" in data:
            user_data = data["user"]
        else:
            user_data = data

        for key in user_keys:
            assert key in user_data

        # Check password is not included
        assert "password" not in user_data
        assert "hashed_password" not in user_data

        if expected_user_data:
            for key, value in expected_user_data.items():
                if key in user_data:
                    assert user_data[key] == value

    @staticmethod
    def assert_course_response(response, expected_course_data: Optional[Dict[str, Any]] = None):
        """Assert that response contains valid course data."""
        APIResponseValidator.assert_success_response(response)

        data = response.json()
        course_keys = ["id", "title", "description", "instructor", "duration", "difficulty"]

        if isinstance(data, dict) and "course" in data:
            course_data = data["course"]
        else:
            course_data = data

        for key in course_keys:
            assert key in course_data

        if expected_course_data:
            for key, value in expected_course_data.items():
                if key in course_data:
                    assert course_data[key] == value

    @staticmethod
    def assert_post_response(response, expected_post_data: Optional[Dict[str, Any]] = None):
        """Assert that response contains valid post data."""
        APIResponseValidator.assert_success_response(response)

        data = response.json()
        post_keys = ["id", "content", "author", "created_at"]

        if isinstance(data, dict) and "post" in data:
            post_data = data["post"]
        else:
            post_data = data

        for key in post_keys:
            assert key in post_data

        # Validate author data
        assert "author" in post_data
        author_keys = ["id", "username", "full_name"]
        for key in author_keys:
            assert key in post_data["author"]

        if expected_post_data:
            for key, value in expected_post_data.items():
                if key in post_data and key != "author":
                    assert post_data[key] == value


class DatabaseHelper:
    """Helper functions for database operations in tests."""

    @staticmethod
    async def create_test_user(session: AsyncSession, **user_data) -> Dict[str, Any]:
        """Create a test user in the database."""
        from lyo_app.auth.models import User
        from lyo_app.auth.security import get_password_hash

        # Hash password if provided as plain text
        if "password" in user_data and not user_data.get("hashed_password"):
            user_data["hashed_password"] = get_password_hash(user_data["password"])
            user_data.pop("password", None)

        user = User(**user_data)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name
        }

    @staticmethod
    async def create_test_course(session: AsyncSession, **course_data) -> Dict[str, Any]:
        """Create a test course in the database."""
        from lyo_app.learning.models import Course

        course = Course(**course_data)
        session.add(course)
        await session.commit()
        await session.refresh(course)

        return {
            "id": course.id,
            "title": course.title,
            "description": course.description,
            "instructor": course.instructor
        }

    @staticmethod
    async def create_test_post(session: AsyncSession, author_id: str, **post_data) -> Dict[str, Any]:
        """Create a test post in the database."""
        from lyo_app.feeds.models import Post

        post_data["author_id"] = author_id
        post = Post(**post_data)
        session.add(post)
        await session.commit()
        await session.refresh(post)

        return {
            "id": post.id,
            "content": post.content,
            "author_id": post.author_id
        }

    @staticmethod
    async def enroll_user_in_course(session: AsyncSession, user_id: str, course_id: str) -> Any:
        """Enroll a user in a course."""
        from lyo_app.learning.models import CourseEnrollment

        enrollment = CourseEnrollment(
            id=TestDataFactory.generate_uuid(),
            user_id=user_id,
            course_id=course_id,
            enrolled_at=datetime.utcnow()
        )

        session.add(enrollment)
        await session.commit()
        await session.refresh(enrollment)
        return enrollment

    @staticmethod
    async def create_lesson_completion(session: AsyncSession, user_id: str, lesson_id: str) -> Any:
        """Mark a lesson as completed for a user."""
        from lyo_app.learning.models import LessonCompletion

        completion = LessonCompletion(
            id=TestDataFactory.generate_uuid(),
            user_id=user_id,
            lesson_id=lesson_id,
            completed_at=datetime.utcnow()
        )

        session.add(completion)
        await session.commit()
        await session.refresh(completion)
        return completion

    @staticmethod
    async def bulk_create_users(session: AsyncSession, users_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create multiple users in bulk."""
        users = []
        for user_data in users_data:
            user = await DatabaseHelper.create_test_user(session, **user_data)
            users.append(user)
        return users


class AuthenticationHelper:
    """Helper functions for authentication in tests."""

    @staticmethod
    async def authenticate_user(client: Union[TestClient, AsyncClient], email: str, password: str) -> str:
        """Authenticate a user and return access token."""
        login_data = {"email": email, "password": password}

        if isinstance(client, TestClient):
            response = client.post("/api/v1/auth/login", json=login_data)
        else:
            response = await client.post("/api/v1/auth/login", json=login_data)

        assert response.status_code == 200
        data = response.json()
        return data["access_token"]

    @staticmethod
    def get_auth_headers(token: str) -> Dict[str, str]:
        """Get authorization headers."""
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    async def create_authenticated_user(
        client: Union[TestClient, AsyncClient],
        session: AsyncSession,
        user_data: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """Create a user and authenticate them, returning user data and token."""
        if user_data is None:
            user_data = TestDataFactory.create_user_data()

        # Create user in database
        user = await DatabaseHelper.create_test_user(session, **user_data)

        # Authenticate user
        token = await AuthenticationHelper.authenticate_user(
            client, user_data["email"], user_data["password"]
        )

        return user, token


class MockHelper:
    """Helper functions for creating mocks."""

    @staticmethod
    def create_mock_redis():
        """Create a mock Redis client."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.exists.return_value = 0
        mock_redis.expire.return_value = True
        mock_redis.ping.return_value = True
        return mock_redis

    @staticmethod
    def create_mock_ai_client():
        """Create a mock AI client."""
        mock_ai = AsyncMock()
        mock_ai.generate_response.return_value = {
            "response": "Mock AI response",
            "model": "mock-gemini",
            "tokens_used": 100
        }
        mock_ai.analyze_content.return_value = {
            "sentiment": "positive",
            "topics": ["test"],
            "confidence": 0.95
        }
        return mock_ai

    @staticmethod
    def create_mock_external_api():
        """Create a mock external API client."""
        mock_api = AsyncMock()
        mock_api.get.return_value = {"status": "success", "data": []}
        mock_api.post.return_value = {"status": "created", "id": 1}
        return mock_api

    @staticmethod
    def create_mock_user(**overrides) -> Mock:
        """Create a mock user object."""
        from lyo_app.auth.models import User

        mock_user = Mock(spec=User)
        default_attrs = {
            "id": TestDataFactory.generate_uuid(),
            "email": "mock@example.com",
            "username": "mockuser",
            "full_name": "Mock User",
            "is_active": True,
            "is_verified": True,
            "role": "student"
        }

        default_attrs.update(overrides)

        for key, value in default_attrs.items():
            setattr(mock_user, key, value)

        return mock_user

    @staticmethod
    def create_mock_course(**overrides) -> Mock:
        """Create a mock course object."""
        from lyo_app.learning.models import Course

        mock_course = Mock(spec=Course)
        default_attrs = {
            "id": TestDataFactory.generate_uuid(),
            "title": "Mock Course",
            "description": "Mock course description",
            "instructor": "Mock Instructor",
            "duration": 60,
            "difficulty": "beginner",
            "is_published": True
        }

        default_attrs.update(overrides)

        for key, value in default_attrs.items():
            setattr(mock_course, key, value)

        return mock_course


class PerformanceHelper:
    """Helper functions for performance testing."""

    @staticmethod
    def measure_execution_time(func, *args, **kwargs) -> tuple:
        """Measure execution time of a function."""
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        return result, execution_time

    @staticmethod
    async def measure_async_execution_time(coro) -> tuple:
        """Measure execution time of an async function."""
        start_time = time.time()
        result = await coro
        end_time = time.time()
        execution_time = end_time - start_time
        return result, execution_time

    @staticmethod
    def assert_performance_threshold(execution_time: float, threshold: float):
        """Assert that execution time is within acceptable threshold."""
        assert execution_time <= threshold, f"Execution time {execution_time:.2f}s exceeds threshold {threshold:.2f}s"

    @staticmethod
    def calculate_percentile(response_times: List[float], percentile: float) -> float:
        """Calculate percentile from response times."""
        sorted_times = sorted(response_times)
        index = int(len(sorted_times) * percentile / 100)
        return sorted_times[min(index, len(sorted_times) - 1)]

    @staticmethod
    def calculate_average(response_times: List[float]) -> float:
        """Calculate average response time."""
        return sum(response_times) / len(response_times)

    @staticmethod
    def calculate_throughput(total_requests: int, total_time: float) -> float:
        """Calculate requests per second."""
        return total_requests / total_time


class TestCase:
    """Base test case with common utilities."""

    def setup_method(self):
        """Setup method called before each test."""
        self.start_time = time.time()

    def teardown_method(self):
        """Teardown method called after each test."""
        end_time = time.time()
        execution_time = end_time - self.start_time
        print(f"Test execution time: {execution_time:.2f}s")

    def assert_response_time(self, response, max_time: float = 1.0):
        """Assert that response time is within acceptable limit."""
        assert hasattr(response, 'elapsed'), "Response object must have elapsed time"
        execution_time = response.elapsed.total_seconds()
        assert execution_time <= max_time, f"Response time {execution_time:.2f}s exceeds {max_time:.2f}s"


# Custom pytest markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "api: marks tests as API tests")
    config.addinivalue_line("markers", "performance: marks tests as performance tests")
    config.addinivalue_line("markers", "security: marks tests as security tests")


# Test data constants
TEST_USERS = [
    {
        "username": "testuser1",
        "email": "test1@example.com",
        "password": "testpass123",
        "full_name": "Test User 1"
    },
    {
        "username": "testuser2",
        "email": "test2@example.com",
        "password": "testpass123",
        "full_name": "Test User 2"
    }
]

TEST_COURSES = [
    {
        "title": "Python Basics",
        "description": "Learn Python fundamentals",
        "instructor": "John Doe",
        "duration": 60,
        "difficulty": "beginner"
    },
    {
        "title": "Advanced Python",
        "description": "Master advanced Python concepts",
        "instructor": "Jane Smith",
        "duration": 120,
        "difficulty": "advanced"
    }
]


# Utility functions
def generate_random_email() -> str:
    """Generate a random email address."""
    return f"test_{TestDataFactory.generate_random_string(8)}@example.com"


def generate_random_username() -> str:
    """Generate a random username."""
    return f"user_{TestDataFactory.generate_random_string(8)}"


def create_test_user_payload(**overrides) -> Dict[str, Any]:
    """Create a test user payload for API requests."""
    return TestDataFactory.create_user_data(overrides)


def create_test_course_payload(**overrides) -> Dict[str, Any]:
    """Create a test course payload for API requests."""
    return TestDataFactory.create_course_data(overrides)


def assert_response_contains_data(response, data_keys: List[str]):
    """Assert that response contains specified data keys."""
    response_data = response.json()
    for key in data_keys:
        assert key in response_data, f"Response missing required key: {key}"


def assert_response_data_matches(response, expected_data: Dict[str, Any]):
    """Assert that response data matches expected values."""
    response_data = response.json()
    for key, expected_value in expected_data.items():
        assert key in response_data, f"Response missing key: {key}"
        assert response_data[key] == expected_value, f"Value mismatch for {key}: expected {expected_value}, got {response_data[key]}"


# Performance test utilities
def benchmark_endpoint(
    client: AsyncClient,
    endpoint: str,
    method: str = "GET",
    num_requests: int = 100,
    concurrent: bool = True,
    **kwargs
) -> dict:
    """Benchmark an endpoint with multiple requests."""
    async def single_request():
        if method.upper() == "GET":
            return await client.get(endpoint, **kwargs)
        elif method.upper() == "POST":
            return await client.post(endpoint, **kwargs)
        # Add other methods as needed

    start_time = time.time()

    if concurrent:
        # Run concurrently
        tasks = [single_request() for _ in range(num_requests)]
        responses = asyncio.run(asyncio.gather(*tasks))
    else:
        # Run sequentially
        responses = []
        for _ in range(num_requests):
            response = asyncio.run(single_request())
            responses.append(response)

    end_time = time.time()
    total_time = end_time - start_time

    return {
        "total_requests": num_requests,
        "total_time": total_time,
        "avg_response_time": total_time / num_requests,
        "requests_per_second": num_requests / total_time,
        "responses": responses
    }


def generate_performance_report(results: dict) -> str:
    """Generate performance test report."""
    if not results:
        return "No performance data available"

    report = f"""
Performance Test Report
=======================

Total Requests: {results['total_requests']}
Total Time: {results['total_time']:.2f}s
Average Response Time: {results['avg_response_time']:.3f}s
Requests/Second: {results['requests_per_second']:.1f}

Status Code Distribution:
"""

    status_counts = {}
    for response in results['responses']:
        status = response.status_code
        status_counts[status] = status_counts.get(status, 0) + 1

    for status, count in status_counts.items():
        percentage = (count / len(results['responses'])) * 100
        report += f"  {status}: {count} ({percentage:.1f}%)\n"

    return report
