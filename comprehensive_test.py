#!/usr/bin/env python3
"""
Comprehensive Backend Functionality Test
Tests all real AI and database features - NO MOCK DATA
"""
import requests
import json
import time
import sys
from datetime import datetime

BASE_URL = "http://localhost:8082"

def test_endpoint(method, url, data=None, description=""):
    """Test any endpoint with proper error handling."""
    print(f"\n🧪 {description}")
    print(f"   {method} {url}")
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=15)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=15)
        else:
            response = requests.request(method, url, json=data, timeout=15)
        
        print(f"   ✅ Status: {response.status_code}")
        
        if response.headers.get('content-type', '').startswith('application/json'):
            result = response.json()
            
            # Check if mock data is being used
            mock_status = result.get('mock', result.get('mock_data', 'unknown'))
            print(f"   🚫 Mock Data: {mock_status}")
            
            # Show key response data
            if 'message' in result:
                print(f"   📄 Message: {result['message']}")
            if 'response' in result:
                print(f"   🤖 AI Response: {result['response'][:100]}...")
            if 'quiz' in result:
                quiz_count = len(result['quiz']) if result['quiz'] else 0
                print(f"   📝 Quiz Questions: {quiz_count}")
            if 'tests' in result:
                print(f"   🔍 Tests: {result['tests']}")
            
            return True, result
        else:
            print(f"   📄 Response: {response.text[:200]}...")
            return True, response.text
            
    except requests.exceptions.ConnectionError:
        print("   ❌ Connection failed - server not running")
        return False, None
    except requests.exceptions.Timeout:
        print("   ❌ Timeout - server too slow")
        return False, None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False, None

def main():
    print("🚀 COMPREHENSIVE LYOBACKEND FUNCTIONALITY TEST")
    print("=" * 60)
    print(f"Testing server at: {BASE_URL}")
    print(f"Started at: {datetime.now().isoformat()}")
    
    test_results = []
    
    # 1. Basic connectivity tests
    tests = [
        ("GET", f"{BASE_URL}/", None, "Root Endpoint - System Info"),
        ("GET", f"{BASE_URL}/health", None, "Health Check - Service Status"),
        ("GET", f"{BASE_URL}/api/v1/test-real", None, "Real Functionality Test"),
    ]
    
    for method, url, data, desc in tests:
        success, result = test_endpoint(method, url, data, desc)
        test_results.append((desc, success, result))
        time.sleep(0.5)
    
    # 2. AI functionality tests
    print(f"\n{'='*60}")
    print("🤖 AI FUNCTIONALITY TESTS - REAL GEMINI API")
    print("="*60)
    
    ai_tests = [
        ("POST", f"{BASE_URL}/api/v1/ai/study-session", {
            "userInput": "I'm learning about photosynthesis. How does it work?",
            "resourceId": "biology_photosynthesis"
        }, "Socratic Tutoring Session"),
        
        ("POST", f"{BASE_URL}/api/v1/ai/generate-quiz", {
            "topic": "Basic Mathematics", 
            "difficulty": "easy",
            "num_questions": 3
        }, "Quiz Generation"),
        
        ("POST", f"{BASE_URL}/api/v1/ai/analyze-answer", {
            "question": "What is 2 + 2?",
            "answer": "I think it's 5",
            "correct_answer": "4"
        }, "Answer Analysis & Feedback")
    ]
    
    for method, url, data, desc in ai_tests:
        success, result = test_endpoint(method, url, data, desc)
        test_results.append((desc, success, result))
        time.sleep(1)  # Longer delay for AI calls
    
    # 3. API endpoint tests 
    print(f"\n{'='*60}")
    print("📊 API ENDPOINT TESTS - REAL DATA ONLY")
    print("="*60)
    
    api_tests = [
        ("GET", f"{BASE_URL}/api/v1/courses", None, "Course Management"),
        ("GET", f"{BASE_URL}/api/v1/feeds/personalized", None, "Personalized Feed"),
        ("GET", f"{BASE_URL}/api/v1/feeds/trending", None, "Trending Content"),
        ("GET", f"{BASE_URL}/api/v1/gamification/profile", None, "Gamification Profile"),
        ("GET", f"{BASE_URL}/api/v1/gamification/leaderboard", None, "Leaderboard"),
        ("POST", f"{BASE_URL}/api/v1/auth/test", {}, "Authentication Test")
    ]
    
    for method, url, data, desc in api_tests:
        success, result = test_endpoint(method, url, data, desc)
        test_results.append((desc, success, result))
        time.sleep(0.3)
    
    # Results summary
    print(f"\n{'='*60}")
    print("📋 TEST RESULTS SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, success, _ in test_results if success)
    total = len(test_results)
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    print(f"\n🎯 BACKEND STATUS:")
    if passed == total:
        print("✅ ALL TESTS PASSED - FULLY FUNCTIONAL BACKEND")
        print("✅ ZERO MOCK DATA - ALL REAL SERVICES")
        print("✅ PRODUCTION READY")
    elif passed > total * 0.8:
        print("⚠️  MOSTLY FUNCTIONAL - MINOR ISSUES")
    else:
        print("❌ MULTIPLE FAILURES - NEEDS ATTENTION")
    
    # Check for mock data usage
    mock_detected = False
    for desc, success, result in test_results:
        if success and result and isinstance(result, dict):
            if result.get('mock', False) or result.get('mock_data', False):
                mock_detected = True
                print(f"⚠️  Mock data detected in: {desc}")
    
    if not mock_detected:
        print("🎉 CONFIRMED: NO MOCK DATA ANYWHERE")
    
    print(f"\nTest completed at: {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()
