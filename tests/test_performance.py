"""
Performance tests for LyoBackend API endpoints.
Tests response times, throughput, and resource usage.
Enhanced with comprehensive performance testing utilities.
"""

import asyncio
import time
import pytest
from typing import List
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import (
    AsyncTestCase,
    measure_response_time,
    assert_performance_threshold,
    calculate_percentile,
    calculate_average,
    calculate_throughput,
    assert_response_time_distribution,
    assert_throughput,
    assert_error_rate
)
from tests.test_utils import (
    TestDataFactory,
    DatabaseHelper,
    AuthenticationHelper,
    PerformanceHelper,
    APIResponseValidator
)


class TestAPIPerformance(AsyncTestCase):
    """Performance tests for API endpoints."""

    @pytest.mark.performance
    async def test_user_registration_performance(self, async_test_client: AsyncClient):
        """Test user registration response time."""
        user_data = TestDataFactory.create_user_data({
            "username": "perf_test_user",
            "email": "perf_test@example.com"
        })

        response_time = await measure_response_time(
            async_test_client,
            "/api/v1/auth/register",
            method="POST",
            json=user_data
        )

        assert_performance_threshold(response_time, 0.5)
        assert async_test_client.post("/api/v1/auth/register", json=user_data).status_code in [200, 201]

    @pytest.mark.performance
    async def test_user_login_performance(self, async_test_client: AsyncClient):
        """Test user login response time."""
        # Create test user
        user_data = TestDataFactory.create_user_data({
            "username": "perf_login_user",
            "email": "perf_login@example.com"
        })
        await async_test_client.post("/api/v1/auth/register", json=user_data)

        # Test login performance
        login_data = {
            "email": user_data["email"],
            "password": user_data["password"]
        }

        response_time = await measure_response_time(
            async_test_client,
            "/api/v1/auth/login",
            method="POST",
            json=login_data
        )

        assert_performance_threshold(response_time, 0.3)

        login_response = await async_test_client.post("/api/v1/auth/login", json=login_data)
        assert login_response.status_code == 200

    @pytest.mark.performance
    async def test_course_creation_performance(self, async_test_client: AsyncClient):
        """Test course creation response time."""
        # Create and authenticate user
        user_data = TestDataFactory.create_user_data({
            "username": "perf_course_user",
            "email": "perf_course@example.com"
        })

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        course_data = TestDataFactory.create_course_data({
            "title": "Performance Test Course"
        })

        # Test course creation performance
        response_time = await measure_response_time(
            async_test_client,
            "/api/v1/learning/courses",
            method="POST",
            json=course_data,
            headers=headers
        )

        assert_performance_threshold(response_time, 0.5)

        course_response = await async_test_client.post("/api/v1/learning/courses", json=course_data, headers=headers)
        assert course_response.status_code in [200, 201]

    @pytest.mark.performance
    async def test_concurrent_user_registrations(self, async_test_client: AsyncClient):
        """Test concurrent user registrations."""
        async def register_user(user_num: int):
            user_data = TestDataFactory.create_user_data({
                "username": f"concurrent_user_{user_num}",
                "email": f"concurrent_{user_num}@example.com"
            })

            start_time = time.time()
            response = await async_test_client.post("/api/v1/auth/register", json=user_data)
            end_time = time.time()

            return {
                "user_num": user_num,
                "status_code": response.status_code,
                "execution_time": end_time - start_time
            }

        # Test with 10 concurrent registrations
        tasks = [register_user(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Validate results
        response_times = [result["execution_time"] for result in results]

        for result in results:
            assert result["status_code"] in [200, 201]

        # Assert performance distribution
        assert_response_time_distribution(response_times, max_avg=1.0, max_p95=2.0)

        # Check average response time
        avg_time = calculate_average(response_times)
        assert avg_time < 0.8, f"Average response time {avg_time:.2f}s is too high"

    @pytest.mark.performance
    async def test_database_query_performance(self, db_session: AsyncSession):
        """Test database query performance."""
        # Create test data
        for i in range(100):
            user_data = TestDataFactory.create_user_data({
                "username": f"query_test_user_{i}",
                "email": f"query_test_{i}@example.com"
            })
            await self.create_test_user(**user_data)

        # Test query performance
        from lyo_app.auth.models import User

        start_time = time.time()
        result = await db_session.execute(
            db_session.query(User).filter(User.email.like("query_test_%@example.com"))
        )
        users = result.scalars().all()
        end_time = time.time()

        execution_time = end_time - start_time
        assert_performance_threshold(execution_time, 0.1)

        assert len(users) == 100

    @pytest.mark.performance
    async def test_api_endpoint_throughput(self, async_test_client: AsyncClient):
        """Test API endpoint throughput."""
        # Create test user
        user_data = TestDataFactory.create_user_data({
            "username": "throughput_user",
            "email": "throughput@example.com"
        })

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Test throughput with multiple requests
        num_requests = 50
        execution_times = []

        for i in range(num_requests):
            response_time = await measure_response_time(
                async_test_client,
                "/api/v1/auth/profile",
                headers=headers
            )
            execution_times.append(response_time)

        # Calculate throughput metrics
        avg_time = calculate_average(execution_times)
        max_time = max(execution_times)
        min_time = min(execution_times)
        rps = calculate_throughput(num_requests, sum(execution_times))

        # Assert performance thresholds
        assert_performance_threshold(avg_time, 0.2)
        assert_performance_threshold(max_time, 0.5)
        assert_throughput(num_requests, sum(execution_times), min_rps=2.0)

        print("Throughput test results:")
        print(f"  Requests: {num_requests}")
        print(f"  Average time: {avg_time:.3f}s")
        print(f"  Max time: {max_time:.3f}s")
        print(f"  Min time: {min_time:.3f}s")
        print(f"  Requests/second: {rps:.1f}")

    @pytest.mark.performance
    async def test_feeds_performance_under_load(self, async_test_client: AsyncClient):
        """Test feeds performance under load."""
        # Create user and multiple posts
        user_data = TestDataFactory.create_user_data({
            "username": "feeds_load_user",
            "email": "feeds_load@example.com"
        })

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create 20 posts
        for i in range(20):
            post_data = {
                "content": f"Load test post {i}",
                "is_public": True,
                "tags": [f"load{i}"]
            }
            await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)

        # Test feed retrieval performance
        response_time = await measure_response_time(
            async_test_client,
            "/api/v1/feeds/posts",
            headers=headers
        )

        assert_performance_threshold(response_time, 1.0)

        # Verify all posts are returned
        response = await async_test_client.get("/api/v1/feeds/posts", headers=headers)
        data = response.json()
        assert len(data["items"]) == 20


class TestResourceUsage(AsyncTestCase):
    """Tests for resource usage monitoring."""

    @pytest.mark.performance
    async def test_memory_usage_during_bulk_operations(self, async_test_client: AsyncClient):
        """Test memory usage during bulk operations."""
        # Create bulk test data
        for i in range(100):
            user_data = TestDataFactory.create_user_data({
                "username": f"memory_test_user_{i}",
                "email": f"memory_test_{i}@example.com"
            })
            await async_test_client.post("/api/v1/auth/register", json=user_data)

        # Test bulk retrieval performance
        response_time = await measure_response_time(
            async_test_client,
            "/api/v1/auth/users"  # Assuming there's a users list endpoint
        )

        assert_performance_threshold(response_time, 0.5)

        # Verify response contains users
        response = await async_test_client.get("/api/v1/auth/users")
        data = response.json()
        assert len(data.get("items", [])) >= 100

    @pytest.mark.performance
    async def test_database_connection_pool_usage(self, async_test_client: AsyncClient):
        """Test database connection pool usage."""
        # Test multiple concurrent database operations
        async def create_user_async(user_num: int):
            user_data = TestDataFactory.create_user_data({
                "username": f"pool_test_user_{user_num}",
                "email": f"pool_test_{user_num}@example.com"
            })

            response = await async_test_client.post("/api/v1/auth/register", json=user_data)
            return response

        # Create 20 concurrent users
        tasks = [create_user_async(i) for i in range(20)]
        start_time = time.time()
        responses = await asyncio.gather(*tasks)
        end_time = time.time()

        execution_time = end_time - start_time
        assert_performance_threshold(execution_time, 2.0)

        # Verify all requests succeeded
        successful_responses = [r for r in responses if r.status_code in [200, 201]]
        assert len(successful_responses) == 20


class TestLoadTesting(AsyncTestCase):
    """Load testing scenarios."""

    @pytest.mark.performance
    @pytest.mark.slow
    async def test_sustained_load_simulation(self, async_test_client: AsyncClient):
        """Test sustained load over time."""
        # Create test user
        user_data = TestDataFactory.create_user_data({
            "username": "load_test_user",
            "email": "load_test@example.com"
        })

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Simulate sustained load for 30 seconds
        end_time = time.time() + 30
        request_count = 0
        response_times = []

        while time.time() < end_time:
            response_time = await measure_response_time(
                async_test_client,
                "/api/v1/auth/profile",
                headers=headers
            )
            response_times.append(response_time)
            request_count += 1

            # Small delay to prevent overwhelming the system
            await asyncio.sleep(0.1)

        print(f"Completed {request_count} requests in 30 seconds")
        print(f"Requests/second: {request_count/30:.1f}")

        # Assert minimum throughput
        assert request_count >= 200, f"Throughput too low: {request_count} requests in 30s"

        # Assert response time distribution
        assert_response_time_distribution(response_times, max_avg=0.5, max_p95=1.0)

    @pytest.mark.performance
    @pytest.mark.slow
    async def test_peak_load_handling(self, async_test_client: AsyncClient):
        """Test handling of peak load scenarios."""
        async def make_request(request_id: int):
            user_data = TestDataFactory.create_user_data({
                "username": f"peak_load_user_{request_id}",
                "email": f"peak_load_{request_id}@example.com"
            })

            response = await async_test_client.post("/api/v1/auth/register", json=user_data)
            return {
                "request_id": request_id,
                "status_code": response.status_code,
                "success": response.status_code in [200, 201]
            }

        # Simulate peak load with 50 concurrent requests
        tasks = [make_request(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        # Analyze results
        successful_requests = len([r for r in results if r["success"]])
        success_rate = successful_requests / len(results)

        print("Peak load test results:")
        print(f"  Total requests: {len(results)}")
        print(f"  Successful requests: {successful_requests}")
        print(f"  Success rate: {success_rate:.2%}")

        # Assert acceptable success rate
        assert success_rate >= 0.95, f"Success rate {success_rate:.2%} is below acceptable threshold"

        # Assert error rate
        assert_error_rate(results, max_error_rate=0.05)


class TestCachingPerformance(AsyncTestCase):
    """Test caching performance improvements."""

    @pytest.mark.performance
    async def test_repeated_request_caching(self, async_test_client: AsyncClient):
        """Test that repeated requests benefit from caching."""
        # Create user and some posts
        user_data = TestDataFactory.create_user_data({
            "username": "cache_test_user",
            "email": "cache_test@example.com"
        })

        await async_test_client.post("/api/v1/auth/register", json=user_data)

        login_response = await async_test_client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create a few posts
        for i in range(5):
            post_data = {
                "content": f"Cache test post {i}",
                "is_public": True
            }
            await async_test_client.post("/api/v1/feeds/posts", json=post_data, headers=headers)

        # First request
        first_response_time = await measure_response_time(
            async_test_client,
            "/api/v1/feeds/posts",
            headers=headers
        )

        # Wait a moment
        await asyncio.sleep(0.1)

        # Second request (should be faster if caching works)
        second_response_time = await measure_response_time(
            async_test_client,
            "/api/v1/feeds/posts",
            headers=headers
        )

        # Second request should be at least 20% faster (allowing for some variance)
        improvement_ratio = first_response_time / second_response_time
        assert improvement_ratio > 1.1, f"Cache improvement ratio {improvement_ratio:.2f} is below expected threshold"

        print(f"Cache performance improvement: {improvement_ratio:.2f}x faster")


class TestDatabasePerformance(AsyncTestCase):
    """Test database-specific performance."""

    @pytest.mark.performance
    async def test_bulk_insert_performance(self, async_test_client: AsyncClient):
        """Test bulk insert performance."""
        # Create multiple users in quick succession
        user_data_list = [
            TestDataFactory.create_user_data({
                "username": f"bulk_insert_user_{i}",
                "email": f"bulk_insert_{i}@example.com"
            })
            for i in range(100)
        ]

        start_time = time.time()

        for user_data in user_data_list:
            response = await async_test_client.post("/api/v1/auth/register", json=user_data)
            assert response.status_code in [200, 201]

        end_time = time.time()
        total_time = end_time - start_time

        # Should complete within reasonable time
        assert total_time < 30.0, f"Bulk insert took {total_time:.2f}s, expected < 30.0s"

        # Average time per insert
        avg_time_per_insert = total_time / len(user_data_list)
        assert avg_time_per_insert < 0.5, f"Average insert time {avg_time_per_insert:.2f}s is too high"

        print(f"Bulk insert performance: {len(user_data_list)} users in {total_time:.2f}s")
        print(f"Average time per insert: {avg_time_per_insert:.3f}s")

    @pytest.mark.performance
    async def test_complex_query_performance(self, async_test_client: AsyncClient):
        """Test complex query performance."""
        # Create users with different roles and data
        roles = ["student", "instructor", "admin"]

        for i in range(50):
            user_data = TestDataFactory.create_user_data({
                "username": f"complex_query_user_{i}",
                "email": f"complex_query_{i}@example.com",
                "role": roles[i % len(roles)]
            })
            await async_test_client.post("/api/v1/auth/register", json=user_data)

        # Test complex query (assuming endpoint exists)
        response_time = await measure_response_time(
            async_test_client,
            "/api/v1/auth/users?role=student&limit=20"
        )

        assert_performance_threshold(response_time, 0.3)

        # Verify results
        response = await async_test_client.get("/api/v1/auth/users?role=student&limit=20")
        data = response.json()
        assert len(data.get("items", [])) > 0


# Performance benchmark utilities
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
    """Generate a performance report from benchmark results."""
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
