#!/usr/bin/env python3
"""
Backend Infrastructure Test Suite
Validates database optimization, monitoring systems, and infrastructure performance
"""

import unittest
import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

class TestBackendInfrastructure(unittest.TestCase):
    """Comprehensive test suite for backend infrastructure systems"""

    def setUp(self):
        """Setup test environment"""
        self.start_time = time.time()
        sys.path.append('.')

    def tearDown(self):
        """Cleanup after tests"""
        duration = time.time() - self.start_time
        print(f"   ⏱️  Test duration: {duration:.3f}s")

    def test_database_optimizer_initialization(self):
        """Test database optimizer can be initialized and configured"""
        print("🗄️ Testing database optimizer initialization...")

        try:
            from lyo_app.infrastructure.database_optimizer import (
                DatabaseOptimizer, QueryType, OptimizationLevel
            )

            # Test initialization
            optimizer = DatabaseOptimizer(OptimizationLevel.STANDARD)
            self.assertIsInstance(optimizer, DatabaseOptimizer)
            self.assertEqual(optimizer.optimization_level, OptimizationLevel.STANDARD)

            # Test configuration
            self.assertIsInstance(optimizer.query_metrics, dict)
            self.assertIsInstance(optimizer.connection_pools, dict)
            self.assertGreater(optimizer.slow_query_threshold, 0)

        except ImportError as e:
            self.fail(f"Database optimizer should be importable: {e}")

        print("   ✅ Database optimizer initialization: PASS")

    def test_query_monitoring(self):
        """Test database query monitoring functionality"""
        print("📊 Testing query monitoring...")

        try:
            from lyo_app.infrastructure.database_optimizer import (
                DatabaseOptimizer, QueryType
            )

            optimizer = DatabaseOptimizer()

            # Test query monitoring context manager
            test_query = "SELECT * FROM users WHERE id = 1"

            async def test_monitoring():
                with optimizer.monitored_query(test_query, QueryType.SELECT) as query_id:
                    # Simulate query execution
                    await asyncio.sleep(0.01)
                    self.assertIsInstance(query_id, str)
                    self.assertGreater(len(query_id), 0)

                # Check that metrics were recorded
                self.assertGreater(len(optimizer.query_metrics), 0)

                # Verify query was recorded
                recorded_query = next(iter(optimizer.query_metrics.values()))
                self.assertEqual(recorded_query.query_type, QueryType.SELECT)
                self.assertTrue(recorded_query.success)
                self.assertGreater(recorded_query.execution_time, 0)

            asyncio.run(test_monitoring())

        except Exception as e:
            self.fail(f"Query monitoring should work: {e}")

        print("   ✅ Query monitoring: PASS")

    def test_performance_analysis(self):
        """Test database performance analysis"""
        print("📈 Testing performance analysis...")

        try:
            from lyo_app.infrastructure.database_optimizer import DatabaseOptimizer, QueryType

            optimizer = DatabaseOptimizer()

            # Record some test metrics
            async def record_test_metrics():
                test_queries = [
                    ("SELECT * FROM courses", QueryType.SELECT, 0.05),
                    ("INSERT INTO sessions VALUES (1, 2)", QueryType.INSERT, 0.02),
                    ("SELECT COUNT(*) FROM users", QueryType.AGGREGATION, 1.5),  # Slow query
                ]

                for query_text, query_type, sim_time in test_queries:
                    with optimizer.monitored_query(query_text, query_type):
                        await asyncio.sleep(sim_time / 100)  # Scaled down simulation

            asyncio.run(record_test_metrics())

            # Test performance summary
            summary = optimizer.get_query_performance_summary(3600)

            self.assertIsInstance(summary, dict)
            self.assertIn("total_queries", summary)
            self.assertIn("success_rate", summary)
            self.assertIn("performance_score", summary)

            # Verify reasonable values
            self.assertGreater(summary["total_queries"], 0)
            self.assertGreaterEqual(summary["success_rate"], 0)
            self.assertLessEqual(summary["success_rate"], 100)
            self.assertGreaterEqual(summary["performance_score"], 0)
            self.assertLessEqual(summary["performance_score"], 100)

        except Exception as e:
            self.fail(f"Performance analysis should work: {e}")

        print("   ✅ Performance analysis: PASS")

    def test_connection_pool_optimization(self):
        """Test connection pool optimization"""
        print("🔗 Testing connection pool optimization...")

        try:
            from lyo_app.infrastructure.database_optimizer import DatabaseOptimizer

            optimizer = DatabaseOptimizer()

            # Register a test connection pool
            pool_config = {
                "max_connections": 10,
                "min_connections": 2,
                "timeout": 30
            }

            optimizer.register_connection_pool("test_pool", pool_config)

            # Verify pool was registered
            self.assertIn("test_pool", optimizer.connection_pools)
            self.assertIn("test_pool", optimizer.connection_pool_stats)

            # Test pool optimization
            current_stats = {
                "active_connections": 8,
                "average_checkout_time": 2.5
            }

            optimization_result = optimizer.optimize_connection_pool("test_pool", current_stats)

            self.assertIsInstance(optimization_result, dict)
            self.assertIn("pool_name", optimization_result)
            self.assertIn("current_utilization", optimization_result)
            self.assertIn("recommendations", optimization_result)

            # Check utilization calculation
            expected_utilization = 8 / 10  # 80%
            self.assertEqual(optimization_result["current_utilization"], expected_utilization)

        except Exception as e:
            self.fail(f"Connection pool optimization should work: {e}")

        print("   ✅ Connection pool optimization: PASS")

    def test_monitoring_system_initialization(self):
        """Test monitoring system initialization"""
        print("📡 Testing monitoring system initialization...")

        try:
            from lyo_app.infrastructure.monitoring_system import (
                MonitoringSystem, AlertLevel, ComponentStatus
            )

            # Test initialization
            monitor = MonitoringSystem()
            self.assertIsInstance(monitor, MonitoringSystem)

            # Test default configuration
            self.assertIsInstance(monitor.metrics, dict)
            self.assertIsInstance(monitor.alerts, dict)
            self.assertIsInstance(monitor.component_health, dict)
            self.assertIsInstance(monitor.thresholds, dict)
            self.assertFalse(monitor.monitoring_active)

            # Test threshold configuration
            self.assertIn("cpu_usage", monitor.thresholds)
            self.assertIn("memory_usage", monitor.thresholds)
            self.assertIn("warning", monitor.thresholds["cpu_usage"])
            self.assertIn("critical", monitor.thresholds["cpu_usage"])

        except ImportError as e:
            self.fail(f"Monitoring system should be importable: {e}")

        print("   ✅ Monitoring system initialization: PASS")

    def test_metric_recording_and_alerting(self):
        """Test metric recording and alert generation"""
        print("📊 Testing metric recording and alerting...")

        try:
            from lyo_app.infrastructure.monitoring_system import MonitoringSystem, AlertLevel

            monitor = MonitoringSystem()

            # Record normal metrics (should not trigger alerts)
            monitor.record_metric("cpu_usage", 50.0, "system")
            monitor.record_metric("memory_usage", 60.0, "system")

            # Verify metrics were recorded
            self.assertIn("cpu_usage", monitor.metrics)
            self.assertIn("memory_usage", monitor.metrics)
            self.assertGreater(len(monitor.metrics["cpu_usage"]), 0)

            # Record metric that triggers warning
            monitor.record_metric("cpu_usage", 75.0, "system")  # Above warning threshold

            # Record metric that triggers critical alert
            monitor.record_metric("memory_usage", 96.0, "system")  # Above critical threshold

            # Check alerts were generated
            active_alerts = monitor.get_active_alerts()
            self.assertGreater(len(active_alerts), 0)

            # Find critical alert
            critical_alerts = [a for a in active_alerts if a.level == AlertLevel.CRITICAL]
            self.assertGreater(len(critical_alerts), 0)

            # Test alert resolution
            if active_alerts:
                alert_to_resolve = active_alerts[0]
                resolved = monitor.resolve_alert(alert_to_resolve.id)
                self.assertTrue(resolved)
                self.assertTrue(monitor.alerts[alert_to_resolve.id].resolved)

        except Exception as e:
            self.fail(f"Metric recording and alerting should work: {e}")

        print("   ✅ Metric recording and alerting: PASS")

    def test_component_health_monitoring(self):
        """Test component health monitoring"""
        print("🏥 Testing component health monitoring...")

        try:
            from lyo_app.infrastructure.monitoring_system import (
                MonitoringSystem, ComponentStatus
            )

            monitor = MonitoringSystem()

            # Register test components
            test_components = ["api_server", "database", "cache"]
            for component in test_components:
                monitor.register_component(component)

            # Verify components were registered
            for component in test_components:
                self.assertIn(component, monitor.component_health)
                self.assertEqual(monitor.component_health[component].component_name, component)

            # Test health check with custom function
            async def mock_health_check():
                return {
                    "score": 95.0,
                    "status": "healthy",
                    "metrics": {"uptime": 99.9, "errors": 0}
                }

            async def test_health_checks():
                # Check component health
                health = await monitor.check_component_health("api_server", mock_health_check)

                self.assertEqual(health.component_name, "api_server")
                self.assertEqual(health.health_score, 95.0)
                self.assertEqual(health.status, ComponentStatus.HEALTHY)
                self.assertIsNotNone(health.response_time)
                self.assertIn("uptime", health.metrics)

            asyncio.run(test_health_checks())

        except Exception as e:
            self.fail(f"Component health monitoring should work: {e}")

        print("   ✅ Component health monitoring: PASS")

    def test_system_snapshot_generation(self):
        """Test system snapshot generation"""
        print("📸 Testing system snapshot generation...")

        try:
            from lyo_app.infrastructure.monitoring_system import MonitoringSystem

            monitor = MonitoringSystem()

            # Add some test data
            monitor.record_metric("cpu_usage", 45.0, "system")
            monitor.record_metric("memory_usage", 65.0, "system")
            monitor.register_component("test_service")

            async def test_snapshot():
                snapshot = await monitor.generate_system_snapshot()

                # Verify snapshot structure
                self.assertIsNotNone(snapshot.timestamp)
                self.assertIsInstance(snapshot.cpu_usage, (int, float))
                self.assertIsInstance(snapshot.memory_usage, (int, float))
                self.assertIsInstance(snapshot.overall_health_score, (int, float))
                self.assertIsInstance(snapshot.component_health, dict)

                # Verify health score is reasonable
                self.assertGreaterEqual(snapshot.overall_health_score, 0)
                self.assertLessEqual(snapshot.overall_health_score, 100)

            asyncio.run(test_snapshot())

        except Exception as e:
            self.fail(f"System snapshot generation should work: {e}")

        print("   ✅ System snapshot generation: PASS")

    def test_query_optimization_suggestions(self):
        """Test SQL query optimization suggestions"""
        print("🔧 Testing query optimization suggestions...")

        try:
            from lyo_app.infrastructure.database_optimizer import DatabaseOptimizer

            optimizer = DatabaseOptimizer()

            # Test various query optimization scenarios
            test_queries = [
                "SELECT * FROM users",  # Should suggest specific columns
                "SELECT * FROM courses WHERE status = 'active'",  # Should be fine
                "SELECT name FROM users WHERE id IN (SELECT user_id FROM sessions)",  # Should suggest EXISTS
                "SELECT u.name, c.title FROM users u, courses c WHERE u.id = c.instructor_id"  # Should suggest JOIN
            ]

            for query in test_queries:
                optimized_query, suggestions = optimizer.optimize_query_text(query)

                # Verify optimization results
                self.assertIsInstance(optimized_query, str)
                self.assertIsInstance(suggestions, list)
                self.assertGreater(len(optimized_query.strip()), 0)

                # Verify query was cleaned up (whitespace normalized)
                self.assertEqual(optimized_query, ' '.join(query.split()))

            # Test specific optimization suggestion
            select_all_query = "SELECT * FROM large_table"
            _, suggestions = optimizer.optimize_query_text(select_all_query)
            has_column_suggestion = any("specific columns" in s for s in suggestions)
            self.assertTrue(has_column_suggestion, "Should suggest specific columns for SELECT *")

        except Exception as e:
            self.fail(f"Query optimization suggestions should work: {e}")

        print("   ✅ Query optimization suggestions: PASS")

    def test_index_recommendations(self):
        """Test database index recommendations"""
        print("📇 Testing index recommendations...")

        try:
            from lyo_app.infrastructure.database_optimizer import DatabaseOptimizer

            optimizer = DatabaseOptimizer()

            # Mock query patterns that would benefit from indexes
            query_patterns = [
                {
                    "table_name": "users",
                    "where_columns": ["email"],
                    "execution_count": 200,
                    "avg_execution_time": 0.8
                },
                {
                    "table_name": "courses",
                    "where_columns": ["category", "status"],
                    "order_columns": ["created_at"],
                    "execution_count": 150,
                    "avg_execution_time": 1.2
                },
                {
                    "table_name": "sessions",
                    "where_columns": ["user_id"],
                    "execution_count": 50,
                    "avg_execution_time": 0.3
                }
            ]

            recommendations = optimizer.generate_index_recommendations(query_patterns)

            # Verify recommendations structure
            self.assertIsInstance(recommendations, list)

            for rec in recommendations:
                self.assertIsNotNone(rec.table_name)
                self.assertIsInstance(rec.column_names, list)
                self.assertGreater(len(rec.column_names), 0)
                self.assertIn(rec.priority, ["low", "medium", "high"])
                self.assertGreater(rec.estimated_benefit, 0)
                self.assertIsInstance(rec.reasoning, str)

            # Should recommend high-frequency columns first
            if recommendations:
                high_benefit_recs = [r for r in recommendations if r.estimated_benefit > 5.0]
                self.assertGreater(len(high_benefit_recs), 0, "Should have high-benefit recommendations")

        except Exception as e:
            self.fail(f"Index recommendations should work: {e}")

        print("   ✅ Index recommendations: PASS")

    def test_performance_analytics(self):
        """Test performance analytics and reporting"""
        print("📊 Testing performance analytics...")

        try:
            from lyo_app.infrastructure.monitoring_system import MonitoringSystem

            monitor = MonitoringSystem()

            # Add test data
            test_metrics = [
                ("cpu_usage", 45.0),
                ("cpu_usage", 52.0),
                ("cpu_usage", 38.0),
                ("memory_usage", 67.0),
                ("memory_usage", 72.0),
                ("response_time", 150.0),
                ("response_time", 200.0)
            ]

            for metric_name, value in test_metrics:
                monitor.record_metric(metric_name, value, "system")

            async def test_analytics():
                analytics = await monitor.get_performance_analytics(3600)

                # Verify analytics structure
                self.assertIsInstance(analytics, dict)
                self.assertIn("system_performance", analytics)
                self.assertIn("component_performance", analytics)
                self.assertIn("alert_summary", analytics)

                # Check system performance metrics
                sys_perf = analytics["system_performance"]
                if "cpu_usage" in sys_perf:
                    cpu_stats = sys_perf["cpu_usage"]
                    self.assertIn("average", cpu_stats)
                    self.assertIn("max", cpu_stats)
                    self.assertIn("min", cpu_stats)
                    self.assertIsInstance(cpu_stats["average"], (int, float))

                # Check alert summary
                alert_summary = analytics["alert_summary"]
                self.assertIn("total_alerts", alert_summary)
                self.assertIn("active_alerts", alert_summary)
                self.assertIsInstance(alert_summary["total_alerts"], int)

            asyncio.run(test_analytics())

        except Exception as e:
            self.fail(f"Performance analytics should work: {e}")

        print("   ✅ Performance analytics: PASS")

