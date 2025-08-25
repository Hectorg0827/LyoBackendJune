"""
Market-Ready Database Management V2
==================================

Production-grade database layer with Google Cloud SQL integration.
Supports PostgreSQL 15 with pgvector for hybrid search capabilities.
"""

import asyncio
from typing import AsyncGenerator, Optional, Dict, Any, List
from contextlib import asynccontextmanager
import time

import asyncpg
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy.pool import NullPool
from sqlalchemy import text, create_engine
from sqlalchemy.exc import SQLAlchemyError

from lyo_app.core.config_v2 import settings
from lyo_app.core.logging_v2 import logger


# Base class for all models
Base = declarative_base()


class DatabaseManager:
    """Centralized database management with connection pooling and health checks."""
    
    def __init__(self):
        self.engine: Optional[AsyncEngine] = None
        self.async_session_factory: Optional[async_sessionmaker] = None
        self.sync_engine = None  # For Alembic migrations
        self._is_initialized = False
        
    async def initialize(self):
        """Initialize database connections and prepare for use."""
        try:
            logger.info("🔄 Initializing database connections...")
            
            # Create async engine with connection pooling
            self.engine = create_async_engine(
                str(settings.DATABASE_URL),
                echo=settings.DEBUG,
                pool_size=settings.DATABASE_POOL_SIZE,
                max_overflow=settings.DATABASE_MAX_OVERFLOW,
                pool_pre_ping=True,
                pool_recycle=3600,  # 1 hour
                connect_args={
                    "server_settings": {
                        "jit": "off",  # Disable JIT for better cold start performance
                    }
                } if settings.is_production() else {},
            )
            
            # Create session factory
            self.async_session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autocommit=False,
                autoflush=False,
            )
            
            # Create sync engine for Alembic
            self.sync_engine = create_engine(
                settings.database_url_sync,
                echo=settings.DEBUG,
                poolclass=NullPool,  # Alembic doesn't need connection pooling
            )
            
            # Test connection
            await self._test_connection()
            
            # Enable pgvector extension if configured
            if settings.ENABLE_VECTOR_SEARCH:
                await self._setup_pgvector()
            
            self._is_initialized = True
            logger.info("✅ Database connections initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            raise
    
    async def shutdown(self):
        """Cleanup database connections."""
        if self.engine:
            logger.info("🔄 Shutting down database connections...")
            await self.engine.dispose()
            if self.sync_engine:
                self.sync_engine.dispose()
            self._is_initialized = False
            logger.info("✅ Database connections closed")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with automatic cleanup."""
        if not self._is_initialized:
            raise RuntimeError("Database not initialized")
        
        async with self.async_session_factory() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()
    
    async def health_check(self) -> bool:
        """Quick database health check."""
        try:
            async with self.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def ready_check(self) -> bool:
        """Comprehensive database readiness check."""
        try:
            start_time = time.time()
            
            async with self.get_session() as session:
                # Test basic connectivity
                await session.execute(text("SELECT 1"))
                
                # Test table access (assuming users table exists)
                try:
                    await session.execute(text("SELECT COUNT(*) FROM users LIMIT 1"))
                except Exception:
                    # Tables might not exist yet during initial deployment
                    logger.warning("User table not accessible - might be initial deployment")
                
                # Check pgvector if enabled
                if settings.ENABLE_VECTOR_SEARCH:
                    result = await session.execute(
                        text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                    )
                    if not result.scalar():
                        logger.warning("pgvector extension not installed")
                        return False
                
                response_time = time.time() - start_time
                if response_time > 5.0:  # 5 second threshold
                    logger.warning(f"Database response time high: {response_time:.2f}s")
                    return False
                
                return True
                
        except Exception as e:
            logger.error(f"Database readiness check failed: {e}")
            return False
    
    async def _test_connection(self):
        """Test initial database connection."""
        try:
            async with self.engine.begin() as conn:
                result = await conn.execute(text("SELECT version()"))
                version = result.scalar()
                logger.info(f"Connected to database: {version}")
                
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise
    
    async def _setup_pgvector(self):
        """Setup pgvector extension for vector search."""
        try:
            async with self.engine.begin() as conn:
                # Check if pgvector is already installed
                result = await conn.execute(
                    text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                )
                
                if not result.scalar():
                    logger.info("Installing pgvector extension...")
                    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    logger.info("✅ pgvector extension installed")
                else:
                    logger.info("✅ pgvector extension already installed")
                    
        except Exception as e:
            logger.error(f"pgvector setup failed: {e}")
            # Don't raise - vector search is optional
    
    async def execute_raw(self, query: str, params: Optional[Dict] = None) -> Any:
        """Execute raw SQL query."""
        async with self.get_session() as session:
            result = await session.execute(text(query), params or {})
            await session.commit()
            return result
    
    async def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get information about a specific table."""
        query = """
        SELECT 
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns 
        WHERE table_name = :table_name
        ORDER BY ordinal_position
        """
        
        async with self.get_session() as session:
            result = await session.execute(text(query), {"table_name": table_name})
            columns = []
            for row in result:
                columns.append({
                    "name": row.column_name,
                    "type": row.data_type,
                    "nullable": row.is_nullable == "YES",
                    "default": row.column_default,
                })
            
            return {"table": table_name, "columns": columns}
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics for monitoring."""
        stats_query = """
        SELECT 
            pg_database_size(current_database()) as db_size,
            (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_connections,
            (SELECT count(*) FROM pg_stat_activity) as total_connections
        """
        
        async with self.get_session() as session:
            result = await session.execute(text(stats_query))
            row = result.first()
            
            return {
                "database_size_bytes": row.db_size if row else 0,
                "active_connections": row.active_connections if row else 0,
                "total_connections": row.total_connections if row else 0,
                "max_connections": settings.DATABASE_POOL_SIZE,
            }


# Global database manager instance
database_manager = DatabaseManager()


# Dependency for FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with database_manager.get_session() as session:
        yield session


# Legacy compatibility
init_db = database_manager.initialize
close_db = database_manager.shutdown
get_database = get_db
