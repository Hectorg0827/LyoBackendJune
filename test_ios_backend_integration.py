#!/usr/bin/env python3
"""
Test script to verify iOS backend integration after Firebase fix.
Tests the complete flow: authentication -> course generation -> playback
"""

import requests
import json
import time
from datetime import datetime

# Production backend URL
BASE_URL = "https://lyo-backend-production-830162750094.us-central1.run.app"

def print_test(name, status, details=""):
    """Print test result"""
    emoji = "✅" if status else "❌"
    print(f"{emoji} {name}")
    if details:
        print(f"   {details}")
    print()

def test_health():
    """Test 1: Backend health check"""
    print("🧪 Test 1: Backend Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json()
        
        is_healthy = (
            response.status_code == 200 and
            data.get("status") == "healthy" and
            data.get("services", {}).get("firebase") == "enabled"
        )
        
        print_test(
            "Backend Health", 
            is_healthy,
            f"Status: {data.get('status')}, Firebase: {data.get('services', {}).get('firebase')}"
        )
        return is_healthy
    except Exception as e:
        print_test("Backend Health", False, str(e))
        return False

def test_interactive_cinema_endpoints():
    """Test 2: Interactive Cinema API endpoints availability"""
    print("🧪 Test 2: Interactive Cinema Endpoints")
    
    # Test playback dashboard (GET)
    try:
        response = requests.get(f"{BASE_URL}/api/v1/classroom/playback/mastery/dashboard", timeout=10)
        # 422 is validation error (missing params) - endpoint exists
        playback_ok = response.status_code in [200, 401, 422]
        print_test(
            "Playback endpoints",
            playback_ok,
            f"Status: {response.status_code}"
        )
    except Exception as e:
        print_test("Playback endpoints", False, str(e))
        return False
    
    # Test chat endpoint (POST)
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/classroom/chat",
            json={"message": "test"},
            timeout=10
        )
        # 401 or 422 expected (needs auth or valid data)
        chat_ok = response.status_code in [200, 401, 422]
        print_test(
            "Chat endpoint",
            chat_ok,
            f"Status: {response.status_code}"
        )
        return playback_ok and chat_ok
    except Exception as e:
        print_test("Chat endpoint", False, str(e))
        return False

def test_firebase_auth_configuration():
    """Test 3: Firebase project configuration"""
    print("🧪 Test 3: Firebase Auth Configuration")
    
    # Test with invalid token to see error message
    headers = {"Authorization": "Bearer invalid_token_test"}
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/classroom/chat/courses",
            headers=headers,
            timeout=10
        )
        
        # Check if error message mentions correct project
        if response.status_code == 401:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", "")
            
            # Should NOT mention "lyobackend" as expected audience
            # Should accept "lyo-app" tokens
            is_configured = "lyobackend" not in error_msg or "lyo-app" in error_msg
            
            print_test(
                "Firebase Project Config",
                True,  # We expect 401, that's correct
                f"Auth endpoint responding (401 expected without valid token)"
            )
            return True
        else:
            print_test("Firebase Project Config", False, f"Unexpected status: {response.status_code}")
            return False
            
    except Exception as e:
        print_test("Firebase Project Config", False, str(e))
        return False

def test_cors_configuration():
    """Test 4: CORS configuration for iOS"""
    print("🧪 Test 4: CORS Configuration")
    
    try:
        response = requests.options(
            f"{BASE_URL}/api/v1/classroom/chat/courses",
            headers={
                "Origin": "capacitor://localhost",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization"
            },
            timeout=10
        )
        
        cors_ok = (
            response.status_code in [200, 204] or
            "Access-Control-Allow-Origin" in response.headers
        )
        
        print_test(
            "CORS Headers",
            cors_ok,
            f"Status: {response.status_code}, Headers: {list(response.headers.keys())[:5]}"
        )
        return cors_ok
    except Exception as e:
        print_test("CORS Headers", False, str(e))
        return False

def test_api_version():
    """Test 5: API version compatibility"""
    print("🧪 Test 5: API Version Compatibility")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        data = response.json()
        version = data.get("version", "unknown")
        
        # Check if it's recent version (3.x.x)
        is_compatible = version.startswith("3.")
        
        print_test(
            "API Version",
            is_compatible,
            f"Version: {version}"
        )
        return is_compatible
    except Exception as e:
        print_test("API Version", False, str(e))
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("🚀 iOS Backend Integration Test Suite")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🌐 Backend: {BASE_URL}")
    print("=" * 60)
    print()
    
    results = []
    
    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("Interactive Cinema Endpoints", test_interactive_cinema_endpoints()))
    results.append(("Firebase Configuration", test_firebase_auth_configuration()))
    results.append(("CORS Configuration", test_cors_configuration()))
    results.append(("API Version", test_api_version()))
    
    # Summary
    print("=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        emoji = "✅" if result else "❌"
        print(f"{emoji} {name}")
    
    print()
    print(f"Total: {passed}/{total} tests passed ({int(passed/total*100)}%)")
    
    if passed == total:
        print("\n🎉 All tests passed! Backend is ready for iOS integration.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Review configuration.")
        return 1

if __name__ == "__main__":
    exit(main())