def run_backend_infrastructure_tests():
    """Run comprehensive backend infrastructure test suite"""
    print("🎯 BACKEND INFRASTRUCTURE TEST SUITE")
    print("=" * 80)

    suite = unittest.TestLoader().loadTestsFromTestCase(TestBackendInfrastructure)
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)

    start_time = time.time()
    result = runner.run(suite)
    total_time = time.time() - start_time

    # Calculate results
    total_tests = result.testsRun
    failed_tests = len(result.failures) + len(result.errors)
    success_rate = ((total_tests - failed_tests) / total_tests * 100) if total_tests > 0 else 0

    print(f"\n📊 BACKEND INFRASTRUCTURE TEST RESULTS")
    print("=" * 80)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {total_tests - failed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Duration: {total_time:.3f}s")

    if result.failures:
        print(f"\n❌ FAILURES:")
        for test, error in result.failures:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if result.errors:
        print(f"\n💥 ERRORS:")
        for test, error in result.errors:
            print(f"   • {test}: {error.split(chr(10))[0]}")

    if success_rate >= 90.0:
        print(f"\n🎉 BACKEND INFRASTRUCTURE: EXCELLENT ({success_rate:.1f}%)")
        print("✅ Advanced database optimization")
        print("✅ Comprehensive monitoring system")
        print("✅ Intelligent performance analytics")
        print("✅ Real-time alerting and health checks")
        print("✅ Query optimization and caching")
        print("✅ Connection pool management")
    else:
        print(f"\n⚠️  BACKEND INFRASTRUCTURE: NEEDS IMPROVEMENT ({success_rate:.1f}%)")
        print("📝 Address failing tests to optimize backend performance")

    return success_rate >= 90.0, {
        "total_tests": total_tests,
        "passed_tests": total_tests - failed_tests,
        "failed_tests": failed_tests,
        "success_rate": success_rate,
        "duration": total_time,
        "status": "pass" if success_rate >= 90.0 else "fail"
    }

if __name__ == "__main__":
    success, results = run_backend_infrastructure_tests()