#!/usr/bin/env python3
"""
Production Validation Script for LyoBackendJune
Comprehensive testing of production deployment and all features.
"""
import asyncio
import aiohttp
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class ProductionValidator:
    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_token: Optional[str] = None
        self.test_results: List[Dict[str, Any]] = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def print_header(self, title: str):
        """Print a formatted header."""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{title.center(60)}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    def print_test(self, test_name: str, status: str, details: str = ""):
        """Print test result with color coding."""
        if status == "PASS":
            status_color = Colors.GREEN
            symbol = "✅"
        elif status == "FAIL":
            status_color = Colors.RED
            symbol = "❌"
        elif status == "WARN":
            status_color = Colors.YELLOW
            symbol = "⚠️"
        else:
            status_color = Colors.WHITE
            symbol = "ℹ️"
        
        print(f"{symbol} {test_name}: {status_color}{status}{Colors.END}")
        if details:
            print(f"   {Colors.CYAN}{details}{Colors.END}")
        
        self.test_results.append({
            "test": test_name,
            "status": status,
            "details": details
        })
    
    async def test_basic_connectivity(self):
        """Test basic application connectivity."""
        self.print_header("Basic Connectivity Tests")
        
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    self.print_test("Health Endpoint", "PASS", f"Status: {data.get('status', 'unknown')}")
                else:
                    self.print_test("Health Endpoint", "FAIL", f"HTTP {response.status}")
        except Exception as e:
            self.print_test("Health Endpoint", "FAIL", str(e))
        
        # Test API documentation
        try:
            async with self.session.get(f"{self.base_url}/docs") as response:
                if response.status == 200:
                    self.print_test("API Documentation", "PASS", "Swagger UI accessible")
                else:
                    self.print_test("API Documentation", "FAIL", f"HTTP {response.status}")
        except Exception as e:
            self.print_test("API Documentation", "FAIL", str(e))
        
        # Test OpenAPI schema
        try:
            async with self.session.get(f"{self.base_url}/openapi.json") as response:
                if response.status == 200:
                    schema = await response.json()
                    self.print_test("OpenAPI Schema", "PASS", f"Version: {schema.get('openapi', 'unknown')}")
                else:
                    self.print_test("OpenAPI Schema", "FAIL", f"HTTP {response.status}")
        except Exception as e:
            self.print_test("OpenAPI Schema", "FAIL", str(e))
    
    async def test_authentication_system(self):
        """Test authentication and user management."""
        self.print_header("Authentication System Tests")
        
        # Test user registration
        test_user = {
            "email": f"test_user_{asyncio.get_event_loop().time()}@example.com",
            "username": f"testuser_{int(asyncio.get_event_loop().time())}",
            "password": "SecureTestPassword123!",
            "full_name": "Test User"
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/register",
                json=test_user
            ) as response:
                if response.status == 201:
                    user_data = await response.json()
                    self.print_test("User Registration", "PASS", f"User ID: {user_data.get('id')}")
                else:
                    error_text = await response.text()
                    self.print_test("User Registration", "FAIL", f"HTTP {response.status}: {error_text}")
                    return
        except Exception as e:
            self.print_test("User Registration", "FAIL", str(e))
            return
        
        # Test user login
        try:
            login_data = {
                "email": test_user["email"],
                "password": test_user["password"]
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                json=login_data
            ) as response:
                if response.status == 200:
                    auth_data = await response.json()
                    self.auth_token = auth_data.get("access_token")
                    self.print_test("User Login", "PASS", "Access token received")
                else:
                    error_text = await response.text()
                    self.print_test("User Login", "FAIL", f"HTTP {response.status}: {error_text}")
        except Exception as e:
            self.print_test("User Login", "FAIL", str(e))
        
        # Test protected endpoint access
        if self.auth_token:
            try:
                headers = {"Authorization": f"Bearer {self.auth_token}"}
                async with self.session.get(
                    f"{self.base_url}/api/v1/auth/me",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        user_data = await response.json()
                        self.print_test("Protected Endpoint Access", "PASS", f"User: {user_data.get('email')}")
                    else:
                        self.print_test("Protected Endpoint Access", "FAIL", f"HTTP {response.status}")
            except Exception as e:
                self.print_test("Protected Endpoint Access", "FAIL", str(e))
    
    async def test_learning_resources(self):
        """Test learning resources functionality."""
        self.print_header("Learning Resources Tests")
        
        if not self.auth_token:
            self.print_test("Learning Resources Test", "SKIP", "No authentication token available")
            return
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Test resource discovery
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/learning/discover",
                headers=headers
            ) as response:
                if response.status == 200:
                    resources = await response.json()
                    self.print_test("Resource Discovery", "PASS", f"Found {len(resources)} resources")
                else:
                    self.print_test("Resource Discovery", "FAIL", f"HTTP {response.status}")
        except Exception as e:
            self.print_test("Resource Discovery", "FAIL", str(e))
        
        # Test resource search
        try:
            params = {"q": "python", "limit": 5}
            async with self.session.get(
                f"{self.base_url}/api/v1/learning/search",
                params=params,
                headers=headers
            ) as response:
                if response.status == 200:
                    search_results = await response.json()
                    self.print_test("Resource Search", "PASS", f"Found {len(search_results)} results")
                else:
                    self.print_test("Resource Search", "FAIL", f"HTTP {response.status}")
        except Exception as e:
            self.print_test("Resource Search", "FAIL", str(e))
    
    async def test_performance_metrics(self):
        """Test performance and monitoring endpoints."""
        self.print_header("Performance & Monitoring Tests")
        
        # Test metrics endpoint
        try:
            async with self.session.get(f"{self.base_url}/metrics") as response:
                if response.status == 200:
                    metrics_text = await response.text()
                    if "http_requests_total" in metrics_text:
                        self.print_test("Prometheus Metrics", "PASS", "Metrics endpoint functional")
                    else:
                        self.print_test("Prometheus Metrics", "WARN", "Metrics format unexpected")
                else:
                    self.print_test("Prometheus Metrics", "FAIL", f"HTTP {response.status}")
        except Exception as e:
            self.print_test("Prometheus Metrics", "FAIL", str(e))
        
        # Test response time
        import time
        start_time = time.time()
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                response_time = (time.time() - start_time) * 1000
                if response_time < 500:  # Less than 500ms
                    self.print_test("Response Time", "PASS", f"{response_time:.2f}ms")
                elif response_time < 1000:  # Less than 1 second
                    self.print_test("Response Time", "WARN", f"{response_time:.2f}ms (acceptable)")
                else:
                    self.print_test("Response Time", "FAIL", f"{response_time:.2f}ms (too slow)")
        except Exception as e:
            self.print_test("Response Time", "FAIL", str(e))
    
    async def test_database_connectivity(self):
        """Test database operations."""
        self.print_header("Database Connectivity Tests")
        
        if not self.auth_token:
            self.print_test("Database Test", "SKIP", "No authentication token available")
            return
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Test user stats (involves database query)
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/learning/stats",
                headers=headers
            ) as response:
                if response.status == 200:
                    stats = await response.json()
                    self.print_test("Database Operations", "PASS", f"Stats retrieved: {len(stats)} fields")
                else:
                    self.print_test("Database Operations", "FAIL", f"HTTP {response.status}")
        except Exception as e:
            self.print_test("Database Operations", "FAIL", str(e))
    
    async def test_external_services(self):
        """Test external service integrations."""
        self.print_header("External Services Tests")
        
        # Test if external API configurations are present
        config_tests = [
            ("YouTube API", "YOUTUBE_API_KEY"),
            ("OpenAI API", "OPENAI_API_KEY"),
            ("Anthropic API", "ANTHROPIC_API_KEY"),
            ("Gemini API", "GEMINI_API_KEY")
        ]
        
        for service_name, env_var in config_tests:
            if os.getenv(env_var):
                if os.getenv(env_var).startswith("your-") or len(os.getenv(env_var)) < 10:
                    self.print_test(f"{service_name} Configuration", "WARN", "Placeholder key detected")
                else:
                    self.print_test(f"{service_name} Configuration", "PASS", "API key configured")
            else:
                self.print_test(f"{service_name} Configuration", "FAIL", "API key missing")
    
    async def test_security_headers(self):
        """Test security headers and configurations."""
        self.print_header("Security Tests")
        
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                headers = response.headers
                
                security_headers = [
                    ("X-Frame-Options", "DENY"),
                    ("X-Content-Type-Options", "nosniff"),
                    ("X-XSS-Protection", "1; mode=block"),
                    ("Referrer-Policy", "strict-origin-when-cross-origin")
                ]
                
                for header_name, expected_value in security_headers:
                    if header_name in headers:
                        if expected_value in headers[header_name]:
                            self.print_test(f"Security Header: {header_name}", "PASS", headers[header_name])
                        else:
                            self.print_test(f"Security Header: {header_name}", "WARN", f"Unexpected value: {headers[header_name]}")
                    else:
                        self.print_test(f"Security Header: {header_name}", "FAIL", "Header missing")
        except Exception as e:
            self.print_test("Security Headers", "FAIL", str(e))
    
    def print_summary(self):
        """Print test summary."""
        self.print_header("Test Summary")
        
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if r["status"] == "PASS"])
        failed_tests = len([r for r in self.test_results if r["status"] == "FAIL"])
        warning_tests = len([r for r in self.test_results if r["status"] == "WARN"])
        skipped_tests = len([r for r in self.test_results if r["status"] == "SKIP"])
        
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {Colors.GREEN}{passed_tests}{Colors.END}")
        print(f"❌ Failed: {Colors.RED}{failed_tests}{Colors.END}")
        print(f"⚠️  Warnings: {Colors.YELLOW}{warning_tests}{Colors.END}")
        print(f"⏭️  Skipped: {Colors.BLUE}{skipped_tests}{Colors.END}")
        
        success_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        print(f"\n🎯 Success Rate: {success_rate:.1f}%")
        
        if failed_tests == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 All critical tests passed! Production deployment is ready.{Colors.END}")
        elif failed_tests <= 2:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  Minor issues detected. Review failed tests before production deployment.{Colors.END}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ Critical issues detected. Fix failed tests before production deployment.{Colors.END}")
        
        return failed_tests == 0

