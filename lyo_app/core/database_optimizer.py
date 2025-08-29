"""Database Optimization and Query Performance Tools
Advanced database optimization for LyoBackend
"""

import asyncio
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import text, Index, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
import psycopg2
import sqlite3

from lyo_app.core.config import settings
from lyo_app.core.database import get_db
from lyo_app.models.production import User, Course, CourseItem, Achievement, UserAchievement
from lyo_app.core.performance_monitor import get_performance_monitor

logger = logging.getLogger(__name__)

class DatabaseOptimizer:
    """Database performance optimization and monitoring"""

    def __init__(self):
        self.performance_monitor = get_performance_monitor()
        self.db_type = "postgresql" if "postgresql" in settings.DATABASE_URL else "sqlite"

    async def analyze_query_performance(self) -> Dict[str, Any]:
        """Analyze database query performance"""
        async with get_db() as session:
            start_time = time.time()

            # Analyze slow queries
            slow_queries = await self._get_slow_queries(session)

            # Check index usage
            index_stats = await self._analyze_index_usage(session)

            # Check table statistics
            table_stats = await self._get_table_statistics(session)

            analysis_time = time.time() - start_time

            return {
                'analysis_time': analysis_time,
                'slow_queries': slow_queries,
                'index_usage': index_stats,
                'table_statistics': table_stats,
                'recommendations': self._generate_recommendations(slow_queries, index_stats)
            }

    async def _get_slow_queries(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """Get slow query statistics"""
        if self.db_type == "postgresql":
            # PostgreSQL slow query analysis
            try:
                result = await session.execute(text("""
                    SELECT
                        query,
                        calls,
                        total_time,
                        mean_time,
                        rows
                    FROM pg_stat_statements
                    WHERE mean_time > 100  -- queries taking more than 100ms on average
                    ORDER BY mean_time DESC
                    LIMIT 20
                """))

                return [dict(row) for row in result.mappings()]
            except Exception as e:
                logger.warning(f"Could not analyze PostgreSQL slow queries: {e}")
                return []
        else:
            # SQLite doesn't have built-in slow query tracking
            return []

    async def _analyze_index_usage(self, session: AsyncSession) -> Dict[str, Any]:
        """Analyze index usage statistics"""
        if self.db_type == "postgresql":
            try:
                # Get index usage statistics
                result = await session.execute(text("""
                    SELECT
                        schemaname,
                        tablename,
                        indexname,
                        idx_scan,
                        idx_tup_read,
                        idx_tup_fetch
                    FROM pg_stat_user_indexes
                    ORDER BY idx_scan DESC
                """))

                indexes = [dict(row) for row in result.mappings()]

                # Identify unused indexes
                unused_indexes = [
                    idx for idx in indexes
                    if idx['idx_scan'] == 0
                ]

                return {
                    'total_indexes': len(indexes),
                    'unused_indexes': unused_indexes,
                    'most_used_indexes': sorted(
                        indexes,
                        key=lambda x: x['idx_scan'],
                        reverse=True
                    )[:10]
                }
            except Exception as e:
                logger.warning(f"Could not analyze PostgreSQL index usage: {e}")
                return {'error': str(e)}
        else:
            # SQLite index analysis
            try:
                result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))
                indexes = [row[0] for row in result]

                return {
                    'total_indexes': len(indexes),
                    'index_names': indexes
                }
            except Exception as e:
                logger.warning(f"Could not analyze SQLite indexes: {e}")
                return {'error': str(e)}

    async def _get_table_statistics(self, session: AsyncSession) -> Dict[str, Any]:
        """Get table statistics and sizes"""
        tables = ['users', 'courses', 'course_items', 'achievements', 'user_achievements']

        stats = {}
        for table in tables:
            try:
                # Get row count
                count_result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                row_count = count_result.scalar()

                if self.db_type == "postgresql":
                    # Get table size
                    size_result = await session.execute(text(f"""
                        SELECT pg_size_pretty(pg_total_relation_size('{table}'))
                    """))
                    table_size = size_result.scalar()
                else:
                    table_size = "N/A (SQLite)"

                stats[table] = {
                    'row_count': row_count,
                    'size': table_size
                }
            except Exception as e:
                logger.warning(f"Could not get statistics for table {table}: {e}")
                stats[table] = {'error': str(e)}

        return stats

    def _generate_recommendations(self, slow_queries: List[Dict], index_stats: Dict) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []

        # Analyze slow queries
        if slow_queries:
            recommendations.append(f"Found {len(slow_queries)} slow queries that need optimization")

        # Analyze index usage
        if 'unused_indexes' in index_stats and index_stats['unused_indexes']:
            recommendations.append(f"Consider removing {len(index_stats['unused_indexes'])} unused indexes")

        # General recommendations
        recommendations.extend([
            "Consider adding composite indexes for frequently queried columns",
            "Implement query result caching for expensive operations",
            "Use database connection pooling for better performance",
            "Consider partitioning large tables if applicable",
            "Regularly analyze and vacuum database for optimal performance"
        ])

        return recommendations

    async def create_optimized_indexes(self):
        """Create optimized indexes for better query performance"""
        async with get_db() as session:
            try:
                # Index for user authentication (email lookups)
                await session.execute(text("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_email
                    ON users (email) WHERE email IS NOT NULL
                """))

                # Index for user creation date (for analytics)
                await session.execute(text("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_users_created_at
                    ON users (created_at)
                """))

                # Composite index for courses by user and status
                await session.execute(text("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_courses_user_status
                    ON courses (user_id, is_published, created_at DESC)
                """))

                # Index for course items by course
                await session.execute(text("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_course_items_course
                    ON course_items (course_id, type, created_at)
                """))

                # Index for achievements by user
                await session.execute(text("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_user_achievements_user
                    ON user_achievements (user_id, achievement_id, unlocked_at DESC)
                """))

                # Index for content search (if implementing search)
                await session.execute(text("""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_course_items_content
                    ON course_items USING gin (to_tsvector('english', content))
                    WHERE content IS NOT NULL
                """))

                await session.commit()
                logger.info("Optimized indexes created successfully")

            except Exception as e:
                logger.error(f"Failed to create optimized indexes: {e}")
                await session.rollback()

    async def optimize_table_statistics(self):
        """Update table statistics for better query planning"""
        if self.db_type == "postgresql":
            async with get_db() as session:
                try:
                    # Analyze all tables
                    await session.execute(text("ANALYZE"))
                    logger.info("Table statistics updated")
                except Exception as e:
                    logger.error(f"Failed to update table statistics: {e}")

    async def get_query_execution_plan(self, query: str) -> Dict[str, Any]:
        """Get query execution plan for analysis"""
        async with get_db() as session:
            try:
                if self.db_type == "postgresql":
                    result = await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {query}"))
                    plan = [row[0] for row in result]
                    return {
                        'query': query,
                        'execution_plan': plan,
                        'estimated_cost': self._parse_execution_cost(plan)
                    }
                else:
                    # SQLite EXPLAIN QUERY PLAN
                    result = await session.execute(text(f"EXPLAIN QUERY PLAN {query}"))
                    plan = [dict(row) for row in result.mappings()]
                    return {
                        'query': query,
                        'execution_plan': plan
                    }
            except Exception as e:
                logger.error(f"Failed to get execution plan: {e}")
                return {'error': str(e)}

    def _parse_execution_cost(self, plan: List[str]) -> Dict[str, Any]:
        """Parse PostgreSQL execution plan for cost analysis"""
        cost_info = {}

        for line in plan:
            if 'cost=' in line:
                # Extract cost information
                cost_match = line.split('cost=')[1].split()[0]
                if '..' in cost_match:
                    start_cost, end_cost = cost_match.split('..')
                    cost_info['start_cost'] = float(start_cost)
                    cost_info['end_cost'] = float(end_cost)

        return cost_info

class QueryOptimizer:
    """Advanced query optimization utilities"""

    def __init__(self):
        self.optimizer = DatabaseOptimizer()

    async def optimize_frequent_queries(self):
        """Optimize frequently executed queries"""

        # Optimize user feed query
        await self._optimize_user_feed_query()

        # Optimize course listing query
        await self._optimize_course_listing_query()

        # Optimize achievement queries
        await self._optimize_achievement_queries()

    async def _optimize_user_feed_query(self):
        """Optimize user feed query with proper indexing and caching"""
        async with get_db() as session:
            try:
                # Create optimized query for user feed
                query = """
                SELECT c.id, c.title, c.description, c.created_at,
                       u.username, u.avatar_url,
                       COUNT(ci.id) as item_count
                FROM courses c
                JOIN users u ON c.user_id = u.id
                LEFT JOIN course_items ci ON c.id = ci.course_id
                WHERE c.is_published = true
                GROUP BY c.id, u.id
                ORDER BY c.created_at DESC
                LIMIT 50
                """

                # Analyze the query
                plan = await self.optimizer.get_query_execution_plan(query)

                # Log optimization insights
                logger.info(f"User feed query analysis: {plan}")

            except Exception as e:
                logger.error(f"Failed to optimize user feed query: {e}")

    async def _optimize_course_listing_query(self):
        """Optimize course listing with pagination"""
        async with get_db() as session:
            try:
                # Optimized course listing query
                query = """
                SELECT c.*, u.username,
                       json_agg(json_build_object(
                           'id', ci.id,
                           'type', ci.type,
                           'title', ci.title
                       )) as items
                FROM courses c
                JOIN users u ON c.user_id = u.id
                LEFT JOIN course_items ci ON c.id = ci.course_id
                WHERE c.is_published = true
                GROUP BY c.id, u.id
                ORDER BY c.created_at DESC
                LIMIT 20 OFFSET 0
                """

                plan = await self.optimizer.get_query_execution_plan(query)
                logger.info(f"Course listing query analysis: {plan}")

            except Exception as e:
                logger.error(f"Failed to optimize course listing query: {e}")

    async def _optimize_achievement_queries(self):
        """Optimize achievement-related queries"""
        async with get_db() as session:
            try:
                # User achievements query
                query = """
                SELECT a.*, ua.unlocked_at, ua.progress
                FROM achievements a
                JOIN user_achievements ua ON a.id = ua.achievement_id
                WHERE ua.user_id = $1
                ORDER BY ua.unlocked_at DESC
                """

                plan = await self.optimizer.get_query_execution_plan(query)
                logger.info(f"Achievement query analysis: {plan}")

            except Exception as e:
                logger.error(f"Failed to optimize achievement queries: {e}")

class ConnectionPoolOptimizer:
    """Database connection pool optimization"""

    def __init__(self):
        self.pool_stats = {}

    async def monitor_connection_pool(self):
        """Monitor database connection pool usage"""
        # This would integrate with your database connection pool
        # For now, we'll track basic connection metrics

        while True:
            try:
                # Monitor connection pool size, active connections, etc.
                # This is a placeholder for actual pool monitoring
                self.pool_stats = {
                    'timestamp': time.time(),
                    'active_connections': 0,  # Would get from pool
                    'idle_connections': 0,    # Would get from pool
                    'total_connections': 0,   # Would get from pool
                    'waiting_clients': 0      # Would get from pool
                }

                logger.info(f"Connection pool stats: {self.pool_stats}")

                await asyncio.sleep(60)  # Monitor every minute

            except Exception as e:
                logger.error(f"Connection pool monitoring error: {e}")
                await asyncio.sleep(30)

# Global instances
db_optimizer = DatabaseOptimizer()
query_optimizer = QueryOptimizer()
pool_optimizer = ConnectionPoolOptimizer()

async def initialize_database_optimization():
    """Initialize database optimization system"""
    try:
        # Create optimized indexes
        await db_optimizer.create_optimized_indexes()

        # Update table statistics
        await db_optimizer.optimize_table_statistics()

        # Optimize frequent queries
        await query_optimizer.optimize_frequent_queries()

        # Start connection pool monitoring
        asyncio.create_task(pool_optimizer.monitor_connection_pool())

        logger.info("Database optimization system initialized")

    except Exception as e:
        logger.error(f"Failed to initialize database optimization: {e}")

async def run_database_health_check():
    """Run comprehensive database health check"""
    try:
        # Analyze query performance
        analysis = await db_optimizer.analyze_query_performance()

        # Log analysis results
        logger.info(f"Database Health Check Results: {json.dumps(analysis, indent=2)}")

        # Check for critical issues
        if analysis.get('slow_queries'):
            logger.warning(f"Found {len(analysis['slow_queries'])} slow queries")

        return analysis

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {'error': str(e)}
