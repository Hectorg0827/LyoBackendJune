# LyoBackend Testing Infrastructure

Comprehensive testing framework for LyoBackend with enhanced utilities, performance testing, and automated test management.

## Overview

This testing infrastructure provides:

- **Comprehensive Test Utilities**: Enhanced test data factories, API validators, database helpers
- **Performance Testing**: Built-in benchmarking and load testing capabilities
- **Async Testing Support**: Full async/await support with proper fixtures
- **Mock Management**: Intelligent mocking for external services
- **Coverage Reporting**: Detailed coverage analysis with multiple report formats
- **Test Configuration**: Environment-based test configuration management

## Quick Start

### Running Tests

```bash
# Run all tests
python run_tests.py all

# Run specific test types
python run_tests.py unit
python run_tests.py integration
python run_tests.py api
python run_tests.py performance

# Run with coverage
python run_tests.py coverage

# Run specific test file
python run_tests.py --test-path tests/test_auth.py
```

### Using Test Utilities

```python
from tests.test_utils import TestDataFactory, APIResponseValidator, AuthenticationHelper

# Create test data
user_data = TestDataFactory.create_user_data()
course_data = TestDataFactory.create_course_data()

# Validate API responses
APIResponseValidator.validate_success_response(response_data)
APIResponseValidator.assert_user_response(response)

# Handle authentication in tests
user, token = await AuthenticationHelper.create_authenticated_user(client, session)
```

## Test Structure

```
tests/
├── conftest.py              # Enhanced test fixtures and configuration
├── test_utils.py            # Comprehensive testing utilities
├── test_config.py           # Test environment configuration
├── test_auth.py             # Authentication endpoint tests
├── test_learning.py         # Learning module tests
├── test_feeds.py            # Social feeds tests
├── test_performance.py      # Performance and load testing
└── test_*.py               # Additional test files
```

## Configuration

### pytest.ini

Enhanced pytest configuration with:

- **Coverage Settings**: 80% minimum coverage requirement
- **Custom Markers**: Specialized test categorization
- **Async Support**: Automatic async test detection
- **Logging**: Structured test logging

### Test Configuration

```python
from tests.test_config import configure_test_environment, TestEnvironment

# Configure for different environments
configure_test_environment(
    environment=TestEnvironment.UNIT,
    database_type=DatabaseType.MEMORY,
    use_real_redis=False
)
```

## Test Categories

### Unit Tests (`-m unit`)

- Test individual functions and classes
- Use mocks for external dependencies
- Fast execution, isolated components

### Integration Tests (`-m integration`)

- Test component interactions
- Use test database
- Validate data flow between modules

### API Tests (`-m api`)

- Test REST API endpoints
- Full request/response validation
- Authentication and authorization

### Performance Tests (`-m performance`)

- Benchmark endpoint response times
- Load testing with concurrent requests
- Memory and resource usage analysis

### Security Tests (`-m security`)

- Authentication bypass attempts
- Input validation testing
- Rate limiting verification

## Test Utilities

### TestDataFactory

Generate realistic test data:

```python
# Create user data
user = TestDataFactory.create_user_data({
    "email": "custom@example.com",
    "role": "instructor"
})

# Create course with lessons
course = TestDataFactory.create_course_data()
lesson = TestDataFactory.create_lesson_data(course["id"])

# Bulk data creation
users = TestDataFactory.create_bulk_users(50)
```

### APIResponseValidator

Validate API responses:

```python
# Validate successful responses
APIResponseValidator.assert_success_response(response, 200, ["id", "name"])

# Validate paginated responses
APIResponseValidator.assert_paginated_response(response, min_items=10)

# Validate user data
APIResponseValidator.assert_user_response(response, expected_user_data)
```

### DatabaseHelper

Database operations in tests:

```python
# Create test data
user = await DatabaseHelper.create_test_user(session, **user_data)
course = await DatabaseHelper.create_test_course(session, **course_data)

# Handle relationships
await DatabaseHelper.enroll_user_in_course(session, user["id"], course["id"])
```

