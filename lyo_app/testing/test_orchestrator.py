"""
Test Orchestrator - Comprehensive Testing System
Coordinates end-to-end, integration, performance, and quality assurance testing
"""

import asyncio
import json
import time
import logging
import subprocess
import sys
from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
import concurrent.futures
import traceback

logger = logging.getLogger(__name__)

class TestType(str, Enum):
    """Types of tests supported"""
    UNIT = "unit"
    INTEGRATION = "integration"
    END_TO_END = "end_to_end"
    PERFORMANCE = "performance"
    LOAD = "load"
    SECURITY = "security"
    ACCESSIBILITY = "accessibility"
    VISUAL_REGRESSION = "visual_regression"

class TestStatus(str, Enum):
    """Test execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"

@dataclass
class TestResult:
    """Individual test result"""
    test_id: str
    test_name: str
    test_type: TestType
    status: TestStatus
    duration: float = 0.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    assertions_count: int = 0
    passed_assertions: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TestSuite:
    """Test suite configuration"""
    name: str
    description: str
    test_type: TestType
    test_functions: List[Callable] = field(default_factory=list)
    setup_function: Optional[Callable] = None
    teardown_function: Optional[Callable] = None
    timeout_seconds: int = 300
    parallel: bool = False
    dependencies: List[str] = field(default_factory=list)

class TestOrchestrator:
    """Orchestrates comprehensive testing across the entire system"""

    def __init__(self):
        self.test_suites: Dict[str, TestSuite] = {}
        self.test_results: Dict[str, List[TestResult]] = {}
        self.global_setup_done = False
        self.global_teardown_done = False

    def register_suite(self, suite: TestSuite):
        """Register a test suite"""
        self.test_suites[suite.name] = suite
        logger.info(f"Registered test suite: {suite.name}")

    async def run_all_tests(self, test_types: List[TestType] = None) -> Dict[str, Any]:
        """Run all registered test suites"""
        logger.info("Starting comprehensive test orchestration")

        if not self.global_setup_done:
            await self._global_setup()

        # Filter suites by test types if specified
        suites_to_run = self.test_suites.values()
        if test_types:
            suites_to_run = [s for s in suites_to_run if s.test_type in test_types]

        # Sort suites by dependencies
        sorted_suites = self._sort_suites_by_dependencies(suites_to_run)

        total_start_time = time.time()
        overall_results = {
            "start_time": datetime.now().isoformat(),
            "suites": {},
            "summary": {}
        }

        for suite in sorted_suites:
            logger.info(f"Running test suite: {suite.name}")

            suite_start_time = time.time()
            suite_results = await self._run_test_suite(suite)
            suite_duration = time.time() - suite_start_time

            overall_results["suites"][suite.name] = {
                "results": suite_results,
                "duration": suite_duration,
                "status": self._get_suite_status(suite_results)
            }

            self.test_results[suite.name] = suite_results

        total_duration = time.time() - total_start_time

        # Generate summary
        summary = self._generate_summary(overall_results["suites"], total_duration)
        overall_results["summary"] = summary
        overall_results["end_time"] = datetime.now().isoformat()
        overall_results["total_duration"] = total_duration

        if not self.global_teardown_done:
            await self._global_teardown()

        return overall_results

    async def run_suite(self, suite_name: str) -> List[TestResult]:
        """Run a specific test suite"""
        if suite_name not in self.test_suites:
            raise ValueError(f"Test suite '{suite_name}' not found")

        suite = self.test_suites[suite_name]
        return await self._run_test_suite(suite)

    async def _run_test_suite(self, suite: TestSuite) -> List[TestResult]:
        """Execute a single test suite"""
        results = []

        try:
            # Setup
            if suite.setup_function:
                logger.debug(f"Running setup for {suite.name}")
                await self._execute_with_timeout(suite.setup_function, suite.timeout_seconds)

            # Run tests
            if suite.parallel and len(suite.test_functions) > 1:
                results = await self._run_tests_parallel(suite)
            else:
                results = await self._run_tests_sequential(suite)

            # Teardown
            if suite.teardown_function:
                logger.debug(f"Running teardown for {suite.name}")
                await self._execute_with_timeout(suite.teardown_function, suite.timeout_seconds)

        except Exception as e:
            logger.error(f"Suite {suite.name} failed during setup/teardown: {e}")
            # Create error result for the entire suite
            error_result = TestResult(
                test_id=f"{suite.name}_suite_error",
                test_name=f"{suite.name} Suite Error",
                test_type=suite.test_type,
                status=TestStatus.ERROR,
                error_message=str(e)
            )
            results.append(error_result)

        return results

    async def _run_tests_sequential(self, suite: TestSuite) -> List[TestResult]:
        """Run tests sequentially"""
        results = []

        for i, test_func in enumerate(suite.test_functions):
            test_id = f"{suite.name}_{i:03d}"
            test_name = getattr(test_func, '__name__', f'test_{i}')

            result = await self._execute_test(test_id, test_name, test_func, suite)
            results.append(result)

            # Stop on first failure if not configured to continue
            if result.status == TestStatus.FAILED and not getattr(suite, 'continue_on_failure', True):
                logger.warning(f"Stopping suite {suite.name} due to test failure")
                break

        return results

    async def _run_tests_parallel(self, suite: TestSuite) -> List[TestResult]:
        """Run tests in parallel"""
        logger.info(f"Running {len(suite.test_functions)} tests in parallel for {suite.name}")

        tasks = []
        for i, test_func in enumerate(suite.test_functions):
            test_id = f"{suite.name}_{i:03d}"
            test_name = getattr(test_func, '__name__', f'test_{i}')

            task = asyncio.create_task(
                self._execute_test(test_id, test_name, test_func, suite)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions in parallel execution
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_result = TestResult(
                    test_id=f"{suite.name}_{i:03d}",
                    test_name=f"parallel_test_{i}",
                    test_type=suite.test_type,
                    status=TestStatus.ERROR,
                    error_message=str(result)
                )
                processed_results.append(error_result)
            else:
                processed_results.append(result)

        return processed_results

    async def _execute_test(self, test_id: str, test_name: str,
                          test_func: Callable, suite: TestSuite) -> TestResult:
        """Execute individual test function"""
        result = TestResult(
            test_id=test_id,
            test_name=test_name,
            test_type=suite.test_type,
            status=TestStatus.PENDING,
            start_time=datetime.now()
        )

        try:
            result.status = TestStatus.RUNNING
            start_time = time.time()

            # Execute test with timeout
            if asyncio.iscoroutinefunction(test_func):
                test_result = await asyncio.wait_for(
                    test_func(),
                    timeout=suite.timeout_seconds
                )
            else:
                test_result = await asyncio.wait_for(
                    asyncio.to_thread(test_func),
                    timeout=suite.timeout_seconds
                )

            result.duration = time.time() - start_time
            result.end_time = datetime.now()

            # Process test result
            if isinstance(test_result, bool):
                result.status = TestStatus.PASSED if test_result else TestStatus.FAILED
            elif isinstance(test_result, dict):
                result.status = TestStatus.PASSED if test_result.get('passed', False) else TestStatus.FAILED
                result.assertions_count = test_result.get('assertions', 0)
                result.passed_assertions = test_result.get('passed_assertions', 0)
                result.metadata = test_result.get('metadata', {})
            else:
                result.status = TestStatus.PASSED

        except asyncio.TimeoutError:
            result.status = TestStatus.ERROR
            result.error_message = f"Test timed out after {suite.timeout_seconds} seconds"
            result.duration = suite.timeout_seconds
            result.end_time = datetime.now()

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            result.duration = time.time() - start_time if 'start_time' in locals() else 0
            result.end_time = datetime.now()
            logger.error(f"Test {test_name} failed: {e}")
            logger.debug(traceback.format_exc())

        return result

    async def _execute_with_timeout(self, func: Callable, timeout: int):
        """Execute function with timeout"""
        if asyncio.iscoroutinefunction(func):
            return await asyncio.wait_for(func(), timeout=timeout)
        else:
            return await asyncio.wait_for(asyncio.to_thread(func), timeout=timeout)

    def _sort_suites_by_dependencies(self, suites: List[TestSuite]) -> List[TestSuite]:
        """Sort test suites based on dependencies"""
        # Simple topological sort for now
        suite_map = {s.name: s for s in suites}
        sorted_suites = []
        visited = set()

        def visit(suite_name: str):
            if suite_name in visited:
                return

            if suite_name in suite_map:
                suite = suite_map[suite_name]
                for dep in suite.dependencies:
                    visit(dep)

                visited.add(suite_name)
                sorted_suites.append(suite)

        for suite in suites:
            visit(suite.name)

        return sorted_suites

    def _get_suite_status(self, results: List[TestResult]) -> str:
        """Determine overall status of test suite"""
        if not results:
            return "empty"

        statuses = [r.status for r in results]

        if TestStatus.ERROR in statuses:
            return "error"
        elif TestStatus.FAILED in statuses:
            return "failed"
        elif all(s == TestStatus.PASSED for s in statuses):
            return "passed"
        elif TestStatus.SKIPPED in statuses:
            return "partial"
        else:
            return "unknown"

    def _generate_summary(self, suite_results: Dict[str, Any], total_duration: float) -> Dict[str, Any]:
        """Generate comprehensive test summary"""
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        error_tests = 0
        skipped_tests = 0

        suite_summary = {}

        for suite_name, suite_data in suite_results.items():
            results = suite_data["results"]
            suite_stats = {
                "total": len(results),
                "passed": sum(1 for r in results if r.status == TestStatus.PASSED),
                "failed": sum(1 for r in results if r.status == TestStatus.FAILED),
                "error": sum(1 for r in results if r.status == TestStatus.ERROR),
                "skipped": sum(1 for r in results if r.status == TestStatus.SKIPPED),
                "duration": suite_data["duration"],
                "status": suite_data["status"]
            }

            suite_summary[suite_name] = suite_stats

            total_tests += suite_stats["total"]
            passed_tests += suite_stats["passed"]
            failed_tests += suite_stats["failed"]
            error_tests += suite_stats["error"]
            skipped_tests += suite_stats["skipped"]

        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0

        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "error_tests": error_tests,
            "skipped_tests": skipped_tests,
            "success_rate": round(success_rate, 2),
            "total_duration": round(total_duration, 3),
            "suites_summary": suite_summary,
            "overall_status": "passed" if success_rate == 100.0 else "failed"
        }

    async def _global_setup(self):
        """Global test environment setup"""
        logger.info("Running global test setup")
        # Add any global setup logic here
        self.global_setup_done = True

    async def _global_teardown(self):
        """Global test environment teardown"""
        logger.info("Running global test teardown")
        # Add any global teardown logic here
        self.global_teardown_done = True

    def generate_report(self, results: Dict[str, Any], format: str = "json") -> str:
        """Generate test report in specified format"""
        if format.lower() == "json":
            return json.dumps(results, indent=2, default=str)

        elif format.lower() == "html":
            return self._generate_html_report(results)

        elif format.lower() == "junit":
            return self._generate_junit_report(results)

        else:
            raise ValueError(f"Unsupported report format: {format}")

    def _generate_html_report(self, results: Dict[str, Any]) -> str:
        """Generate HTML test report"""
        summary = results["summary"]

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .summary {{ margin: 20px 0; }}
                .suite {{ margin: 10px 0; padding: 10px; border: 1px solid #ddd; }}
                .passed {{ color: green; }}
                .failed {{ color: red; }}
                .error {{ color: orange; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Test Report</h1>
                <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>

            <div class="summary">
                <h2>Summary</h2>
                <p>Total Tests: {summary['total_tests']}</p>
                <p class="passed">Passed: {summary['passed_tests']}</p>
                <p class="failed">Failed: {summary['failed_tests']}</p>
                <p class="error">Errors: {summary['error_tests']}</p>
                <p>Success Rate: {summary['success_rate']}%</p>
                <p>Duration: {summary['total_duration']}s</p>
            </div>
        """

        # Add suite details
        for suite_name, suite_data in results["suites"].items():
            status_class = "passed" if suite_data["status"] == "passed" else "failed"
            html += f"""
            <div class="suite">
                <h3 class="{status_class}">{suite_name}</h3>
                <p>Status: {suite_data['status']}</p>
                <p>Duration: {suite_data['duration']:.3f}s</p>
                <p>Tests: {len(suite_data['results'])}</p>
            </div>
            """

        html += "</body></html>"
        return html

    def _generate_junit_report(self, results: Dict[str, Any]) -> str:
        """Generate JUnit XML test report"""
        summary = results["summary"]

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="LyoBackend" tests="{summary['total_tests']}"
           failures="{summary['failed_tests']}" errors="{summary['error_tests']}"
           time="{summary['total_duration']:.3f}">
