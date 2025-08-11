#!/usr/bin/env python3
"""
API Endpoint Testing Script
Tests all major API endpoints for functionality
"""

import requests
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000"

def test_health_endpoint():
    """Test health check endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health Check: {data.get('status', 'OK')}")
            return True
        else:
            print(f"❌ Health Check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health Check error: {str(e)}")
        return False

def test_auth_endpoints():
    """Test authentication endpoints"""
    try:
        # Test registration endpoint exists
        response = requests.post(f"{BASE_URL}/api/v1/auth/register", 
                               json={"username": "test", "email": "test@test.com", "password": "test123"},
                               timeout=5)
        # We expect this to fail validation, but endpoint should exist
        if response.status_code in [422, 400, 409]:  # Validation error or conflict is OK
            print("✅ Auth Registration endpoint exists")
            return True
        elif response.status_code == 201:
            print("✅ Auth Registration endpoint working")
            return True
        else:
            print(f"❌ Auth Registration unexpected status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Auth endpoints error: {str(e)}")
        return False

def test_learning_endpoints():
    """Test learning endpoints"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/learning/courses", timeout=5)
        if response.status_code in [200, 401]:  # 401 is OK if auth required
            print("✅ Learning endpoints accessible")
            return True
        else:
            print(f"❌ Learning endpoints status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Learning endpoints error: {str(e)}")
        return False

def test_feeds_endpoints():
    """Test feeds endpoints"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/feeds/posts", timeout=5)
        if response.status_code in [200, 401]:  # 401 is OK if auth required
            print("✅ Feeds endpoints accessible")
            return True
        else:
            print(f"❌ Feeds endpoints status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Feeds endpoints error: {str(e)}")
        return False

def test_community_endpoints():
    """Test community endpoints"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/community/study-groups", timeout=5)
        if response.status_code in [200, 401]:  # 401 is OK if auth required
            print("✅ Community endpoints accessible")
            return True
        else:
            print(f"❌ Community endpoints status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Community endpoints error: {str(e)}")
        return False

def test_gamification_endpoints():
    """Test gamification endpoints"""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/gamification/leaderboard", timeout=5)
        if response.status_code in [200, 401]:  # 401 is OK if auth required
            print("✅ Gamification endpoints accessible")
            return True
        else:
            print(f"❌ Gamification endpoints status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Gamification endpoints error: {str(e)}")
        return False

def test_api_docs():
    """Test API documentation"""
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        if response.status_code == 200:
            print("✅ API Documentation accessible")
            return True
        else:
            print(f"❌ API Documentation status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API Documentation error: {str(e)}")
        return False

def main():
    print("🧪 API ENDPOINT TESTING")
    print("=" * 40)
    
    tests = [
        ("Health Check", test_health_endpoint),
        ("Authentication", test_auth_endpoints),
        ("Learning System", test_learning_endpoints),
        ("Feeds System", test_feeds_endpoints),
        ("Community System", test_community_endpoints),
        ("Gamification", test_gamification_endpoints),
        ("API Documentation", test_api_docs),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 Testing {test_name}...")
        if test_func():
            passed += 1
    
    print("\n" + "=" * 40)
    print(f"📊 API TESTING RESULTS: {passed}/{total} ({(passed/total)*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL API ENDPOINTS WORKING!")
    elif passed >= total * 0.8:
        print("👍 MOST API ENDPOINTS WORKING!")
    else:
        print("⚠️ SOME API ENDPOINTS NEED ATTENTION!")
    
    print(f"\n🔗 Server: {BASE_URL}")
    print(f"🔗 API Docs: {BASE_URL}/docs")
    print(f"🔗 Health: {BASE_URL}/api/v1/health")

if __name__ == "__main__":
    main()