### AuthenticationHelper

Handle authentication in tests:

```python
# Authenticate user
token = await AuthenticationHelper.authenticate_user(client, email, password)

# Create and authenticate user
user, token = await AuthenticationHelper.create_authenticated_user(client, session)

# Get auth headers
headers = AuthenticationHelper.get_auth_headers(token)
```

### PerformanceHelper

Performance testing utilities:

```python
# Measure execution time
result, time_taken = PerformanceHelper.measure_execution_time(func, *args)

# Assert performance threshold
PerformanceHelper.assert_performance_threshold(time_taken, 1.0)

# Calculate percentiles
p95 = PerformanceHelper.calculate_percentile(response_times, 95)
```

## Mock Management

### MockHelper

Create intelligent mocks:

```python
# Mock Redis
mock_redis = MockHelper.create_mock_redis()

# Mock AI client
mock_ai = MockHelper.create_mock_ai_client()

# Mock user object
mock_user = MockHelper.create_mock_user(id="123", email="test@example.com")
```

## Performance Testing

### Running Performance Tests

```bash
# Run performance tests
python run_tests.py performance

# Load test specific endpoint
python run_tests.py load --endpoint /api/v1/courses --num-requests 1000 --concurrent 50
```

### Performance Benchmarks

```python
@pytest.mark.performance
class TestAPIPerformance:
    async def test_course_creation_performance(self, client, session):
        """Test course creation performance."""
        course_data = TestDataFactory.create_course_data()

        start_time = time.time()
        response = await client.post("/api/v1/courses", json=course_data)
        end_time = time.time()

        assert response.status_code == 201
        PerformanceHelper.assert_performance_threshold(end_time - start_time, 0.5)
```

## Coverage Reporting

### Generate Coverage Reports

```bash
# Terminal coverage report
python run_tests.py coverage

# HTML coverage report
pytest --cov=lyo_app --cov-report=html

# Check minimum coverage
python run_tests.py check-coverage --min-coverage 85
```

### Coverage Configuration

- **Minimum Coverage**: 80%
- **Excluded Files**: Test files, migrations, cache directories
- **Report Types**: Terminal, HTML, XML

## Test Fixtures

### Enhanced conftest.py

Provides comprehensive fixtures:

```python
@pytest.fixture
async def test_session():
    """Async database session for tests."""
    async with get_test_session() as session:
        yield session

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return MockHelper.create_mock_redis()

@pytest.fixture
async def authenticated_client(client, test_session):
    """Client with authenticated user."""
    user, token = await AuthenticationHelper.create_authenticated_user(client, test_session)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
```

## Environment Configuration

### Test Environments

```python
from tests.test_config import configure_unit_tests, configure_performance_tests

# Unit testing configuration
configure_unit_tests()

# Performance testing configuration
configure_performance_tests()
```

### Environment Variables

```bash
# Database configuration
export TEST_DATABASE_URL="postgresql://test:test@localhost/lyo_test"

# Redis configuration
export TEST_REDIS_URL="redis://localhost:6379"
export TEST_REDIS_DB=1

# AI service configuration
export TEST_AI_API_KEY="your-api-key"
export TEST_AI_MODEL="gemini-pro"

# Performance settings
export TEST_PERFORMANCE_THRESHOLD=2.0
export TEST_LOAD_USERS=1000
export TEST_CONCURRENT_REQUESTS=50

# Logging
export TEST_LOG_LEVEL="DEBUG"
export TEST_LOG_TO_FILE="true"
```

## Custom Test Markers

### Available Markers

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.api` - API tests
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.security` - Security tests
- `@pytest.mark.auth` - Authentication tests
- `@pytest.mark.learning` - Learning module tests
- `@pytest.mark.feeds` - Social feeds tests
- `@pytest.mark.database` - Database tests
- `@pytest.mark.redis` - Redis-dependent tests
- `@pytest.mark.ai` - AI service tests
- `@pytest.mark.async` - Async tests
- `@pytest.mark.slow` - Slow-running tests

