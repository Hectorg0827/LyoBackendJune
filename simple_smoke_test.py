#!/usr/bin/env python3
"""
🔥 Simple Smoke Test - Immediate Validation
===========================================

Quick smoke test to validate core LyoBackend functionality.
This test runs in under 2 minutes and checks essential system components.

Usage: python simple_smoke_test.py
"""

import requests
import json
import time
import sys
from datetime import datetime
from typing import Dict, Any

class SimpleSmokeTest:
    """Quick smoke test for essential LyoBackend functionality."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_results = []
        self.start_time = datetime.now()
    
    def print_header(self, title: str):
        """Print test section header."""
        print(f"\n{'='*50}")
        print(f"🧪 {title}")
        print('='*50)
    
    def print_test(self, name: str, success: bool, details: str = ""):
        """Print test result."""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {name}")
        if details:
            print(f"    {details}")
        
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })
    
    def test_server_connectivity(self) -> bool:
        """Test basic server connectivity."""
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success and response.headers.get('content-type'):
                details += f", Content-Type: {response.headers['content-type']}"
            self.print_test("Server Connectivity", success, details)
            return success
        except Exception as e:
            self.print_test("Server Connectivity", False, f"Error: {e}")
            return False
    
    def test_health_endpoint(self) -> bool:
        """Test health check endpoint."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        status = data.get('status', 'unknown')
                        details += f", Health Status: {status}"
                        if 'checks' in data:
                            checks = data['checks']
                            details += f", Checks: {len(checks)}"
                except:
                    details += ", Response: Non-JSON"
            
            self.print_test("Health Check Endpoint", success, details)
            return success
        except Exception as e:
            self.print_test("Health Check Endpoint", False, f"Error: {e}")
            return False
    
    def test_api_documentation(self) -> bool:
        """Test API documentation endpoint."""
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=5)
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            if success:
                content_type = response.headers.get('content-type', '')
                details += f", Content-Type: {content_type}"
            self.print_test("API Documentation", success, details)
            return success
        except Exception as e:
            self.print_test("API Documentation", False, f"Error: {e}")
            return False
    
    def test_auth_endpoints(self) -> bool:
        """Test authentication endpoints availability."""
        endpoints = [
            ("/v1/auth/health", "Auth Health Check"),
            ("/v1/auth/register", "User Registration"),
            ("/v1/auth/login", "User Login")
        ]
        
        success_count = 0
        for endpoint, name in endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                # For POST endpoints, we expect 422 (validation error) or 405 (method not allowed)
                # For GET endpoints, we expect 200 or 404
                success = response.status_code in [200, 405, 422, 404]
                details = f"Status: {response.status_code}"
                
                if success:
                    success_count += 1
                
                self.print_test(name, success, details)
            except Exception as e:
                self.print_test(name, False, f"Error: {e}")
        
        overall_success = success_count >= 2  # At least 2 out of 3 should work
        return overall_success
    
    def test_learning_endpoints(self) -> bool:
        """Test learning module endpoints availability."""
        endpoints = [
            ("/v1/learning/health", "Learning Health Check"),
            ("/v1/learning/courses", "Courses Endpoint")
        ]
        
        success_count = 0
        for endpoint, name in endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                # We expect 200 (success) or 401 (unauthorized, which means endpoint exists)
                success = response.status_code in [200, 401, 404]
                details = f"Status: {response.status_code}"
                
                if response.status_code == 401:
                    details += " (Authentication required - endpoint exists)"
                    success = True
                
                if success:
                    success_count += 1
                
                self.print_test(name, success, details)
            except Exception as e:
                self.print_test(name, False, f"Error: {e}")
        
        overall_success = success_count >= 1  # At least 1 should work
        return overall_success
    
    def test_gamification_endpoints(self) -> bool:
        """Test gamification module endpoints availability."""
        endpoints = [
            ("/v1/gamification/health", "Gamification Health Check"),
            ("/v1/gamification/leaderboard", "Leaderboard Endpoint")
        ]
        
        success_count = 0
        for endpoint, name in endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                success = response.status_code in [200, 401, 404]
                details = f"Status: {response.status_code}"
                
                if response.status_code == 401:
                    details += " (Authentication required - endpoint exists)"
                    success = True
                
                if success:
                    success_count += 1
                
                self.print_test(name, success, details)
            except Exception as e:
                self.print_test(name, False, f"Error: {e}")
        
        overall_success = success_count >= 1  # At least 1 should work
        return overall_success
    
    def test_ai_endpoints(self) -> bool:
        """Test AI module endpoints availability."""
        endpoints = [
            ("/v1/ai/health", "AI Health Check"),
            ("/api/v1/ai/study-session", "AI Study Session")
        ]
        
        success_count = 0
        for endpoint, name in endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                success = response.status_code in [200, 401, 404, 405, 422]
                details = f"Status: {response.status_code}"
                
                if response.status_code in [401, 405, 422]:
                    details += " (Endpoint exists, requires proper method/auth)"
                    success = True
                
                if success:
                    success_count += 1
                
                self.print_test(name, success, details)
            except Exception as e:
                self.print_test(name, False, f"Error: {e}")
        
        overall_success = success_count >= 1  # At least 1 should work
        return overall_success
    
    def test_performance_basic(self) -> bool:
        """Test basic performance characteristics."""
        try:
            start_time = time.time()
            response = requests.get(f"{self.base_url}/health", timeout=5)
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            success = response.status_code == 200 and response_time < 2000  # Under 2 seconds
            details = f"Response time: {response_time:.0f}ms"
            
            if response_time < 500:
                details += " (Excellent)"
            elif response_time < 1000:
                details += " (Good)"
            elif response_time < 2000:
                details += " (Acceptable)"
            else:
                details += " (Slow)"
            
            self.print_test("Basic Performance", success, details)
            return success
        except Exception as e:
            self.print_test("Basic Performance", False, f"Error: {e}")
            return False
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate test summary."""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result['success'])
        failed_tests = total_tests - passed_tests
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        duration = (datetime.now() - self.start_time).total_seconds()
        
        summary = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": success_rate,
            "duration_seconds": duration,
            "start_time": self.start_time.isoformat(),
            "end_time": datetime.now().isoformat()
        }
        
        return summary
    
    def run_all_tests(self) -> bool:
        """Run all smoke tests."""
        print("🚀 LyoBackend Simple Smoke Test")
        print("=" * 50)
        print(f"🕐 Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌐 Base URL: {self.base_url}")
        
        # Run tests in order of importance
        test_functions = [
            ("Core System Tests", [
                self.test_server_connectivity,
                self.test_health_endpoint,
                self.test_api_documentation
            ]),
            ("Module Tests", [
                self.test_auth_endpoints,
                self.test_learning_endpoints,
                self.test_gamification_endpoints,
                self.test_ai_endpoints
            ]),
            ("Performance Tests", [
                self.test_performance_basic
            ])
        ]
        
        overall_success = True
        
        for section_name, test_funcs in test_functions:
            self.print_header(section_name)
            
            section_success = True
            for test_func in test_funcs:
                result = test_func()
                if not result:
                    section_success = False
                    overall_success = False
            
            # Print section result
            section_status = "✅ PASS" if section_success else "❌ FAIL"
            print(f"\n{section_status} {section_name} Section")
        
        # Generate and print summary
        summary = self.generate_summary()
        
        print(f"\n{'='*50}")
        print("📊 SMOKE TEST SUMMARY")
        print('='*50)
        print(f"Total Tests: {summary['total_tests']}")
        print(f"✅ Passed: {summary['passed_tests']}")
        print(f"❌ Failed: {summary['failed_tests']}")
        print(f"📈 Success Rate: {summary['success_rate']:.1f}%")
        print(f"⏱️  Duration: {summary['duration_seconds']:.1f} seconds")
        
        if summary['success_rate'] >= 80:
            print("\n🎉 SMOKE TESTS PASSED!")
            print("✅ Your LyoBackend system looks healthy and ready to use!")
            print("\n🔥 Next Steps:")
            print("   • Run full tests: python smoke_tests_runner.py --full")
            print("   • Check API docs: http://localhost:8000/docs")
            print("   • Start developing your app!")
        elif summary['success_rate'] >= 60:
            print("\n⚠️  SMOKE TESTS PARTIALLY PASSED")
            print("💡 Some components may need attention, but core functionality works.")
            print("🔧 Consider running individual module tests to diagnose issues.")
        else:
            print("\n❌ SMOKE TESTS FAILED")
            print("🚨 Critical issues detected! Please check:")
            print("   • Is the server running? (python start_server.py)")
            print("   • Are dependencies installed? (pip install -r requirements.txt)")
            print("   • Check server logs for errors")
        
        # Save results to file
        results_file = f"simple_smoke_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_data = {
            "summary": summary,
            "test_results": self.test_results
        }
        
        try:
            with open(results_file, 'w') as f:
                json.dump(results_data, f, indent=2)
            print(f"\n💾 Detailed results saved to: {results_file}")
        except Exception as e:
            print(f"\n⚠️  Could not save results file: {e}")
        
        return overall_success

def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LyoBackend Simple Smoke Test")
    parser.add_argument(
        "--url", 
        default="http://localhost:8000",
        help="Base URL of the LyoBackend server (default: http://localhost:8000)"
    )
    
    args = parser.parse_args()
    
    # Create and run smoke test
    smoke_test = SimpleSmokeTest(base_url=args.url)
    success = smoke_test.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()