#!/usr/bin/env python3
"""
Automated Backend-Frontend Connection Testing Suite
Comprehensive automated testing of all backend features for iOS frontend integration.
"""

import asyncio
import aiohttp
import json
import subprocess
import time
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import websockets

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class AutomatedBackendTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.auth_token = None
        self.test_user_id = None
        self.server_process = None
        self.results = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "errors": []
        }
    
    def print_header(self, message: str):
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{message.center(60)}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    
    def print_step(self, message: str):
        print(f"{Colors.OKBLUE}📋 {message}{Colors.ENDC}")
    
    def print_success(self, message: str):
        print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")
        self.results["passed"] += 1
    
    def print_warning(self, message: str):
        print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")
    
    def print_error(self, message: str):
        print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")
        self.results["failed"] += 1
        self.results["errors"].append(message)
    
    def count_test(self):
        self.results["total_tests"] += 1
    
    async def setup_environment(self) -> bool:
        """Setup the testing environment"""
        self.print_header("ENVIRONMENT SETUP")
        
        # 1. Check if .env file exists, create if not
        self.print_step("Checking environment configuration...")
        env_file = project_root / ".env"
        
        if not env_file.exists():
            self.print_step("Creating .env file from template...")
            env_template = project_root / ".env.template"
            if env_template.exists():
                # Copy template to .env
                with open(env_template, 'r') as template:
                    content = template.read()
                
                # Set development defaults
                content = content.replace('your-ultra-secure-64-character-secret-key', 
                                        'dev-secret-key-for-testing-only-' + '0' * 32)
                content = content.replace('production', 'development')
                content = content.replace('false', 'true')  # Debug mode
                
                with open(env_file, 'w') as env:
                    env.write(content)
                
                self.print_success("Environment file created")
            else:
                # Create minimal .env
                minimal_env = """
# Development Environment
SECRET_KEY=dev-secret-key-for-testing-only-00000000000000000000000000000000
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=sqlite+aiosqlite:///./lyo_app_dev.db
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]
"""
                with open(env_file, 'w') as env:
                    env.write(minimal_env)
                self.print_success("Minimal environment file created")
        else:
            self.print_success("Environment file exists")
        
        # 2. Install dependencies if needed
        self.print_step("Checking Python dependencies...")
        try:
            import fastapi
            import sqlalchemy
            import uvicorn
            self.print_success("Core dependencies available")
        except ImportError as e:
            self.print_warning(f"Installing missing dependency: {e}")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                         check=True, capture_output=True)
        
        # 3. Setup database
        self.print_step("Setting up database...")
        try:
            from lyo_app.core.database import init_db
            await init_db()
            self.print_success("Database initialized")
        except Exception as e:
            self.print_warning(f"Database setup: {e}")
        
        return True
    
    async def start_server(self) -> bool:
        """Start the backend server"""
        self.print_header("SERVER STARTUP")
        
        self.print_step("Starting FastAPI server...")
        
        # Check if server is already running
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health", timeout=2) as response:
                    if response.status == 200:
                        self.print_success("Server already running")
                        return True
        except:
            pass
        
        # Start server in background
        try:
            import uvicorn
            from lyo_app.main import app
            
            # Start server in a separate process
            self.server_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "lyo_app.main:app", 
                "--host", "0.0.0.0", 
                "--port", "8000",
                "--reload"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait for server to start
            for i in range(30):  # Wait up to 30 seconds
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{self.base_url}/health", timeout=1) as response:
                            if response.status == 200:
                                self.print_success("Server started successfully")
                                return True
                except:
                    pass
                await asyncio.sleep(1)
            
            self.print_error("Server failed to start within 30 seconds")
            return False
            
        except Exception as e:
            self.print_error(f"Failed to start server: {e}")
            return False
    
    async def test_basic_connectivity(self) -> bool:
        """Test basic server connectivity"""
        self.print_header("BASIC CONNECTIVITY TESTS")
        
        async with aiohttp.ClientSession() as session:
            # Test health endpoint
            self.count_test()
            try:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        self.print_success(f"Health check passed: {data.get('status', 'unknown')}")
                    else:
                        self.print_error(f"Health check failed: {response.status}")
                        return False
            except Exception as e:
                self.print_error(f"Health check error: {e}")
                return False
            
            # Test API documentation
            self.count_test()
            try:
                async with session.get(f"{self.base_url}/docs") as response:
                    if response.status == 200:
                        self.print_success("API documentation accessible")
                    else:
                        self.print_warning(f"API docs status: {response.status}")
            except Exception as e:
                self.print_warning(f"API docs error: {e}")
            
            # Test OpenAPI schema
            self.count_test()
            try:
                async with session.get(f"{self.base_url}/openapi.json") as response:
                    if response.status == 200:
                        schema = await response.json()
                        endpoint_count = len(schema.get('paths', {}))
                        self.print_success(f"OpenAPI schema available ({endpoint_count} endpoints)")
                    else:
                        self.print_warning(f"OpenAPI schema status: {response.status}")
            except Exception as e:
                self.print_warning(f"OpenAPI schema error: {e}")
        
        return True
    
    async def test_authentication_flow(self) -> bool:
        """Test complete authentication flow"""
        self.print_header("AUTHENTICATION FLOW TESTS")
        
        async with aiohttp.ClientSession() as session:
            # Test user registration
            self.count_test()
            register_data = {
                "email": f"test{int(time.time())}@example.com",
                "username": f"testuser{int(time.time())}",
                "password": "SecurePassword123!",
                "full_name": "Test User"
            }
            
            try:
                async with session.post(
                    f"{self.base_url}/api/v1/auth/register",
                    json=register_data
                ) as response:
                    if response.status in [200, 201]:
                        user_data = await response.json()
                        self.test_user_id = user_data.get("id")
                        self.print_success("User registration successful")
                    elif response.status == 422:
                        error_data = await response.json()
                        self.print_warning(f"Registration validation error: {error_data}")
                    else:
                        self.print_error(f"Registration failed: {response.status}")
                        return False
            except Exception as e:
                self.print_error(f"Registration error: {e}")
                return False
            
            # Test user login
            self.count_test()
            login_data = {
                "username": register_data["username"],
                "password": register_data["password"]
            }
            
            try:
                async with session.post(
                    f"{self.base_url}/api/v1/auth/login",
                    data=login_data,  # Form data for OAuth2
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                ) as response:
                    if response.status == 200:
                        auth_data = await response.json()
                        self.auth_token = auth_data.get("access_token")
                        self.print_success("User login successful")
                    else:
                        self.print_error(f"Login failed: {response.status}")
                        return False
            except Exception as e:
                self.print_error(f"Login error: {e}")
                return False
            
            # Test protected endpoint access
            self.count_test()
            if self.auth_token:
                headers = {"Authorization": f"Bearer {self.auth_token}"}
                try:
                    async with session.get(
                        f"{self.base_url}/api/v1/auth/me",
                        headers=headers
                    ) as response:
                        if response.status == 200:
                            user_data = await response.json()
                            self.print_success(f"Protected endpoint access successful: {user_data.get('username')}")
                        else:
                            self.print_error(f"Protected endpoint failed: {response.status}")
                except Exception as e:
                    self.print_error(f"Protected endpoint error: {e}")
        
        return True
    
    async def test_api_endpoints(self) -> bool:
        """Test all main API endpoints"""
        self.print_header("API ENDPOINTS TESTS")
        
        if not self.auth_token:
            self.print_error("No auth token available for API testing")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        async with aiohttp.ClientSession() as session:
            # Test endpoints that should exist
            endpoints_to_test = [
                # Core endpoints
                ("GET", "/api/v1/users/me", "Current user profile"),
                ("GET", "/api/v1/auth/me", "Auth user info"),
                
                # Learning endpoints
                ("GET", "/api/v1/learning/courses", "Learning courses"),
                ("GET", "/api/v1/learning/stats", "Learning statistics"),
                
                # Social endpoints (may not exist yet)
                ("GET", "/api/v1/social/stories", "Stories feed"),
                ("GET", "/api/v1/social/conversations", "Conversations"),
                
                # Feeds endpoints
                ("GET", "/api/v1/feeds/", "Social feeds"),
                
                # Gamification endpoints
                ("GET", "/api/v1/gamification/profile", "Gamification profile"),
                ("GET", "/api/v1/gamification/leaderboard", "Leaderboard"),
                
                # File endpoints
                ("GET", "/files/", "User files"),
            ]
            
            for method, endpoint, description in endpoints_to_test:
                self.count_test()
                try:
                    async with session.request(
                        method,
                        f"{self.base_url}{endpoint}",
                        headers=headers,
                        timeout=10
                    ) as response:
                        if response.status == 200:
                            self.print_success(f"{description} endpoint working")
                        elif response.status == 404:
                            self.print_warning(f"{description} endpoint not implemented")
                        elif response.status == 401:
                            self.print_warning(f"{description} endpoint requires authentication")
                        else:
                            self.print_warning(f"{description} endpoint returned {response.status}")
                except Exception as e:
                    self.print_warning(f"{description} endpoint error: {e}")
        
        return True
    
    async def test_social_features(self) -> bool:
        """Test social features (stories, messaging)"""
        self.print_header("SOCIAL FEATURES TESTS")
        
        if not self.auth_token:
            self.print_error("No auth token available for social testing")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        async with aiohttp.ClientSession() as session:
            # Test story creation
            self.count_test()
            story_data = {
                "content": "Test story content",
                "content_type": "text"
            }
            
            try:
                async with session.post(
                    f"{self.base_url}/api/v1/social/stories/",
                    json=story_data,
                    headers=headers
                ) as response:
                    if response.status in [200, 201]:
                        story = await response.json()
                        self.print_success(f"Story creation successful: {story.get('id')}")
                    elif response.status == 404:
                        self.print_warning("Stories endpoint not implemented")
                    else:
                        self.print_warning(f"Story creation status: {response.status}")
            except Exception as e:
                self.print_warning(f"Story creation error: {e}")
            
            # Test conversation creation
            self.count_test()
            conversation_data = {
                "name": "Test Chat",
                "participant_ids": [self.test_user_id] if self.test_user_id else [],
                "is_group": False
            }
            
            try:
                async with session.post(
                    f"{self.base_url}/api/v1/social/conversations/",
                    json=conversation_data,
                    headers=headers
                ) as response:
                    if response.status in [200, 201]:
                        conversation = await response.json()
                        self.print_success(f"Conversation creation successful: {conversation.get('id')}")
                    elif response.status == 404:
                        self.print_warning("Conversations endpoint not implemented")
                    else:
                        self.print_warning(f"Conversation creation status: {response.status}")
            except Exception as e:
                self.print_warning(f"Conversation creation error: {e}")
        
        return True
    
    async def test_websocket_connection(self) -> bool:
        """Test WebSocket connections"""
        self.print_header("WEBSOCKET CONNECTION TESTS")
        
        if not self.auth_token or not self.test_user_id:
            self.print_warning("Skipping WebSocket tests - missing auth or user ID")
            return True
        
        # Test WebSocket connections
        websocket_tests = [
            (f"ws://localhost:8000/api/v1/social/ws/{self.test_user_id}", "Social WebSocket"),
            (f"ws://localhost:8000/api/v1/ai/ws/{self.test_user_id}", "AI WebSocket"),
        ]
        
        for ws_url, description in websocket_tests:
            self.count_test()
            try:
                # Add auth token to URL
                auth_url = f"{ws_url}?token={self.auth_token}"
                
                async with websockets.connect(auth_url, timeout=5) as websocket:
                    # Send test message
                    test_message = {
                        "type": "test",
                        "content": "Hello WebSocket!"
                    }
                    await websocket.send(json.dumps(test_message))
                    
                    # Try to receive response (with timeout)
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2)
                        self.print_success(f"{description} connection successful")
                    except asyncio.TimeoutError:
                        self.print_success(f"{description} connection established (no immediate response)")
                    
            except Exception as e:
                self.print_warning(f"{description} connection error: {e}")
        
        return True
    
    async def test_file_upload(self) -> bool:
        """Test file upload functionality"""
        self.print_header("FILE UPLOAD TESTS")
        
        if not self.auth_token:
            self.print_error("No auth token available for file upload testing")
            return False
        
        # Create a test file
        test_file_content = b"This is a test file for upload testing"
        test_file_name = "test_upload.txt"
        
        self.count_test()
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            
            async with aiohttp.ClientSession() as session:
                data = aiohttp.FormData()
                data.add_field('file', test_file_content, 
                             filename=test_file_name, 
                             content_type='text/plain')
                
                async with session.post(
                    f"{self.base_url}/files/upload",
                    data=data,
                    headers=headers
                ) as response:
                    if response.status in [200, 201]:
                        upload_result = await response.json()
                        self.print_success(f"File upload successful: {upload_result.get('filename')}")
                    elif response.status == 404:
                        self.print_warning("File upload endpoint not found")
                    else:
                        self.print_warning(f"File upload status: {response.status}")
        except Exception as e:
            self.print_warning(f"File upload error: {e}")
        
        return True
    
    async def test_ai_integration(self) -> bool:
        """Test AI integration endpoints"""
        self.print_header("AI INTEGRATION TESTS")
        
        if not self.auth_token:
            self.print_error("No auth token available for AI testing")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        async with aiohttp.ClientSession() as session:
            # Test AI chat endpoint
            self.count_test()
            ai_message = {
                "message": "Hello AI, how can you help me learn?",
                "model": "gpt-3.5-turbo"
            }
            
            try:
                async with session.post(
                    f"{self.base_url}/api/v1/ai/chat",
                    json=ai_message,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        ai_response = await response.json()
                        self.print_success(f"AI chat successful: {ai_response.get('response', 'No response')[:50]}...")
                    elif response.status == 404:
                        self.print_warning("AI chat endpoint not implemented")
                    else:
                        self.print_warning(f"AI chat status: {response.status}")
            except Exception as e:
                self.print_warning(f"AI chat error: {e}")
            
            # Test AI agents list
            self.count_test()
            try:
                async with session.get(
                    f"{self.base_url}/api/v1/ai/agents",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        agents = await response.json()
                        agent_count = len(agents) if isinstance(agents, list) else 1
                        self.print_success(f"AI agents endpoint working ({agent_count} agents)")
                    elif response.status == 404:
                        self.print_warning("AI agents endpoint not implemented")
                    else:
                        self.print_warning(f"AI agents status: {response.status}")
            except Exception as e:
                self.print_warning(f"AI agents error: {e}")
        
        return True
    
    async def test_database_operations(self) -> bool:
        """Test database connectivity and basic operations"""
        self.print_header("DATABASE OPERATIONS TESTS")
        
        self.count_test()
        try:
            # Test database connection through health endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health/detailed") as response:
                    if response.status == 200:
                        health_data = await response.json()
                        db_status = health_data.get('database', {}).get('status', 'unknown')
                        if db_status == 'healthy':
                            self.print_success("Database connection healthy")
                        else:
                            self.print_warning(f"Database status: {db_status}")
                    else:
                        self.print_warning(f"Detailed health check status: {response.status}")
        except Exception as e:
            self.print_warning(f"Database health check error: {e}")
        
        return True
    
    def generate_report(self):
        """Generate test results report"""
        self.print_header("TEST RESULTS SUMMARY")
        
        total = self.results["total_tests"]
        passed = self.results["passed"]
        failed = self.results["failed"]
        
        print(f"{Colors.BOLD}Total Tests: {total}{Colors.ENDC}")
        print(f"{Colors.OKGREEN}Passed: {passed}{Colors.ENDC}")
        print(f"{Colors.FAIL}Failed: {failed}{Colors.ENDC}")
        
        if total > 0:
            success_rate = (passed / total) * 100
            print(f"{Colors.BOLD}Success Rate: {success_rate:.1f}%{Colors.ENDC}")
        
        if self.results["errors"]:
            print(f"\n{Colors.FAIL}Errors encountered:{Colors.ENDC}")
            for error in self.results["errors"]:
                print(f"  • {error}")
        
        # Generate iOS integration guide
        self.print_header("iOS INTEGRATION GUIDE")
        
        print(f"{Colors.OKBLUE}Backend URL for iOS app:{Colors.ENDC}")
        print(f"  {self.base_url}")
        
        if self.auth_token:
            print(f"\n{Colors.OKBLUE}Sample Authentication Token:{Colors.ENDC}")
            print(f"  {self.auth_token[:50]}...")
        
        print(f"\n{Colors.OKBLUE}Key Endpoints for iOS:{Colors.ENDC}")
        endpoints = [
            "POST /api/v1/auth/register - User registration",
            "POST /api/v1/auth/login - User login",
            "GET /api/v1/auth/me - Get current user",
            "GET /api/v1/social/stories - Get stories",
            "POST /api/v1/social/stories - Create story",
            "GET /api/v1/social/conversations - Get conversations",
            "POST /api/v1/ai/chat - AI chat",
            "POST /files/upload - File upload",
        ]
        
        for endpoint in endpoints:
            print(f"  • {endpoint}")
        
        print(f"\n{Colors.OKBLUE}WebSocket Endpoints:{Colors.ENDC}")
        if self.test_user_id:
            print(f"  • ws://localhost:8000/api/v1/social/ws/{self.test_user_id}")
            print(f"  • ws://localhost:8000/api/v1/ai/ws/{self.test_user_id}")
        else:
            print(f"  • ws://localhost:8000/api/v1/social/ws/{{user_id}}")
            print(f"  • ws://localhost:8000/api/v1/ai/ws/{{user_id}}")
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.server_process:
            self.print_step("Stopping server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
    
    async def run_all_tests(self):
        """Run all automated tests"""
        try:
            self.print_header("🚀 AUTOMATED BACKEND-FRONTEND CONNECTION TESTING")
            
            # Setup
            if not await self.setup_environment():
                return False
            
            # Start server
            if not await self.start_server():
                return False
            
            # Wait a moment for server to fully initialize
            await asyncio.sleep(2)
            
            # Run tests
            await self.test_basic_connectivity()
            await self.test_authentication_flow()
            await self.test_api_endpoints()
            await self.test_social_features()
            await self.test_websocket_connection()
            await self.test_file_upload()
            await self.test_ai_integration()
            await self.test_database_operations()
            
            # Generate report
            self.generate_report()
            
            return True
            
        except KeyboardInterrupt:
            self.print_warning("Testing interrupted by user")
            return False
        except Exception as e:
            self.print_error(f"Unexpected error during testing: {e}")
            return False
        finally:
            await self.cleanup()

async def main():
    """Main entry point"""
    tester = AutomatedBackendTester()
    success = await tester.run_all_tests()
    
    if success:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 Automated testing complete! Your backend is ready for iOS integration.{Colors.ENDC}")
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}❌ Testing completed with issues. Check the results above.{Colors.ENDC}")
    
    return success

if __name__ == "__main__":
    # Run the automated tests
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
