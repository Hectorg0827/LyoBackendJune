#!/usr/bin/env python3
"""
🚀 LyoBackend Phase 2 Comprehensive Test Suite
Testing AI Content Generation + Social Study Groups
Experience the future of learning - AI tutoring + social collaboration
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from typing import Dict, List, Any
import random

# Test Configuration
BASE_URL = "http://localhost:8000"
TEST_USER = {
    "username": f"test_user_{random.randint(1000, 9999)}",
    "email": f"test{random.randint(1000, 9999)}@lyoapp.com",
    "password": "TestPass123!"
}

class LyoPhase2TestSuite:
    """Comprehensive Phase 2 Testing Suite"""
    
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.user_id = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def print_test_header(self, test_name: str):
        """Print formatted test header"""
        print(f"\n{'='*60}")
        print(f"🧪 {test_name}")
        print('='*60)
    
    def print_success(self, message: str):
        """Print success message"""
        print(f"✅ {message}")
    
    def print_error(self, message: str):
        """Print error message"""
        print(f"❌ {message}")
    
    def print_info(self, message: str):
        """Print info message"""
        print(f"ℹ️  {message}")
    
    async def test_server_health(self):
        """Test if server is running"""
        self.print_test_header("Server Health Check")
        
        try:
            async with self.session.get(f"{BASE_URL}/") as resp:
                if resp.status == 200:
                    self.print_success("Server is running")
                    return True
                else:
                    self.print_error(f"Server returned status {resp.status}")
                    return False
        except Exception as e:
            self.print_error(f"Server is not accessible: {e}")
            return False
    
    async def register_and_login(self):
        """Register a test user and login"""
        self.print_test_header("User Registration & Authentication")
        
        # Register user
        try:
            async with self.session.post(f"{BASE_URL}/api/v1/auth/register", 
                                       json=TEST_USER) as resp:
                if resp.status in [200, 201]:
                    self.print_success("User registered successfully")
                elif resp.status == 400:
                    # User might already exist, try to login
                    self.print_info("User may already exist, trying login...")
                else:
                    self.print_error(f"Registration failed: {resp.status}")
        except Exception as e:
            self.print_error(f"Registration error: {e}")
        
        # Login
        try:
            login_data = {
                "username": TEST_USER["username"],
                "password": TEST_USER["password"]
            }
            async with self.session.post(f"{BASE_URL}/api/v1/auth/login", 
                                       data=login_data) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.auth_token = data.get("access_token")
                    self.user_id = data.get("user_id")
                    self.print_success("Login successful")
                    return True
                else:
                    self.print_error(f"Login failed: {resp.status}")
                    return False
        except Exception as e:
            self.print_error(f"Login error: {e}")
            return False
    
    def get_auth_headers(self):
        """Get authorization headers"""
        return {"Authorization": f"Bearer {self.auth_token}"}
    
    async def test_ai_study_session(self):
        """Test AI Study Session Endpoint"""
        self.print_test_header("AI Study Session - Interactive Tutoring")
        
        # Sample study session request
        study_request = {
            "resourceId": "python_basics_101",
            "conversationHistory": [
                {"role": "user", "content": "I want to learn about Python variables"},
                {"role": "assistant", "content": "Great! Python variables are containers for storing data values."}
            ],
            "userInput": "Can you explain different data types in Python?"
        }
        
        try:
            async with self.session.post(
                f"{BASE_URL}/api/v1/ai/study-session",
                json=study_request,
                headers=self.get_auth_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.print_success("AI Study Session successful")
                    self.print_info(f"AI Response: {data.get('response', '')[:100]}...")
                    return True
                else:
                    text = await resp.text()
                    self.print_error(f"AI Study Session failed: {resp.status} - {text}")
                    return False
        except Exception as e:
            self.print_error(f"AI Study Session error: {e}")
            return False
    
    async def test_quiz_generation(self):
        """Test AI Quiz Generation"""
        self.print_test_header("AI Quiz Generation")
        
        quiz_request = {
            "resourceId": "python_basics_101",
            "quizType": "multiple_choice",
            "questionCount": 3
        }
        
        try:
            async with self.session.post(
                f"{BASE_URL}/api/v1/ai/generate-quiz",
                json=quiz_request,
                headers=self.get_auth_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.print_success("Quiz Generation successful")
                    self.print_info(f"Generated {len(data.get('questions', []))} questions")
                    return True
                else:
                    text = await resp.text()
                    self.print_error(f"Quiz Generation failed: {resp.status} - {text}")
                    return False
        except Exception as e:
            self.print_error(f"Quiz Generation error: {e}")
            return False
    
    async def test_content_explanation(self):
        """Test AI Content Explanation"""
        self.print_test_header("AI Content Explanation")
        
        explanation_request = {
            "content": "def factorial(n): return 1 if n <= 1 else n * factorial(n-1)",
            "explanationLevel": "beginner",
            "language": "python"
        }
        
        try:
            async with self.session.post(
                f"{BASE_URL}/api/v1/ai/explain-content",
                json=explanation_request,
                headers=self.get_auth_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.print_success("Content Explanation successful")
                    self.print_info(f"Explanation: {data.get('explanation', '')[:100]}...")
                    return True
                else:
                    text = await resp.text()
                    self.print_error(f"Content Explanation failed: {resp.status} - {text}")
                    return False
        except Exception as e:
            self.print_error(f"Content Explanation error: {e}")
            return False
    
    async def test_study_groups(self):
        """Test Study Groups Creation and Management"""
        self.print_test_header("Study Groups - Social Learning")
        
        # Create a study group
        group_data = {
            "name": f"Python Study Group {random.randint(100, 999)}",
            "description": "A collaborative group for learning Python programming",
            "subject": "Python Programming",
            "privacy": "public",
            "max_members": 10
        }
        
        try:
            async with self.session.post(
                f"{BASE_URL}/api/v1/study-groups",
                json=group_data,
                headers=self.get_auth_headers()
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    group_id = data.get("id")
                    self.print_success(f"Study Group created: {group_data['name']}")
                    return group_id
                else:
                    text = await resp.text()
                    self.print_error(f"Study Group creation failed: {resp.status} - {text}")
                    return None
        except Exception as e:
            self.print_error(f"Study Group creation error: {e}")
            return None
    
    async def test_personalized_feed(self):
        """Test Personalized Learning Feed"""
        self.print_test_header("Personalized Learning Feed")
        
        feed_request = {
            "feed_type": "courses",
            "limit": 5,
            "filters": {"subject": "programming"}
        }
        
        try:
            async with self.session.post(
                f"{BASE_URL}/api/v1/feeds/personalized",
                json=feed_request,
                headers=self.get_auth_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.print_success("Personalized Feed retrieved")
                    self.print_info(f"Retrieved {len(data.get('items', []))} feed items")
                    return True
                else:
                    text = await resp.text()
                    self.print_error(f"Personalized Feed failed: {resp.status} - {text}")
                    return False
        except Exception as e:
            self.print_error(f"Personalized Feed error: {e}")
            return False
    
    async def test_learning_analytics(self):
        """Test Learning Analytics"""
        self.print_test_header("Learning Analytics & Progress Tracking")
        
        try:
            async with self.session.get(
                f"{BASE_URL}/api/v1/analytics/progress",
                headers=self.get_auth_headers()
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.print_success("Learning Analytics retrieved")
                    self.print_info(f"Analytics data: {json.dumps(data, indent=2)[:200]}...")
                    return True
                else:
                    text = await resp.text()
                    self.print_error(f"Learning Analytics failed: {resp.status} - {text}")
                    return False
        except Exception as e:
            self.print_error(f"Learning Analytics error: {e}")
            return False
    
    async def run_comprehensive_test(self):
        """Run all Phase 2 tests"""
        print("🚀 Starting LyoBackend Phase 2 Comprehensive Test Suite")
        print(f"🎯 Testing AI-Powered Learning & Social Collaboration")
        print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Health Check
        if not await self.test_server_health():
            return False
        
        # Authentication
        if not await self.register_and_login():
            return False
        
        # Phase 2 Features Tests
        tests = [
            self.test_ai_study_session,
            self.test_quiz_generation,
            self.test_content_explanation,
            self.test_study_groups,
            self.test_personalized_feed,
            self.test_learning_analytics
        ]
        
        success_count = 0
        for test in tests:
            try:
                result = await test()
                if result:
                    success_count += 1
                await asyncio.sleep(1)  # Brief pause between tests
            except Exception as e:
                self.print_error(f"Test failed with exception: {e}")
        
        # Summary
        print(f"\n{'='*60}")
        print(f"🎯 TEST SUMMARY")
        print(f"{'='*60}")
        print(f"✅ Successful Tests: {success_count}/{len(tests)}")
        print(f"🔥 Success Rate: {(success_count/len(tests)*100):.1f}%")
        
        if success_count == len(tests):
            print(f"🎉 ALL TESTS PASSED! LyoBackend Phase 2 is ready!")
            print(f"🚀 Experience the future of learning - AI tutoring + social collaboration")
        else:
            print(f"⚠️  Some tests failed. Check the logs above for details.")
        
        print(f"⏰ Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return success_count == len(tests)

async def main():
    """Main test runner"""
    async with LyoPhase2TestSuite() as test_suite:
        await test_suite.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())
