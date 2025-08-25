"""
Enhanced Database Configuration with Scalability Features
Implements connection pooling, read replicas, and sharding support
"""

import asyncio
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy import event
import logging
from contextlib import asynccontextmanager
import random
from lyo_app.core.config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Enhanced database manager with scalability features"""
    
    def __init__(self):
        self.primary_engine = None
        self.read_replica_engines: List = []
        self.session_factory = None
        self.read_session_factories: List = []
        self.connection_pool_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "checked_out": 0
        }
    
    async def initialize(self):
        """Initialize database connections with advanced configuration"""
        
        # Primary database engine (read/write)
        self.primary_engine = create_async_engine(
            settings.database_url,
            # Advanced connection pooling
            poolclass=QueuePool,
            pool_size=settings.database_pool_size,  # Base connections
            max_overflow=settings.database_max_overflow,  # Additional connections when needed
            pool_timeout=settings.database_pool_timeout,  # Wait time for connection
            pool_recycle=settings.database_pool_recycle,  # Recycle connections every hour
            pool_pre_ping=True,  # Validate connections before use
            
            # Performance optimizations
            echo=settings.database_echo,
            connect_args={
                "command_timeout": 30,
                "server_settings": {
                    "application_name": "LyoApp_Primary",
                    "jit": "off",  # Disable JIT for faster startup
                }
            }
        )
        
        # Set up read replicas if configured
        await self._setup_read_replicas()
        
        # Create session factories
        self.session_factory = async_sessionmaker(
            bind=self.primary_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Monitor connection pool
        self._setup_pool_monitoring()
        
        logger.info(f"Database initialized - Primary: 1, Read Replicas: {len(self.read_replica_engines)}")
    
    async def _setup_read_replicas(self):
        """Set up read replica connections"""
        read_replica_urls = getattr(settings, 'read_replica_urls', [])
        
        for i, replica_url in enumerate(read_replica_urls):
            try:
                replica_engine = create_async_engine(
                    replica_url,
                    poolclass=QueuePool,
                    pool_size=max(5, settings.database_pool_size // 2),  # Smaller pool for replicas
                    max_overflow=settings.database_max_overflow // 2,
                    pool_timeout=settings.database_pool_timeout,
                    pool_recycle=settings.database_pool_recycle,
                    pool_pre_ping=True,
                    connect_args={
                        "command_timeout": 30,
                        "server_settings": {
                            "application_name": f"LyoApp_Replica_{i+1}",
                            "default_transaction_read_only": "on",  # Ensure read-only
                        }
                    }
                )
                
                self.read_replica_engines.append(replica_engine)
                
                # Create session factory for this replica
                replica_session_factory = async_sessionmaker(
                    bind=replica_engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )
                self.read_session_factories.append(replica_session_factory)
                
                logger.info(f"Read replica {i+1} initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize read replica {i+1}: {e}")
    
    def _setup_pool_monitoring(self):
        """Set up connection pool monitoring"""
        
        @event.listens_for(self.primary_engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            self.connection_pool_stats["total_connections"] += 1
            logger.debug("New database connection established")
        
        @event.listens_for(self.primary_engine.sync_engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            self.connection_pool_stats["checked_out"] += 1
        
        @event.listens_for(self.primary_engine.sync_engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            self.connection_pool_stats["checked_out"] -= 1
    
    @asynccontextmanager
    async def get_session(self, read_only: bool = False):
        """Get database session with read/write routing"""
        
        if read_only and self.read_session_factories:
            # Load balance across read replicas
            factory = random.choice(self.read_session_factories)
            session = factory()
            logger.debug("Using read replica for query")
        else:
            # Use primary database
            session = self.session_factory()
            logger.debug("Using primary database")
        
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        primary_pool = self.primary_engine.pool
        
        stats = {
            "primary": {
                "pool_size": primary_pool.size(),
                "checked_out": primary_pool.checkedout(),
                "overflow": primary_pool.overflow(),
                "invalid": primary_pool.invalid(),
            },
            "replicas": []
        }
        
        for i, engine in enumerate(self.read_replica_engines):
            pool = engine.pool
            stats["replicas"].append({
                "replica_id": i + 1,
                "pool_size": pool.size(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid(),
            })
        
        return stats
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all database connections"""
        results = {"primary": False, "replicas": []}
        
        # Check primary database
        try:
            async with self.get_session() as session:
                await session.execute("SELECT 1")
                results["primary"] = True
        except Exception as e:
            logger.error(f"Primary database health check failed: {e}")
        
        # Check read replicas
        for i, factory in enumerate(self.read_session_factories):
            try:
                session = factory()
                await session.execute("SELECT 1")
                await session.close()
                results["replicas"].append({"replica_id": i + 1, "healthy": True})
            except Exception as e:
                logger.error(f"Replica {i + 1} health check failed: {e}")
                results["replicas"].append({"replica_id": i + 1, "healthy": False})
        
        return results
    
    async def close(self):
        """Close all database connections"""
        if self.primary_engine:
            await self.primary_engine.dispose()
        
        for engine in self.read_replica_engines:
            await engine.dispose()
        
        logger.info("All database connections closed")

# Singleton database manager
db_manager = DatabaseManager()

# Convenience functions for backward compatibility
async def get_session(read_only: bool = False):
    """Get database session with read/write routing"""
    async with db_manager.get_session(read_only=read_only) as session:
        yield session

async def get_db():
    """Get database session (write access)"""
    async with db_manager.get_session(read_only=False) as session:
        yield session

async def get_read_db():
    """Get read-only database session"""
    async with db_manager.get_session(read_only=True) as session:
        yield session
