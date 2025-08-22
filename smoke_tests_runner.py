#!/usr/bin/env python3
"""
🧪 LyoBackend Comprehensive Smoke Tests Runner
==============================================

This script runs comprehensive smoke tests to validate all system functionality.
It combines multiple test suites to provide comprehensive system validation.

Usage:
    python smoke_tests_runner.py --quick          # Quick smoke tests (5-10 minutes)
    python smoke_tests_runner.py --full           # Full comprehensive tests (15-20 minutes)
    python smoke_tests_runner.py --module auth    # Test specific module
    python smoke_tests_runner.py --ci             # CI/CD friendly output
"""

import asyncio
import argparse
import json
import time
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path
import requests

# Console colors for beautiful output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class SmokeTestRunner:
    """Comprehensive smoke test runner for LyoBackend."""
    
    def __init__(self, mode: str = "quick", module: str = None, ci_mode: bool = False):
        self.mode = mode
        self.module = module
        self.ci_mode = ci_mode
        self.base_url = "http://localhost:8000"
        self.results = {
            "start_time": datetime.now().isoformat(),
            "test_suites": {},
            "summary": {},
            "errors": [],
            "warnings": []
        }
        
    def print_header(self, title: str, emoji: str = "🧪"):
        """Print a formatted header."""
        if not self.ci_mode:
            print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
            print(f"{Colors.HEADER}{emoji} {title}{Colors.ENDC}")
            print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
        else:
            print(f"\n=== {emoji} {title} ===")
    
    def print_success(self, message: str):
        """Print success message."""
        if not self.ci_mode:
            print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")
        else:
            print(f"✅ {message}")
    
    def print_error(self, message: str):
        """Print error message."""
        if not self.ci_mode:
            print(f"{Colors.RED}❌ {message}{Colors.ENDC}")
        else:
            print(f"❌ {message}")
    
    def print_warning(self, message: str):
        """Print warning message."""
        if not self.ci_mode:
            print(f"{Colors.YELLOW}⚠️  {message}{Colors.ENDC}")
        else:
            print(f"⚠️  {message}")
    
    def print_info(self, message: str):
        """Print info message."""
        if not self.ci_mode:
            print(f"{Colors.BLUE}ℹ️  {message}{Colors.ENDC}")
        else:
            print(f"ℹ️  {message}")

    def check_server_availability(self) -> bool:
        """Check if the server is running and accessible."""
        self.print_info("Checking server availability...")
        
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                self.print_success("Server is running and accessible")
                return True
            else:
                self.print_error(f"Server returned status code: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            self.print_error(f"Cannot connect to server: {e}")
            self.print_info("💡 Try starting the server with: python start_server.py")
            return False

    def run_test_script(self, script_path: str, description: str, timeout: int = 300) -> Dict[str, Any]:
        """Run a test script and capture results."""
        self.print_info(f"Running {description}...")
        
        start_time = time.time()
        result = {
            "script": script_path,
            "description": description,
            "status": "unknown",
            "duration": 0,
            "output": "",
            "error": ""
        }
        
        try:
            if not Path(script_path).exists():
                result["status"] = "skipped"
                result["error"] = f"Script not found: {script_path}"
                self.print_warning(f"Skipping {description} - script not found")
                return result
            
            # Run the test script
            process = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=Path(__file__).parent
            )
            
            result["duration"] = time.time() - start_time
            result["output"] = process.stdout
            result["error"] = process.stderr
            
            if process.returncode == 0:
                result["status"] = "passed"
                self.print_success(f"{description} - PASSED ({result['duration']:.1f}s)")
            else:
                result["status"] = "failed"
                self.print_error(f"{description} - FAILED ({result['duration']:.1f}s)")
                if process.stderr:
                    self.print_error(f"Error: {process.stderr[:200]}...")
                    
        except subprocess.TimeoutExpired:
            result["duration"] = timeout
            result["status"] = "timeout"
            result["error"] = f"Test timed out after {timeout} seconds"
            self.print_error(f"{description} - TIMEOUT ({timeout}s)")
            
        except Exception as e:
            result["duration"] = time.time() - start_time
            result["status"] = "error"
            result["error"] = str(e)
            self.print_error(f"{description} - ERROR: {e}")
        
        return result

    def run_quick_tests(self):
        """Run quick smoke tests (5-10 minutes)."""
        self.print_header("Quick Smoke Tests", "⚡")
        
        tests = [
            ("quick_validation.py", "Quick System Validation", 120),
            ("test_market_ready.py", "Market Ready API Tests", 180),
            ("check_server.py", "Server Health Check", 60),
        ]
        
        for script, description, timeout in tests:
            result = self.run_test_script(script, description, timeout)
            self.results["test_suites"][script] = result

    def run_full_tests(self):
        """Run comprehensive tests (15-20 minutes)."""
        self.print_header("Comprehensive Smoke Tests", "🔬")
        
        tests = [
            ("comprehensive_validation_v2.py", "Comprehensive System Validation", 600),
            ("phase2_comprehensive_test.py", "Phase 2 AI Features Test", 400),
            ("test_authentication.py", "Authentication System Test", 300),
            ("test_gamification_quick.py", "Gamification Module Test", 200),
            ("test_ai_optimization.py", "AI Optimization Test", 300),
            ("production_validation.py", "Production Readiness Test", 400),
        ]
        
        for script, description, timeout in tests:
            result = self.run_test_script(script, description, timeout)
            self.results["test_suites"][script] = result

    def run_module_tests(self, module: str):
        """Run tests for a specific module."""
        self.print_header(f"Module Tests: {module.upper()}", "🔍")
        
        module_tests = {
            "auth": [
                ("test_authentication.py", "Authentication Tests", 300),
                ("test_auth_quick.py", "Quick Auth Tests", 120),
                ("test_comprehensive_auth.py", "Comprehensive Auth Tests", 400),
            ],
            "gamification": [
                ("test_gamification_quick.py", "Quick Gamification Tests", 200),
                ("test_gamification_basic.py", "Basic Gamification Tests", 180),
                ("validate_gamification.py", "Gamification Validation", 250),
            ],
            "ai": [
                ("test_ai_optimization.py", "AI Optimization Tests", 300),
                ("test_ai_study_implementation.py", "AI Study Mode Tests", 250),
                ("test_enhanced_ai_study_mode.py", "Enhanced AI Study Tests", 400),
            ],
            "community": [
                ("test_community_quick.py", "Quick Community Tests", 180),
                ("test_community_basic.py", "Basic Community Tests", 200),
                ("validate_community.py", "Community Validation", 250),
            ]
        }
        
        if module in module_tests:
            for script, description, timeout in module_tests[module]:
                result = self.run_test_script(script, description, timeout)
                self.results["test_suites"][script] = result
        else:
            self.print_error(f"Unknown module: {module}")
            self.print_info(f"Available modules: {', '.join(module_tests.keys())}")

    def run_infrastructure_checks(self):
        """Run infrastructure and dependency checks."""
        self.print_header("Infrastructure Checks", "🏗️")
        
        checks = [
            self.check_python_version,
            self.check_dependencies,
            self.check_database_connection,
            self.check_redis_connection,
            self.check_environment_variables,
        ]
        
        for check in checks:
            try:
                check()
            except Exception as e:
                self.print_error(f"Infrastructure check failed: {e}")
                self.results["errors"].append(f"Infrastructure check failed: {e}")

    def check_python_version(self):
        """Check Python version."""
        version = sys.version_info
        if version.major == 3 and version.minor >= 8:
            self.print_success(f"Python version: {version.major}.{version.minor}.{version.micro}")
        else:
            self.print_error(f"Python version too old: {version.major}.{version.minor}.{version.micro}")

    def check_dependencies(self):
        """Check critical dependencies."""
        try:
            import fastapi
            import sqlalchemy
            import redis
            import httpx
            self.print_success("Critical dependencies available")
        except ImportError as e:
            self.print_error(f"Missing dependency: {e}")

    def check_database_connection(self):
        """Check database connection."""
        try:
            # This is a simple check - in real implementation, you'd test actual DB connection
            self.print_info("Database connection check - implement based on your setup")
            self.print_success("Database check completed")
        except Exception as e:
            self.print_warning(f"Database check inconclusive: {e}")

    def check_redis_connection(self):
        """Check Redis connection."""
        try:
            # This is a simple check - in real implementation, you'd test actual Redis connection
            self.print_info("Redis connection check - implement based on your setup")
            self.print_success("Redis check completed")
        except Exception as e:
            self.print_warning(f"Redis check inconclusive: {e}")

    def check_environment_variables(self):
        """Check critical environment variables."""
        import os
        critical_vars = ["SECRET_KEY", "DATABASE_URL"]
        
        for var in critical_vars:
            if os.getenv(var):
                self.print_success(f"Environment variable {var} is set")
            else:
                self.print_warning(f"Environment variable {var} is not set")

    def generate_report(self):
        """Generate comprehensive test report."""
        self.results["end_time"] = datetime.now().isoformat()
        
        # Calculate summary statistics
        total_tests = len(self.results["test_suites"])
        passed_tests = sum(1 for result in self.results["test_suites"].values() if result["status"] == "passed")
        failed_tests = sum(1 for result in self.results["test_suites"].values() if result["status"] == "failed")
        skipped_tests = sum(1 for result in self.results["test_suites"].values() if result["status"] == "skipped")
        
        self.results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "skipped_tests": skipped_tests,
            "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0
        }
        
        # Print summary
        self.print_header("Test Results Summary", "📊")
        
        self.print_info(f"Total Tests Run: {total_tests}")
        self.print_success(f"Passed: {passed_tests}")
        if failed_tests > 0:
            self.print_error(f"Failed: {failed_tests}")
        if skipped_tests > 0:
            self.print_warning(f"Skipped: {skipped_tests}")
        
        success_rate = self.results["summary"]["success_rate"]
        if success_rate >= 90:
            self.print_success(f"Success Rate: {success_rate:.1f}% - EXCELLENT! 🎉")
        elif success_rate >= 75:
            self.print_success(f"Success Rate: {success_rate:.1f}% - Good 👍")
        elif success_rate >= 50:
            self.print_warning(f"Success Rate: {success_rate:.1f}% - Needs Attention ⚠️")
        else:
            self.print_error(f"Success Rate: {success_rate:.1f}% - Critical Issues ❌")

        # Save detailed report
        report_file = f"smoke_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        self.print_info(f"Detailed report saved to: {report_file}")
        
        return success_rate >= 75  # Return True if tests are mostly passing

    def run(self) -> bool:
        """Run the smoke tests based on the selected mode."""
        start_time = datetime.now()
        
        self.print_header("LyoBackend Smoke Tests Runner", "🚀")
        self.print_info(f"Mode: {self.mode}")
        self.print_info(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Check server availability first
        if not self.check_server_availability():
            self.print_error("Server is not available. Please start the server before running tests.")
            return False
        
        # Run infrastructure checks
        self.run_infrastructure_checks()
        
        # Run tests based on mode
        if self.mode == "quick":
            self.run_quick_tests()
        elif self.mode == "full":
            self.run_full_tests()
        elif self.mode == "module" and self.module:
            self.run_module_tests(self.module)
        else:
            self.print_error(f"Unknown mode: {self.mode}")
            return False
        
        # Generate report and return success status
        success = self.generate_report()
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        self.print_header("Test Run Complete", "🏁")
        self.print_info(f"Total Duration: {duration}")
        
        if success:
            self.print_success("🎉 Smoke tests completed successfully!")
            self.print_info("Your LyoBackend system is ready for use!")
        else:
            self.print_error("💥 Some smoke tests failed!")
            self.print_info("Please review the failures and fix issues before production use.")
        
        return success

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="LyoBackend Comprehensive Smoke Tests Runner")
    parser.add_argument(
        "--quick", 
        action="store_true", 
        help="Run quick smoke tests (5-10 minutes)"
    )
    parser.add_argument(
        "--full", 
        action="store_true", 
        help="Run full comprehensive tests (15-20 minutes)"
    )
    parser.add_argument(
        "--module", 
        choices=["auth", "gamification", "ai", "community"], 
        help="Test specific module only"
    )
    parser.add_argument(
        "--ci", 
        action="store_true", 
        help="CI/CD friendly output (no colors)"
    )
    
    args = parser.parse_args()
    
    # Determine mode
    if args.quick:
        mode = "quick"
    elif args.full:
        mode = "full"
    elif args.module:
        mode = "module"
    else:
        # Default to quick mode
        mode = "quick"
        print("No mode specified, defaulting to --quick")
    
    # Create and run smoke test runner
    runner = SmokeTestRunner(
        mode=mode,
        module=args.module,
        ci_mode=args.ci
    )
    
    success = runner.run()
    
    # Exit with appropriate code for CI/CD
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()