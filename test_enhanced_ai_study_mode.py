#!/usr/bin/env python3
"""
Enhanced AI Study Mode - Backend Intelligence Test
Test the new AI-powered study session and quiz generation endpoints
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any

# Test configuration
BASE_URL = "http://localhost:8000/api/v1/ai"
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "testpass123"

class StudyModeIntelligenceTest:
    """Test the enhanced AI study mode endpoints"""
    
    def __init__(self):
        self.session = None
        self.auth_token = None
        self.study_session_id = None
        self.quiz_id = None
    
    async def setup(self):
        """Set up test session and authentication"""
        self.session = aiohttp.ClientSession()
        print("🚀 Starting Enhanced AI Study Mode Intelligence Test")
        print("=" * 60)
        
        # For testing, we'll skip authentication and assume we have a token
        # In real usage, you'd authenticate first
        # self.auth_token = await self.authenticate()
        self.auth_token = "mock_token_for_testing"
    
    async def cleanup(self):
        """Clean up test session"""
        if self.session:
            await self.session.close()
    
    async def authenticate(self):
        """Authenticate and get access token"""
        auth_url = f"{BASE_URL.replace('/api/v1/ai', '')}/auth/login"
        payload = {
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        }
        
        try:
            async with self.session.post(auth_url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Authentication successful")
                    return data.get("access_token")
                else:
                    print(f"❌ Authentication failed: {response.status}")
                    return None
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return None
    
    async def test_health_check(self):
        """Test the enhanced health check endpoint"""
        print("\n🔍 Testing Enhanced Health Check...")
        
        try:
            url = f"{BASE_URL}/study-mode/health"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Health check passed")
                    print(f"   Status: {data.get('status')}")
                    print(f"   AI Services: {data.get('services', {})}")
                    print(f"   Features: {list(data.get('features', {}).keys())}")
                    return True
                else:
                    print(f"❌ Health check failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
    
    async def test_capabilities(self):
        """Test the enhanced capabilities endpoint"""
        print("\n🎯 Testing Enhanced Capabilities...")
        
        try:
            url = f"{BASE_URL}/study-mode/capabilities"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Capabilities retrieved")
                    print(f"   Tutoring Styles: {len(data.get('tutoring_styles', []))}")
                    print(f"   Quiz Types: {len(data.get('quiz_types', []))}")
                    print(f"   AI Features: {len(data.get('ai_features', {}))}")
                    return True
                else:
                    print(f"❌ Capabilities failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Capabilities error: {e}")
            return False
    
    async def test_create_study_session(self):
        """Test creating an AI-powered study session"""
        print("\n🧠 Testing AI Study Session Creation...")
        
        payload = {
            "resource_id": "lesson_123",
            "resource_type": "lesson",
            "tutoring_style": "socratic"
        }
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            url = f"{BASE_URL}/study-session"
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.study_session_id = data.get("session_id")
                    print(f"✅ AI Study session created")
                    print(f"   Session ID: {self.study_session_id}")
                    print(f"   Tutoring Style: {data.get('tutoring_style')}")
                    print(f"   Welcome Message: {data.get('welcome_message', '')[:100]}...")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Study session creation failed: {response.status}")
                    print(f"   Error: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Study session creation error: {e}")
            return False
    
    async def test_continue_study_session(self):
        """Test continuing an AI study session conversation"""
        if not self.study_session_id:
            print("⚠️  Skipping continue session test - no session ID")
            return False
        
        print("\n💬 Testing AI Study Session Continuation...")
        
        payload = {
            "user_input": "Can you explain the concept of machine learning?",
            "conversation_history": [
                {
                    "role": "user",
                    "content": "Hello, I want to learn about AI",
                    "timestamp": time.time() - 60
                }
            ]
        }
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            url = f"{BASE_URL}/study-session/{self.study_session_id}/continue"
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ AI Study session continued")
                    print(f"   AI Response: {data.get('response', '')[:150]}...")
                    print(f"   Tutoring Insights: {list(data.get('tutoring_insights', {}).keys())}")
                    print(f"   Suggested Next Steps: {len(data.get('suggested_next_steps', []))}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Study session continuation failed: {response.status}")
                    print(f"   Error: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Study session continuation error: {e}")
            return False
    
    async def test_generate_quiz(self):
        """Test AI-powered quiz generation"""
        print("\n📝 Testing AI Quiz Generation...")
        
        payload = {
            "resource_id": "lesson_123",
            "resource_type": "lesson",
            "quiz_type": "multiple_choice",
            "question_count": 5,
            "difficulty_level": "intermediate",
            "focus_areas": ["machine learning basics"],
            "learning_objectives": ["understand ML concepts"],
            "time_limit_minutes": 15
        }
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            url = f"{BASE_URL}/generate-quiz"
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.quiz_id = data.get("quiz_id")
                    print(f"✅ AI Quiz generated")
                    print(f"   Quiz ID: {self.quiz_id}")
                    print(f"   Title: {data.get('title')}")
                    print(f"   Questions: {data.get('total_questions')}")
                    print(f"   Estimated Duration: {data.get('estimated_duration_minutes')} minutes")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Quiz generation failed: {response.status}")
                    print(f"   Error: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Quiz generation error: {e}")
            return False
    
    async def test_adaptive_quiz(self):
        """Test adaptive quiz generation"""
        print("\n🎯 Testing Adaptive AI Quiz Generation...")
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            url = f"{BASE_URL}/generate-adaptive-quiz"
            params = {
                "resource_id": "lesson_123",
                "include_performance_history": True
            }
            async with self.session.post(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Adaptive AI Quiz generated")
                    print(f"   Quiz ID: {data.get('quiz_id')}")
                    print(f"   Difficulty: {data.get('difficulty_level')}")
                    print(f"   Questions: {data.get('total_questions')}")
                    print(f"   Subject Area: {data.get('subject_area')}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Adaptive quiz generation failed: {response.status}")
                    print(f"   Error: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Adaptive quiz generation error: {e}")
            return False
    
    async def test_get_session_history(self):
        """Test getting study session history"""
        if not self.study_session_id:
            print("⚠️  Skipping session history test - no session ID")
            return False
        
        print("\n📊 Testing AI Session History Retrieval...")
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            url = f"{BASE_URL}/study-session/{self.study_session_id}/history"
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ AI Session history retrieved")
                    print(f"   Messages: {data.get('message_count', 0)}")
                    print(f"   Session Type: {data.get('session_type')}")
                    print(f"   Analytics: {list(data.get('analytics', {}).keys())}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Session history retrieval failed: {response.status}")
                    print(f"   Error: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Session history retrieval error: {e}")
            return False
    
    async def test_list_sessions(self):
        """Test listing user study sessions"""
        print("\n📋 Testing AI Study Sessions List...")
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        try:
            url = f"{BASE_URL}/study-sessions"
            params = {"limit": 10, "offset": 0}
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ AI Study sessions listed")
                    print(f"   Total Sessions: {data.get('total', 0)}")
                    print(f"   AI Enhanced: {data.get('ai_enhanced', False)}")
                    print(f"   Sessions: {len(data.get('sessions', []))}")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Sessions list failed: {response.status}")
                    print(f"   Error: {error_text}")
                    return False
        except Exception as e:
            print(f"❌ Sessions list error: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all enhanced AI study mode tests"""
        await self.setup()
        
        # Test results tracking
        results = []
        
        # Run all tests
        test_methods = [
            ("Health Check", self.test_health_check),
            ("Capabilities", self.test_capabilities),
            ("Create Study Session", self.test_create_study_session),
            ("Continue Study Session", self.test_continue_study_session),
            ("Generate Quiz", self.test_generate_quiz),
            ("Adaptive Quiz", self.test_adaptive_quiz),
            ("Session History", self.test_get_session_history),
            ("List Sessions", self.test_list_sessions),
        ]
        
        for test_name, test_method in test_methods:
            try:
                success = await test_method()
                results.append((test_name, success))
            except Exception as e:
                print(f"❌ {test_name} failed with exception: {e}")
                results.append((test_name, False))
        
        # Print summary
        print("\n" + "=" * 60)
        print("🎯 ENHANCED AI STUDY MODE TEST SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} - {test_name}")
        
        print(f"\n📊 Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 All Enhanced AI Study Mode tests passed!")
        else:
            print("⚠️  Some tests failed - check the AI services and database connection")
        
        await self.cleanup()
        return passed == total


async def main():
    """Main test function"""
    print("🤖 Enhanced AI Study Mode - Backend Intelligence Test")
    print("Testing advanced AI-powered study sessions and quiz generation")
    print("=" * 60)
    
    tester = StudyModeIntelligenceTest()
    success = await tester.run_all_tests()
    
    if success:
        print("\n🚀 Ready for frontend integration!")
        print("The AI Study Mode backend intelligence is fully operational.")
    else:
        print("\n🔧 Some issues detected - please review the implementation.")
    
    return success


if __name__ == "__main__":
    asyncio.run(main())
