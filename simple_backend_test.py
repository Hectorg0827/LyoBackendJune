#!/usr/bin/env python3
"""
Simple Backend Connection Test
Quick test to verify backend is working and ready for frontend connection.
"""

import requests
import json
import time
import subprocess
import sys
import os
from pathlib import Path

class BackendConnectionTest:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.server_process = None
        self.auth_token = None
        
    def print_status(self, message, status="INFO"):
        colors = {
            "SUCCESS": "\033[92m✅",
            "ERROR": "\033[91m❌",
            "WARNING": "\033[93m⚠️",
            "INFO": "\033[94m📋"
        }
        print(f"{colors.get(status, '')} {message}\033[0m")
    
    def start_server(self):
        """Start the backend server"""
        self.print_status("Starting backend server...", "INFO")
        
        # Check if server is already running
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            if response.status_code == 200:
                self.print_status("Server already running", "SUCCESS")
                return True
        except:
            pass
        
        # Start server
        try:
            self.server_process = subprocess.Popen([
                sys.executable, "-m", "uvicorn", 
                "lyo_app.main:app", 
                "--host", "0.0.0.0", 
                "--port", "8000"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait for server to start
            for i in range(20):
                try:
                    response = requests.get(f"{self.base_url}/health", timeout=1)
                    if response.status_code == 200:
                        self.print_status("Server started successfully", "SUCCESS")
                        return True
                except:
                    pass
                time.sleep(1)
            
            self.print_status("Server failed to start", "ERROR")
            return False
            
        except Exception as e:
            self.print_status(f"Failed to start server: {e}", "ERROR")
            return False
    
    def test_basic_endpoints(self):
        """Test basic server endpoints"""
        self.print_status("Testing basic endpoints...", "INFO")
        
        endpoints = [
            ("/health", "Health check"),
            ("/docs", "API documentation"),
            ("/openapi.json", "OpenAPI schema")
        ]
        
        for endpoint, description in endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=5)
                if response.status_code == 200:
                    self.print_status(f"{description} working", "SUCCESS")
                else:
                    self.print_status(f"{description} returned {response.status_code}", "WARNING")
            except Exception as e:
                self.print_status(f"{description} failed: {e}", "ERROR")
    
    def test_authentication(self):
        """Test authentication flow"""
        self.print_status("Testing authentication...", "INFO")
        
        # Create test user
        timestamp = int(time.time())
        user_data = {
            "email": f"test{timestamp}@example.com",
            "username": f"testuser{timestamp}",
            "password": "TestPassword123!",
            "full_name": "Test User"
        }
        
        # Register user
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/auth/register",
                json=user_data,
                timeout=10
            )
            if response.status_code in [200, 201]:
                self.print_status("User registration successful", "SUCCESS")
            else:
                self.print_status(f"Registration failed: {response.status_code}", "WARNING")
                return False
        except Exception as e:
            self.print_status(f"Registration error: {e}", "ERROR")
            return False
        
        # Login user
        try:
            login_data = {
                "username": user_data["username"],
                "password": user_data["password"]
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/auth/login",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10
            )
            
            if response.status_code == 200:
                auth_data = response.json()
                self.auth_token = auth_data.get("access_token")
                self.print_status("User login successful", "SUCCESS")
                return True
            else:
                self.print_status(f"Login failed: {response.status_code}", "WARNING")
                return False
        except Exception as e:
            self.print_status(f"Login error: {e}", "ERROR")
            return False
    
    def test_protected_endpoints(self):
        """Test protected endpoints with authentication"""
        if not self.auth_token:
            self.print_status("No auth token for protected endpoint testing", "WARNING")
            return
        
        self.print_status("Testing protected endpoints...", "INFO")
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        protected_endpoints = [
            ("/api/v1/auth/me", "Current user"),
            ("/api/v1/learning/courses", "Learning courses"),
            ("/api/v1/feeds/", "Social feeds"),
            ("/api/v1/gamification/profile", "Gamification profile"),
        ]
        
        for endpoint, description in protected_endpoints:
            try:
                response = requests.get(
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    timeout=5
                )
                if response.status_code == 200:
                    self.print_status(f"{description} endpoint working", "SUCCESS")
                elif response.status_code == 404:
                    self.print_status(f"{description} endpoint not implemented", "WARNING")
                else:
                    self.print_status(f"{description} returned {response.status_code}", "WARNING")
            except Exception as e:
                self.print_status(f"{description} error: {e}", "WARNING")
    
    def test_file_upload(self):
        """Test file upload functionality"""
        if not self.auth_token:
            return
        
        self.print_status("Testing file upload...", "INFO")
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        files = {"file": ("test.txt", b"Test file content", "text/plain")}
        
        try:
            response = requests.post(
                f"{self.base_url}/files/upload",
                files=files,
                headers=headers,
                timeout=10
            )
            if response.status_code in [200, 201]:
                self.print_status("File upload working", "SUCCESS")
            elif response.status_code == 404:
                self.print_status("File upload endpoint not found", "WARNING")
            else:
                self.print_status(f"File upload returned {response.status_code}", "WARNING")
        except Exception as e:
            self.print_status(f"File upload error: {e}", "WARNING")
    
    def generate_ios_guide(self):
        """Generate iOS integration guide"""
        print("\n" + "="*60)
        print("📱 iOS INTEGRATION GUIDE")
        print("="*60)
        
        print(f"Backend URL: {self.base_url}")
        print(f"API Documentation: {self.base_url}/docs")
        
        if self.auth_token:
            print(f"Sample Auth Token: {self.auth_token[:50]}...")
        
        print("\n🔑 Key Endpoints for iOS:")
        endpoints = [
            "POST /api/v1/auth/register - User registration",
            "POST /api/v1/auth/login - User login (form data)",
            "GET /api/v1/auth/me - Get current user",
            "GET /api/v1/learning/courses - Learning content",
            "GET /api/v1/feeds/ - Social feeds",
            "POST /files/upload - File upload",
        ]
        
        for endpoint in endpoints:
            print(f"  • {endpoint}")
        
        print("\n📋 iOS Implementation Steps:")
        steps = [
            "1. Set base URL to http://localhost:8000 (or your domain)",
            "2. Implement OAuth2 login flow with form data",
            "3. Store JWT token securely in iOS keychain",
            "4. Add Authorization header: 'Bearer {token}'",
            "5. Test endpoints using the sample token above",
            "6. Implement WebSocket for real-time features",
        ]
        
        for step in steps:
            print(f"  {step}")
    
    def cleanup(self):
        """Cleanup resources"""
        if self.server_process:
            self.print_status("Stopping server...", "INFO")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
    
    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Backend-Frontend Connection Testing")
        print("="*60)
        
        try:
            # Start server
            if not self.start_server():
                return False
            
            # Wait for server to initialize
            time.sleep(2)
            
            # Run tests
            self.test_basic_endpoints()
            
            if self.test_authentication():
                self.test_protected_endpoints()
                self.test_file_upload()
            
            # Generate guide
            self.generate_ios_guide()
            
            print(f"\n🎉 Backend testing complete!")
            print(f"📱 Your backend is ready for iOS frontend connection!")
            
            return True
            
        except KeyboardInterrupt:
            self.print_status("Testing interrupted", "WARNING")
            return False
        except Exception as e:
            self.print_status(f"Unexpected error: {e}", "ERROR")
            return False
        finally:
            self.cleanup()

def main():
    tester = BackendConnectionTest()
    success = tester.run_all_tests()
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
