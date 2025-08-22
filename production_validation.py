#!/usr/bin/env python3
"""
Comprehensive production validation script for LyoBackend
Validates all systems, configurations, and production readiness
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
import psutil

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set environment for testing
os.environ.setdefault("ENVIRONMENT", "production")

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

class ProductionValidator:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.api_base = f"{self.base_url}/api/v1"
        self.client = None
        self.test_user_token = None
        self.admin_token = None
        self.results = []
        
    async def print_status(self, message: str, status: str = "INFO"):
        """Print colored status message."""
        if status == "SUCCESS":
            print(f"{Colors.GREEN}✅ {message}{Colors.END}")
        elif status == "ERROR":
            print(f"{Colors.RED}❌ {message}{Colors.END}")
        elif status == "WARNING":
            print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")
        elif status == "INFO":
            print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")
        else:
            print(f"{Colors.CYAN}🔄 {message}{Colors.END}")
    
    def add_result(self, test_name: str, passed: bool, message: str = ""):
        """Add test result."""
        self.results.append({
            "test": test_name,
            "passed": passed,
            "message": message
        })
    
    async def wait_for_server(self, max_retries: int = 30) -> bool:
        """Wait for server to be ready."""
        await self.print_status("Waiting for server to start...", "INFO")
        
        for i in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.base_url}/health", timeout=5)
                    if response.status_code == 200:
                        await self.print_status("Server is ready!", "SUCCESS")
                        return True
            except Exception:
                await asyncio.sleep(1)
                if i % 5 == 0:
                    await self.print_status(f"Still waiting... ({i}/{max_retries})", "PROCESSING")
        
        await self.print_status("Server failed to start", "ERROR")
        return False
    
    async def test_database_setup(self) -> bool:
        """Test database connectivity and tables."""
        try:
            await self.print_status("Testing database setup...", "PROCESSING")
            
            # Check if database file exists
            db_path = Path("lyo_app_dev.db")
            if not db_path.exists():
                await self.print_status("Database file not found", "ERROR")
                self.add_result("Database Setup", False, "Database file missing")
                return False
            
            # Test connection and basic tables
            conn = sqlite3.connect("lyo_app_dev.db")
            cursor = conn.cursor()
            
            # Check if main tables exist
            tables = ["users", "learning_paths", "posts", "communities", "user_achievements"]
            for table in tables:
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if not cursor.fetchone():
                    await self.print_status(f"Table {table} not found", "ERROR")
                    self.add_result("Database Setup", False, f"Missing table: {table}")
                    conn.close()
                    return False
            
            conn.close()
            await self.print_status("Database setup verified", "SUCCESS")
            self.add_result("Database Setup", True)
            return True
            
        except Exception as e:
            await self.print_status(f"Database test failed: {e}", "ERROR")
            self.add_result("Database Setup", False, str(e))
            return False
    
    async def test_health_endpoints(self) -> bool:
        """Test all health check endpoints."""
        try:
            await self.print_status("Testing health endpoints...", "PROCESSING")
            
            async with httpx.AsyncClient() as client:
                # Basic health check
                response = await client.get(f"{self.base_url}/health")
                if response.status_code != 200:
                    raise Exception(f"Basic health check failed: {response.status_code}")
                
                # Detailed health check
                response = await client.get(f"{self.base_url}/health/detailed")
                if response.status_code != 200:
                    raise Exception(f"Detailed health check failed: {response.status_code}")
                
                health_data = response.json()
                if not health_data.get("status") == "healthy":
                    raise Exception(f"System not healthy: {health_data}")
                
                # Check readiness
                response = await client.get(f"{self.base_url}/health/ready")
                if response.status_code != 200:
                    raise Exception(f"Readiness check failed: {response.status_code}")
                
                await self.print_status("Health endpoints working", "SUCCESS")
                self.add_result("Health Endpoints", True)
                return True
                
        except Exception as e:
            await self.print_status(f"Health endpoints failed: {e}", "ERROR")
            self.add_result("Health Endpoints", False, str(e))
            return False
    
    async def test_authentication_flow(self) -> bool:
        """Test complete authentication flow."""
        try:
            await self.print_status("Testing authentication flow...", "PROCESSING")
            
            async with httpx.AsyncClient() as client:
                # Test user registration
                user_data = {
                    "username": "testuser_prod",
                    "email": "testuser@production.test",
                    "password": "SecurePassword123!",
                    "full_name": "Test User Production"
                }
                
                response = await client.post(f"{self.api_base}/auth/register", json=user_data)
                if response.status_code not in [200, 201]:
                    # User might already exist, try to login
                    login_data = {
                        "username": user_data["username"],
                        "password": user_data["password"]
                    }
                    response = await client.post(f"{self.api_base}/auth/login", data=login_data)
                    if response.status_code != 200:
                        raise Exception(f"Login failed: {response.status_code} - {response.text}")
                else:
                    # Registration successful, now login
                    login_data = {
                        "username": user_data["username"],
                        "password": user_data["password"]
                    }
                    response = await client.post(f"{self.api_base}/auth/login", data=login_data)
                    if response.status_code != 200:
                        raise Exception(f"Login after registration failed: {response.status_code}")
                
                token_data = response.json()
                self.test_user_token = token_data["access_token"]
                
                # Test protected endpoint
                headers = {"Authorization": f"Bearer {self.test_user_token}"}
                response = await client.get(f"{self.api_base}/auth/me", headers=headers)
                if response.status_code != 200:
                    raise Exception(f"Protected endpoint failed: {response.status_code}")
                
                user_info = response.json()
                if user_info["username"] != user_data["username"]:
                    raise Exception("User info mismatch")
                
                await self.print_status("Authentication flow working", "SUCCESS")
                self.add_result("Authentication Flow", True)
                return True
                
        except Exception as e:
            await self.print_status(f"Authentication test failed: {e}", "ERROR")
            self.add_result("Authentication Flow", False, str(e))
            return False
    
    async def test_rbac_system(self) -> bool:
        """Test Role-Based Access Control."""
        try:
            await self.print_status("Testing RBAC system...", "PROCESSING")
            
            if not self.test_user_token:
                raise Exception("No user token available for RBAC testing")
            
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {self.test_user_token}"}
                
                # Test admin endpoint (should fail for regular user)
                response = await client.get(f"{self.api_base}/admin/users", headers=headers)
                if response.status_code == 200:
                    raise Exception("Regular user accessed admin endpoint")
                
                if response.status_code not in [401, 403]:
                    raise Exception(f"Unexpected RBAC response: {response.status_code}")
                
                await self.print_status("RBAC system working", "SUCCESS")
                self.add_result("RBAC System", True)
                return True
                
        except Exception as e:
            await self.print_status(f"RBAC test failed: {e}", "ERROR")
            self.add_result("RBAC System", False, str(e))
            return False
    
    async def test_core_modules(self) -> bool:
        """Test all core application modules."""
        try:
            await self.print_status("Testing core modules...", "PROCESSING")
            
            if not self.test_user_token:
                raise Exception("No user token available")
            
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {self.test_user_token}"}
                
                # Test learning module
                response = await client.get(f"{self.api_base}/learning/paths", headers=headers)
                if response.status_code not in [200, 404]:  # 404 is OK if no paths exist
                    raise Exception(f"Learning module failed: {response.status_code}")
                
                # Test feeds module
                response = await client.get(f"{self.api_base}/feeds/", headers=headers)
                if response.status_code not in [200, 404]:
                    raise Exception(f"Feeds module failed: {response.status_code}")
                
                # Test community module
                response = await client.get(f"{self.api_base}/community/communities", headers=headers)
                if response.status_code not in [200, 404]:
                    raise Exception(f"Community module failed: {response.status_code}")
                
                # Test gamification module
                response = await client.get(f"{self.api_base}/gamification/leaderboard", headers=headers)
                if response.status_code not in [200, 404]:
                    raise Exception(f"Gamification module failed: {response.status_code}")
                
                await self.print_status("Core modules working", "SUCCESS")
                self.add_result("Core Modules", True)
                return True
                
        except Exception as e:
            await self.print_status(f"Core modules test failed: {e}", "ERROR")
            self.add_result("Core Modules", False, str(e))
            return False
    
    async def test_file_upload_system(self) -> bool:
        """Test file upload functionality."""
        try:
            await self.print_status("Testing file upload system...", "PROCESSING")
            
            if not self.test_user_token:
                raise Exception("No user token available")
            
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {self.test_user_token}"}
                
                # Test file list endpoint
                response = await client.get(f"{self.base_url}/files/", headers=headers)
                if response.status_code not in [200, 404]:
                    raise Exception(f"File list endpoint failed: {response.status_code}")
                
                await self.print_status("File upload system accessible", "SUCCESS")
                self.add_result("File Upload System", True)
                return True
                
        except Exception as e:
            await self.print_status(f"File upload test failed: {e}", "ERROR")
            self.add_result("File Upload System", False, str(e))
            return False
    
    async def test_email_system(self) -> bool:
        """Test email verification system."""
        try:
            await self.print_status("Testing email system...", "PROCESSING")
            
            async with httpx.AsyncClient() as client:
                # Test password reset request (should not fail even if email doesn't exist)
                reset_data = {"email": "nonexistent@test.com"}
                response = await client.post(f"{self.base_url}/auth/password-reset/request", json=reset_data)
                if response.status_code not in [200, 202, 404]:
                    raise Exception(f"Password reset request failed: {response.status_code}")
                
                await self.print_status("Email system accessible", "SUCCESS")
                self.add_result("Email System", True)
                return True
                
        except Exception as e:
            await self.print_status(f"Email system test failed: {e}", "ERROR")
            self.add_result("Email System", False, str(e))
            return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling and exception management."""
        try:
            await self.print_status("Testing error handling...", "PROCESSING")
            
            async with httpx.AsyncClient() as client:
                # Test 404 handling
                response = await client.get(f"{self.base_url}/nonexistent-endpoint")
                if response.status_code != 404:
                    raise Exception(f"404 handling failed: {response.status_code}")
                
                # Test malformed JSON
                response = await client.post(
                    f"{self.api_base}/auth/register",
                    content="invalid json",
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code not in [400, 422]:
                    raise Exception(f"Malformed JSON handling failed: {response.status_code}")
                
                await self.print_status("Error handling working", "SUCCESS")
                self.add_result("Error Handling", True)
                return True
                
        except Exception as e:
            await self.print_status(f"Error handling test failed: {e}", "ERROR")
            self.add_result("Error Handling", False, str(e))
            return False
    
    async def test_production_config(self) -> bool:
        """Test production configuration files."""
        try:
            await self.print_status("Testing production configuration...", "PROCESSING")
            
            # Check required files exist
            required_files = [
                "requirements.txt",
                "Dockerfile",
                "docker-compose.yml",
                "deploy.sh",
                "setup_production_db.py",
                ".env.example",
                "alembic.ini"
            ]
            
            for file_path in required_files:
                if not Path(file_path).exists():
                    raise Exception(f"Required file missing: {file_path}")
            
            # Check GitHub Actions workflow
            workflow_path = Path(".github/workflows/ci-cd.yml")
            if not workflow_path.exists():
                raise Exception("CI/CD workflow missing")
            
            await self.print_status("Production configuration verified", "SUCCESS")
            self.add_result("Production Config", True)
            return True
            
        except Exception as e:
            await self.print_status(f"Production config test failed: {e}", "ERROR")
            self.add_result("Production Config", False, str(e))
            return False
    
    async def generate_report(self):
        """Generate comprehensive test report."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}         LYOAPP PRODUCTION VALIDATION REPORT{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}\n")
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        print(f"{Colors.BOLD}Overall Status: {Colors.END}", end="")
        if passed == total:
            print(f"{Colors.GREEN}ALL TESTS PASSED ✅{Colors.END}")
        else:
            print(f"{Colors.RED}SOME TESTS FAILED ❌{Colors.END}")
        
        print(f"{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.END}\n")
        
        # Detailed results
        for result in self.results:
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            color = Colors.GREEN if result["passed"] else Colors.RED
            print(f"{color}{status}{Colors.END} {result['test']}")
            if result["message"]:
                print(f"      {Colors.YELLOW}→ {result['message']}{Colors.END}")
        
        # Production readiness assessment
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}PRODUCTION READINESS ASSESSMENT:{Colors.END}")
        
        critical_tests = [
            "Database Setup",
            "Health Endpoints", 
            "Authentication Flow",
            "RBAC System",
            "Production Config"
        ]
        
        critical_passed = sum(1 for r in self.results 
                            if r["test"] in critical_tests and r["passed"])
        
        if critical_passed == len(critical_tests):
            print(f"{Colors.GREEN}🚀 READY FOR PRODUCTION DEPLOYMENT{Colors.END}")
            print(f"{Colors.GREEN}   All critical systems operational{Colors.END}")
        else:
            print(f"{Colors.RED}⚠️  NOT READY FOR PRODUCTION{Colors.END}")
            print(f"{Colors.RED}   Critical systems need attention{Colors.END}")
        
        print(f"\n{Colors.BOLD}Next Steps:{Colors.END}")
        if passed == total:
            print(f"{Colors.GREEN}• Deploy to production environment{Colors.END}")
            print(f"{Colors.GREEN}• Configure production databases{Colors.END}")
            print(f"{Colors.GREEN}• Set up monitoring and alerting{Colors.END}")
            print(f"{Colors.GREEN}• Schedule regular health checks{Colors.END}")
        else:
            print(f"{Colors.YELLOW}• Fix failing tests before deployment{Colors.END}")
            print(f"{Colors.YELLOW}• Review error messages above{Colors.END}")
            print(f"{Colors.YELLOW}• Re-run validation after fixes{Colors.END}")
        
        print(f"\n{Colors.CYAN}{'='*80}{Colors.END}")

async def main():
    """Run comprehensive production validation."""
    validator = ProductionValidator()
    
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                    LYOAPP PRODUCTION VALIDATION SUITE                       ║")
    print("║                                                                              ║")
    print("║  Comprehensive testing of all production-ready features                     ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.END}\n")
    
    # Start server if not running
    server_ready = await validator.wait_for_server(max_retries=5)
    if not server_ready:
        await validator.print_status("Starting server...", "PROCESSING")
        # Try to start server
        try:
            subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "lyo_app.main:app", 
                "--host", "0.0.0.0", 
                "--port", "8000"
            ], cwd=Path.cwd())
            server_ready = await validator.wait_for_server(max_retries=20)
        except Exception as e:
            await validator.print_status(f"Failed to start server: {e}", "ERROR")
    
    if not server_ready:
        await validator.print_status("Cannot proceed without server", "ERROR")
        return
    
    # Run all tests
    await validator.test_database_setup()
    await validator.test_health_endpoints()
    await validator.test_authentication_flow()
    await validator.test_rbac_system()
    await validator.test_core_modules()
    await validator.test_file_upload_system()
    await validator.test_email_system()
    await validator.test_error_handling()
    await validator.test_production_config()
    
    # Generate final report
    await validator.generate_report()

if __name__ == "__main__":
    asyncio.run(main())