async def main():
    """Main validation function."""
    print(f"{Colors.BOLD}{Colors.PURPLE}🚀 LyoBackendJune Production Validation{Colors.END}")
    print(f"{Colors.CYAN}Testing production deployment readiness...{Colors.END}\n")
    
    # Test different base URLs
    test_urls = [
        "http://localhost",
        "http://localhost:8000"
    ]
    
    success = False
    
    for base_url in test_urls:
        print(f"\n{Colors.BOLD}Testing with base URL: {base_url}{Colors.END}")
        
        try:
            async with ProductionValidator(base_url) as validator:
                # Run all validation tests
                await validator.test_basic_connectivity()
                await validator.test_authentication_system()
                await validator.test_learning_resources()
                await validator.test_performance_metrics()
                await validator.test_database_connectivity()
                await validator.test_external_services()
                await validator.test_security_headers()
                
                # Print summary
                success = validator.print_summary()
                
                if success:
                    break  # If successful with this URL, no need to try others
                    
        except Exception as e:
            print(f"{Colors.RED}Failed to connect to {base_url}: {e}{Colors.END}")
            continue
    
    if not success:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ Validation failed. Please check the issues above.{Colors.END}")
        sys.exit(1)
    else:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ Production validation completed successfully!{Colors.END}")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())