### Using Markers

```python
@pytest.mark.unit
@pytest.mark.async
async def test_user_creation_async(test_session):
    """Test async user creation."""
    pass

@pytest.mark.performance
@pytest.mark.slow
def test_high_load_scenario():
    """Test under high load conditions."""
    pass
```

## Test Data Management

### Test Data Constants

```python
from tests.test_utils import TEST_USERS, TEST_COURSES

def test_with_preset_data():
    """Test using preset test data."""
    user = TEST_USERS[0]
    course = TEST_COURSES[0]
```

### Dynamic Test Data

```python
def test_dynamic_data_generation():
    """Test with dynamically generated data."""
    user = TestDataFactory.create_user_data()
    course = TestDataFactory.create_course_data()

    # Use generated data in test
    assert user["email"].endswith("@example.com")
    assert "title" in course
```

## Error Handling in Tests

### Testing Error Responses

```python
def test_invalid_login(client):
    """Test invalid login error handling."""
    response = client.post("/api/v1/auth/login", json={
        "email": "invalid@example.com",
        "password": "wrong"
    })

    APIResponseValidator.assert_error_response(response, 401, "INVALID_CREDENTIALS")
```

### Testing Validation Errors

```python
def test_user_validation(client):
    """Test user input validation."""
    response = client.post("/api/v1/users", json={
        "email": "invalid-email",
        "password": "123"
    })

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
```

## Continuous Integration

### CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Run tests
        run: python run_tests.py all
      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          file: ./coverage.xml
```

## Best Practices

### Test Organization

1. **Group related tests** in classes
2. **Use descriptive test names** that explain what is being tested
3. **Keep tests focused** on a single behavior
4. **Use fixtures** for common setup/teardown
5. **Mock external dependencies** appropriately

### Test Naming Convention

```python
# Good
def test_user_creation_with_valid_data()
def test_course_enrollment_for_existing_user()
def test_api_returns_404_for_nonexistent_resource()

# Avoid
def test_user()
def test_course()
def test_api()
```

### Async Testing

```python
@pytest.mark.asyncio
async def test_async_operation(test_session):
    """Test async database operations."""
    user = await DatabaseHelper.create_test_user(test_session, email="test@example.com")
    assert user["email"] == "test@example.com"
```

### Performance Testing Best Practices

```python
@pytest.mark.performance
def test_endpoint_performance(client):
    """Test endpoint performance under load."""
    results = benchmark_endpoint(
        client, "/api/v1/courses",
        num_requests=100,
        concurrent=True
    )

    assert results["avg_response_time"] < 1.0
    assert results["requests_per_second"] > 10
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure test utilities are properly imported
2. **Database Connection**: Check test database configuration
3. **Async Test Failures**: Use `@pytest.mark.asyncio` decorator
4. **Mock Issues**: Verify mock setup and cleanup

### Debug Mode

```bash
# Run tests in debug mode
pytest -v -s --pdb

# Run specific failing test
pytest tests/test_auth.py::TestAuthEndpoints::test_login -v -s
```

## Contributing

### Adding New Tests

1. Create test file in `tests/` directory
2. Use appropriate test markers
3. Follow naming conventions
4. Add comprehensive docstrings
5. Include edge cases and error scenarios

### Extending Test Utilities

1. Add new methods to existing utility classes
2. Create new utility classes for specific domains
3. Update test configuration as needed
4. Document new utilities in this README

## Support

For questions or issues with the testing infrastructure:

1. Check this documentation first
2. Review existing test examples
3. Run tests with verbose output: `python run_tests.py all --verbose`
4. Check pytest documentation for advanced features

---

**Last Updated**: December 2024
**Test Coverage**: 80% minimum required
**Python Version**: 3.9+
