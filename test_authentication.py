#!/usr/bin/env python3
"""
Authentication System Testing and Validation Script.
Tests user registration, login, and protected endpoint access.
"""

import asyncio
import httpx
import json
from typing import Dict, Optional

# Test configuration
API_BASE_URL = "http://localhost:8000"
TEST_USER_DATA = {
    "username": "testuser123",
    "email": "test@lyoapp.com",
    "password": "TestPassword123!",
    "full_name": "Test User"
}

class AuthTester:
    """Authentication system tester."""
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.access_token: Optional[str] = None
        self.user_data: Optional[Dict] = None
    
    async def test_server_health(self) -> bool:
        """Test if the server is running."""
        print("🔍 Testing server health...")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ Server is healthy: {data}")
                    return True
                else:
                    print(f"❌ Server health check failed: {response.status_code}")
                    return False
        except Exception as e:
            print(f"❌ Cannot connect to server: {e}")
            return False
    
    async def test_user_registration(self) -> bool:
        """Test user registration."""
        print("\n👤 Testing user registration...")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/register",
                    json=TEST_USER_DATA
                )
                
                if response.status_code == 201:
                    self.user_data = response.json()
                    print(f"✅ User registered successfully:")
                    print(f"   ID: {self.user_data['id']}")
                    print(f"   Username: {self.user_data['username']}")
                    print(f"   Email: {self.user_data['email']}")
                    return True
                elif response.status_code == 400:
                    error_data = response.json()
                    if "already exists" in str(error_data):
                        print("ℹ️ User already exists, proceeding with login test")
                        return True
                    else:
                        print(f"❌ Registration failed: {error_data}")
                        return False
                else:
                    print(f"❌ Registration failed with status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False
    
    async def test_user_login(self) -> bool:
        """Test user login."""
        print("\n🔐 Testing user login...")
        
        try:
            # Prepare login data (email + password for our current implementation)
            login_data = {
                "email": TEST_USER_DATA["email"],  # Changed from username to email
                "password": TEST_USER_DATA["password"]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/login",
                    json=login_data
                )
                
                if response.status_code == 200:
                    token_data = response.json()
                    self.access_token = token_data["access_token"]
                    print(f"✅ Login successful:")
                    print(f"   Token type: {token_data['token_type']}")
                    print(f"   Access token: {self.access_token[:20]}...")
                    return True
                else:
                    print(f"❌ Login failed with status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    async def test_protected_endpoint(self) -> bool:
        """Test accessing a protected endpoint."""
        print("\n🛡️ Testing protected endpoint access...")
        
        if not self.access_token:
            print("❌ No access token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            async with httpx.AsyncClient() as client:
                # Test gamification achievements endpoint
                response = await client.get(
                    f"{self.base_url}/api/v1/gamification/achievements",
                    headers=headers
                )
                
                if response.status_code == 200:
                    achievements = response.json()
                    print(f"✅ Protected endpoint accessed successfully:")
                    print(f"   Achievements found: {len(achievements)}")
                    return True
                else:
                    print(f"❌ Protected endpoint access failed: {response.status_code} - {response.text}")
                    return False
        except Exception as e:
            print(f"❌ Protected endpoint error: {e}")
            return False
    
    async def test_gamification_features(self) -> bool:
        """Test gamification features with authentication."""
        print("\n🎮 Testing gamification features...")
        
        if not self.access_token:
            print("❌ No access token available")
            return False
        
        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            async with httpx.AsyncClient() as client:
                # Test 1: Award XP
                xp_data = {
                    "user_id": str(self.user_data["id"]) if self.user_data else "1",
                    "points": 50,
                    "action_type": "lesson_completed",
                    "source_id": "lesson-123"
                }
                
                response = await client.post(
                    f"{self.base_url}/api/v1/gamification/xp/award",
                    headers=headers,
                    json=xp_data
                )
                
                if response.status_code == 201:
                    xp_result = response.json()
                    print(f"✅ XP awarded successfully: {xp_result['points']} points")
                else:
                    print(f"⚠️ XP award failed: {response.status_code} - {response.text}")
                
                # Test 2: Check user stats
                response = await client.get(
                    f"{self.base_url}/api/v1/gamification/stats",
                    headers=headers
                )
                
                if response.status_code == 200:
                    stats = response.json()
                    print(f"✅ User stats retrieved: {stats}")
                    return True
                else:
                    print(f"⚠️ Stats retrieval failed: {response.status_code}")
                    return False
                    
        except Exception as e:
            print(f"❌ Gamification features error: {e}")
            return False
    
    async def test_unauthorized_access(self) -> bool:
        """Test that unauthorized access is properly blocked."""
        print("\n🚫 Testing unauthorized access protection...")
        
        try:
            async with httpx.AsyncClient() as client:
                # Test without token
                response = await client.get(
                    f"{self.base_url}/api/v1/gamification/achievements"
                )
                
                if response.status_code == 403:
                    print("✅ Unauthorized access properly blocked (403 Forbidden)")
                    return True
                else:
                    print(f"⚠️ Expected 403, got {response.status_code}")
                    return False
        except Exception as e:
            print(f"❌ Unauthorized access test error: {e}")
            return False


async def start_server_if_needed() -> bool:
    """Start the server if it's not running."""
    print("🚀 Checking if server is running...")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/health", timeout=5.0)
            if response.status_code == 200:
                print("✅ Server is already running")
                return True
    except:
        pass
    
    print("🚀 Starting development server...")
    import subprocess
    import time
    
    # Start server in background
    process = subprocess.Popen([
        "python", "start_server.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for server to start
    for i in range(10):
        time.sleep(1)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{API_BASE_URL}/health", timeout=2.0)
                if response.status_code == 200:
                    print("✅ Server started successfully")
                    return True
        except:
            continue
    
    print("❌ Failed to start server")
    return False


async def main():
    """Run all authentication tests."""
    print("=" * 70)
    print("🔒 AUTHENTICATION SYSTEM TESTING")
    print("=" * 70)
    
    # Ensure server is running
    if not await start_server_if_needed():
        print("❌ Cannot start server, exiting...")
        return False
    
    # Create tester instance
    tester = AuthTester()
    
    # Run test suite
    tests = [
        ("Server Health", tester.test_server_health),
        ("User Registration", tester.test_user_registration),
        ("User Login", tester.test_user_login),
        ("Protected Endpoint Access", tester.test_protected_endpoint),
        ("Gamification Features", tester.test_gamification_features),
        ("Unauthorized Access Protection", tester.test_unauthorized_access),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 AUTHENTICATION TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All authentication tests passed!")
        print("✅ Authentication system is fully operational")
        return True
    else:
        print("⚠️ Some authentication tests failed")
        print("🔧 Check the failures above and fix any issues")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
