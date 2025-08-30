#!/usr/bin/env python3
"""
Test runner script for LyoBackend.
Provides convenient commands to run different types of tests.
"""

import argparse
import asyncio
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Optional


class TestRunner:
    """Test runner for LyoBackend."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.tests_dir = self.project_root / "tests"
        self.pytest_ini = self.project_root / "pytest.ini"

    def run_unit_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run unit tests."""
        cmd = ["pytest", "-m", "unit"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_integration_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run integration tests."""
        cmd = ["pytest", "-m", "integration"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_api_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run API tests."""
        cmd = ["pytest", "-m", "api"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_performance_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run performance tests."""
        cmd = ["pytest", "-m", "performance"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_security_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run security tests."""
        cmd = ["pytest", "-m", "security"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_auth_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run authentication tests."""
        cmd = ["pytest", "-m", "auth"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_learning_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run learning module tests."""
        cmd = ["pytest", "-m", "learning"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_feeds_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run feeds/social tests."""
        cmd = ["pytest", "-m", "feeds"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_all_tests(self, exclude_slow: bool = True, verbose: bool = False) -> int:
        """Run all tests."""
        cmd = ["pytest"]

        if exclude_slow:
            cmd.append("-m")
            cmd.append("not slow")

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_specific_test(self, test_path: str, verbose: bool = False) -> int:
        """Run a specific test file or test function."""
        cmd = ["pytest", test_path]

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_with_coverage(self, test_type: Optional[str] = None, verbose: bool = False) -> int:
        """Run tests with coverage reporting."""
        cmd = ["pytest", "--cov=lyo_app", "--cov-report=term-missing", "--cov-report=html"]

        if test_type:
            cmd.extend(["-m", test_type])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_load_tests(self, endpoint: str, num_requests: int = 100, concurrent: int = 10) -> int:
        """Run load tests on a specific endpoint."""
        cmd = [
            "python", "-m", "pytest",
            "tests/test_performance.py::TestLoadTesting::test_endpoint_load",
            f"--endpoint={endpoint}",
            f"--num-requests={num_requests}",
            f"--concurrent={concurrent}",
            "-v"
        ]

        return self._run_command(cmd)

    def generate_test_report(self, output_format: str = "html") -> int:
        """Generate test report."""
        if output_format == "html":
            cmd = ["pytest", "--html=test_report.html", "--self-contained-html"]
        elif output_format == "junit":
            cmd = ["pytest", "--junitxml=test_report.xml"]
        else:
            print(f"Unsupported report format: {output_format}")
            return 1

        return self._run_command(cmd)

    def check_test_coverage(self, min_coverage: float = 80.0) -> int:
        """Check test coverage against minimum threshold."""
        cmd = [
            "pytest",
            f"--cov=lyo_app",
            f"--cov-fail-under={min_coverage}",
            "--cov-report=term-missing"
        ]

        return self._run_command(cmd)

    def run_database_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run database-related tests."""
        cmd = ["pytest", "-m", "database"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def run_async_tests(self, markers: Optional[List[str]] = None, verbose: bool = False) -> int:
        """Run async tests."""
        cmd = ["pytest", "-m", "async"]

        if markers:
            cmd.extend(["-k", " and ".join(markers)])

        if verbose:
            cmd.append("-v")

        return self._run_command(cmd)

    def _run_command(self, cmd: List[str]) -> int:
        """Run a command and return the exit code."""
        try:
            print(f"Running: {' '.join(cmd)}")
            print("-" * 50)

            # Change to project root directory
            os.chdir(self.project_root)

            result = subprocess.run(cmd, check=False)

            print("-" * 50)
            if result.returncode == 0:
                print("✅ Tests completed successfully!")
            else:
                print(f"❌ Tests failed with exit code: {result.returncode}")

            return result.returncode

        except FileNotFoundError:
            print(f"❌ Command not found: {cmd[0]}")
            print("Make sure pytest is installed and available in PATH")
            return 1
        except Exception as e:
            print(f"❌ Error running tests: {e}")
            return 1

    def list_test_files(self):
        """List all test files in the tests directory."""
        if not self.tests_dir.exists():
            print(f"Tests directory not found: {self.tests_dir}")
            return

        print("Test files found:")
        for test_file in sorted(self.tests_dir.glob("test_*.py")):
            print(f"  - {test_file.name}")

    def show_test_markers(self):
        """Show available test markers."""
        cmd = ["pytest", "--markers"]
        return self._run_command(cmd)

    def clean_test_cache(self):
        """Clean pytest cache."""
        cache_dir = self.project_root / ".pytest_cache"
        if cache_dir.exists():
            import shutil
            shutil.rmtree(cache_dir)
            print("✅ Pytest cache cleaned")
        else:
            print("No pytest cache found")

    def setup_test_environment(self):
        """Setup test environment."""
        print("Setting up test environment...")

        # Create necessary directories
        dirs = ["logs", "htmlcov", "test_reports"]
        for dir_name in dirs:
            (self.project_root / dir_name).mkdir(exist_ok=True)

        print("✅ Test environment setup complete")


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(description="LyoBackend Test Runner")
    parser.add_argument(
        "command",
        choices=[
            "unit", "integration", "api", "performance", "security",
            "auth", "learning", "feeds", "all", "coverage", "load",
            "report", "check-coverage", "database", "async",
            "list", "markers", "clean", "setup"
        ],
        help="Test command to run"
    )

    parser.add_argument(
        "--test-path",
        help="Specific test file or function to run"
    )

    parser.add_argument(
        "--markers",
        nargs="*",
        help="Additional pytest markers to filter tests"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    parser.add_argument(
        "--exclude-slow",
        action="store_true",
        default=True,
        help="Exclude slow tests (default: True)"
    )

    parser.add_argument(
        "--endpoint",
        help="Endpoint for load testing"
    )

    parser.add_argument(
        "--num-requests",
        type=int,
        default=100,
        help="Number of requests for load testing"
    )

    parser.add_argument(
        "--concurrent",
        type=int,
        default=10,
        help="Concurrent requests for load testing"
    )

    parser.add_argument(
        "--output-format",
        choices=["html", "junit"],
        default="html",
        help="Output format for reports"
    )

    parser.add_argument(
        "--min-coverage",
        type=float,
        default=80.0,
        help="Minimum coverage percentage"
    )

    args = parser.parse_args()

    runner = TestRunner()

    # Execute the requested command
    if args.command == "unit":
        exit_code = runner.run_unit_tests(args.markers, args.verbose)
    elif args.command == "integration":
        exit_code = runner.run_integration_tests(args.markers, args.verbose)
    elif args.command == "api":
        exit_code = runner.run_api_tests(args.markers, args.verbose)
    elif args.command == "performance":
        exit_code = runner.run_performance_tests(args.markers, args.verbose)
    elif args.command == "security":
        exit_code = runner.run_security_tests(args.markers, args.verbose)
    elif args.command == "auth":
        exit_code = runner.run_auth_tests(args.markers, args.verbose)
    elif args.command == "learning":
        exit_code = runner.run_learning_tests(args.markers, args.verbose)
    elif args.command == "feeds":
        exit_code = runner.run_feeds_tests(args.markers, args.verbose)
    elif args.command == "all":
        exit_code = runner.run_all_tests(args.exclude_slow, args.verbose)
    elif args.command == "coverage":
        exit_code = runner.run_with_coverage(None, args.verbose)
    elif args.command == "load":
        if not args.endpoint:
            print("❌ --endpoint is required for load testing")
            exit_code = 1
        else:
            exit_code = runner.run_load_tests(
                args.endpoint, args.num_requests, args.concurrent
            )
    elif args.command == "report":
        exit_code = runner.generate_test_report(args.output_format)
    elif args.command == "check-coverage":
        exit_code = runner.check_test_coverage(args.min_coverage)
    elif args.command == "database":
        exit_code = runner.run_database_tests(args.markers, args.verbose)
    elif args.command == "async":
        exit_code = runner.run_async_tests(args.markers, args.verbose)
    elif args.command == "list":
        runner.list_test_files()
        exit_code = 0
    elif args.command == "markers":
        exit_code = runner.show_test_markers()
    elif args.command == "clean":
        runner.clean_test_cache()
        exit_code = 0
    elif args.command == "setup":
        runner.setup_test_environment()
        exit_code = 0
    else:
        if args.test_path:
            exit_code = runner.run_specific_test(args.test_path, args.verbose)
        else:
            parser.print_help()
            exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