"""

        for suite_name, suite_data in results["suites"].items():
            suite_stats = summary['suites_summary'][suite_name]
            xml += f"""
    <testsuite name="{suite_name}" tests="{suite_stats['total']}"
               failures="{suite_stats['failed']}" errors="{suite_stats['error']}"
               time="{suite_stats['duration']:.3f}">
"""

            for result in suite_data['results']:
                xml += f"""
        <testcase name="{result.test_name}" time="{result.duration:.3f}">
"""
                if result.status == TestStatus.FAILED:
                    xml += f"""
            <failure message="{result.error_message or 'Test failed'}"/>
"""
                elif result.status == TestStatus.ERROR:
                    xml += f"""
            <error message="{result.error_message or 'Test error'}"/>
"""

                xml += "        </testcase>\n"

            xml += "    </testsuite>\n"

        xml += "</testsuites>"
        return xml

    async def run_continuous_testing(self, interval_minutes: int = 30,
                                   test_types: List[TestType] = None):
        """Run continuous testing at specified intervals"""
        logger.info(f"Starting continuous testing every {interval_minutes} minutes")

        while True:
            try:
                logger.info("Starting continuous test run")
                results = await self.run_all_tests(test_types)

                # Save results with timestamp
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                report_file = f"test_report_{timestamp}.json"

                with open(report_file, 'w') as f:
                    f.write(self.generate_report(results, "json"))

                logger.info(f"Test results saved to {report_file}")
                logger.info(f"Success rate: {results['summary']['success_rate']}%")

                # Wait for next run
                await asyncio.sleep(interval_minutes * 60)

            except Exception as e:
                logger.error(f"Continuous testing error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

# Global test orchestrator instance
test_orchestrator = TestOrchestrator()