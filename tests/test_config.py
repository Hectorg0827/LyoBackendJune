"""
Test configuration and environment setup for LyoBackend testing.
Provides centralized configuration for all test environments.
"""

import os
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum


class TestEnvironment(Enum):
    """Test environment types."""
    UNIT = "unit"
    INTEGRATION = "integration"
    API = "api"
    PERFORMANCE = "performance"
    E2E = "e2e"


class DatabaseType(Enum):
    """Database types for testing."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MEMORY = "memory"


@dataclass
class TestConfig:
    """Comprehensive test configuration."""

    # Environment settings
    environment: TestEnvironment = TestEnvironment.UNIT
    database_type: DatabaseType = DatabaseType.SQLITE
    use_real_redis: bool = False
    use_real_ai: bool = False

    # Database settings
    database_url: Optional[str] = None
    test_database_name: str = "lyo_app_test"

    # Redis settings
    redis_url: Optional[str] = None
    redis_test_db: int = 1

    # AI service settings
    ai_api_key: Optional[str] = None
    ai_model: str = "gemini-pro"

    # Performance testing settings
    performance_threshold: float = 1.0  # seconds
    load_test_users: int = 100
    concurrent_requests: int = 10

    # Test data settings
    generate_test_data: bool = True
    test_data_count: Dict[str, int] = field(default_factory=lambda: {
        "users": 10,
        "courses": 5,
        "posts": 20,
        "comments": 50
    })

    # Logging settings
    log_level: str = "INFO"
    log_to_file: bool = False
    log_file_path: Optional[str] = None

    # Coverage settings
    coverage_enabled: bool = True
    coverage_min_percentage: float = 80.0
    coverage_report_types: list = field(default_factory=lambda: ["term", "html", "xml"])

    # Async settings
    async_mode: str = "auto"
    event_loop_policy: Optional[str] = None

    def __post_init__(self):
        """Initialize configuration with environment variables and defaults."""
        self._load_from_environment()
        self._set_defaults()

    def _load_from_environment(self):
        """Load configuration from environment variables."""
        # Database configuration
        self.database_url = os.getenv("TEST_DATABASE_URL", self.database_url)
        self.test_database_name = os.getenv("TEST_DATABASE_NAME", self.test_database_name)

        # Redis configuration
        self.redis_url = os.getenv("TEST_REDIS_URL", self.redis_url)
        self.redis_test_db = int(os.getenv("TEST_REDIS_DB", self.redis_test_db))

        # AI configuration
        self.ai_api_key = os.getenv("TEST_AI_API_KEY", self.ai_api_key)
        self.ai_model = os.getenv("TEST_AI_MODEL", self.ai_model)

        # Performance settings
        self.performance_threshold = float(os.getenv("TEST_PERFORMANCE_THRESHOLD", self.performance_threshold))
        self.load_test_users = int(os.getenv("TEST_LOAD_USERS", self.load_test_users))
        self.concurrent_requests = int(os.getenv("TEST_CONCURRENT_REQUESTS", self.concurrent_requests))

        # Logging
        self.log_level = os.getenv("TEST_LOG_LEVEL", self.log_level)
        self.log_to_file = os.getenv("TEST_LOG_TO_FILE", "false").lower() == "true"
        self.log_file_path = os.getenv("TEST_LOG_FILE", self.log_file_path)

        # Coverage
        self.coverage_enabled = os.getenv("TEST_COVERAGE_ENABLED", "true").lower() == "true"
        self.coverage_min_percentage = float(os.getenv("TEST_COVERAGE_MIN", self.coverage_min_percentage))

    def _set_defaults(self):
        """Set default values based on environment."""
        if not self.database_url:
            if self.database_type == DatabaseType.SQLITE:
                self.database_url = f"sqlite:///./{self.test_database_name}.db"
            elif self.database_type == DatabaseType.POSTGRESQL:
                self.database_url = f"postgresql://test:test@localhost/{self.test_database_name}"
            elif self.database_type == DatabaseType.MEMORY:
                self.database_url = "sqlite:///:memory:"

        if not self.redis_url:
            self.redis_url = "redis://localhost:6379"

        if not self.log_file_path:
            self.log_file_path = f"logs/test_{self.environment.value}.log"

    def get_database_url(self) -> str:
        """Get the appropriate database URL for the current environment."""
        return self.database_url

    def get_redis_url(self) -> str:
        """Get the Redis URL with test database."""
        if self.use_real_redis:
            return f"{self.redis_url}/{self.redis_test_db}"
        return None

    def should_use_mocks(self, service: str) -> bool:
        """Determine if a service should use mocks."""
        mock_settings = {
            "redis": not self.use_real_redis,
            "ai": not self.use_real_ai,
        }
        return mock_settings.get(service, True)

    def get_performance_settings(self) -> Dict[str, Any]:
        """Get performance testing settings."""
        return {
            "threshold": self.performance_threshold,
            "load_users": self.load_test_users,
            "concurrent_requests": self.concurrent_requests,
        }

    def get_coverage_settings(self) -> Dict[str, Any]:
        """Get coverage configuration."""
        return {
            "enabled": self.coverage_enabled,
            "min_percentage": self.coverage_min_percentage,
            "report_types": self.coverage_report_types,
        }


class TestEnvironmentManager:
    """Manages test environment setup and teardown."""

    def __init__(self, config: TestConfig):
        self.config = config
        self._setup_complete = False
        self._resources = {}

    async def setup(self):
        """Setup the test environment."""
        if self._setup_complete:
            return

        # Create necessary directories
        self._create_directories()

        # Setup logging
        self._setup_logging()

        # Setup database
        await self._setup_database()

        # Setup Redis if needed
        if self.config.use_real_redis:
            await self._setup_redis()

        # Setup AI services if needed
        if self.config.use_real_ai:
            await self._setup_ai_services()

        self._setup_complete = True

    async def teardown(self):
        """Clean up the test environment."""
        if not self._setup_complete:
            return

        # Clean up resources in reverse order
        for resource_name, cleanup_func in reversed(list(self._resources.items())):
            try:
                if asyncio.iscoroutinefunction(cleanup_func):
                    await cleanup_func()
                else:
                    cleanup_func()
            except Exception as e:
                print(f"Error cleaning up {resource_name}: {e}")

        self._resources.clear()
        self._setup_complete = False

    def _create_directories(self):
        """Create necessary directories for testing."""
        directories = [
            Path("logs"),
            Path("htmlcov"),
            Path("test_reports"),
            Path(".pytest_cache"),
        ]

        for directory in directories:
            directory.mkdir(exist_ok=True)

    def _setup_logging(self):
        """Setup logging configuration."""
        import logging

        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s [%(levelname)8s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        if self.config.log_to_file:
            file_handler = logging.FileHandler(self.config.log_file_path)
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)8s] %(name)s: %(message)s'
            ))
            logging.getLogger().addHandler(file_handler)

    async def _setup_database(self):
        """Setup test database."""
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        database_url = self.config.get_database_url()

        # Create async engine
        engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
        )

        # Create session factory
        async_session_factory = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        self._resources["database_engine"] = engine
        self._resources["async_session_factory"] = async_session_factory

        # Store cleanup function
        async def cleanup_database():
            await engine.dispose()

        self._resources["database_cleanup"] = cleanup_database

    async def _setup_redis(self):
        """Setup Redis connection."""
        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError("redis package is required for real Redis testing")

        redis_url = self.config.get_redis_url()
        redis_client = redis.from_url(redis_url)

        self._resources["redis_client"] = redis_client

        # Store cleanup function
        async def cleanup_redis():
            await redis_client.aclose()

        self._resources["redis_cleanup"] = cleanup_redis

    async def _setup_ai_services(self):
        """Setup AI services."""
        # This would be implemented based on the specific AI service being used
        # For now, just store a placeholder
        self._resources["ai_client"] = None

    def get_resource(self, name: str):
        """Get a test resource by name."""
        return self._resources.get(name)

    async def __aenter__(self):
        """Async context manager entry."""
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.teardown()


# Global test configuration instance
test_config = TestConfig()

# Environment manager instance
env_manager = TestEnvironmentManager(test_config)


def get_test_config() -> TestConfig:
    """Get the global test configuration."""
    return test_config


def get_env_manager() -> TestEnvironmentManager:
    """Get the global environment manager."""
    return env_manager


def configure_test_environment(**kwargs):
    """Configure the test environment with custom settings."""
    global test_config, env_manager

    # Update configuration
    for key, value in kwargs.items():
        if hasattr(test_config, key):
            setattr(test_config, key, value)

    # Recreate environment manager with new config
    env_manager = TestEnvironmentManager(test_config)


# Utility functions for common test configurations
def configure_unit_tests():
    """Configure for unit testing."""
    configure_test_environment(
        environment=TestEnvironment.UNIT,
        database_type=DatabaseType.MEMORY,
        use_real_redis=False,
        use_real_ai=False,
        generate_test_data=False,
    )


def configure_integration_tests():
    """Configure for integration testing."""
    configure_test_environment(
        environment=TestEnvironment.INTEGRATION,
        database_type=DatabaseType.SQLITE,
        use_real_redis=False,
        use_real_ai=False,
        generate_test_data=True,
    )


def configure_api_tests():
    """Configure for API testing."""
    configure_test_environment(
        environment=TestEnvironment.API,
        database_type=DatabaseType.SQLITE,
        use_real_redis=False,
        use_real_ai=False,
        generate_test_data=True,
    )


def configure_performance_tests():
    """Configure for performance testing."""
    configure_test_environment(
        environment=TestEnvironment.PERFORMANCE,
        database_type=DatabaseType.POSTGRESQL,
        use_real_redis=True,
        use_real_ai=True,
        generate_test_data=True,
        load_test_users=1000,
        concurrent_requests=50,
    )


def configure_e2e_tests():
    """Configure for end-to-end testing."""
    configure_test_environment(
        environment=TestEnvironment.E2E,
        database_type=DatabaseType.POSTGRESQL,
        use_real_redis=True,
        use_real_ai=True,
        generate_test_data=True,
    )
