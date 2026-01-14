#!/usr/bin/env python3
"""
Comprehensive Backend Test Suite
Tests all critical endpoints: Auth, Chat, Course Creation
"""
import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"
API_KEY = "lyo_sk_live_S5ALtW3WDjhF-TAgn767ORCCga4Nx52xBlAkMHg2-TQ"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, name):
        self.passed += 1
        print(f"✅ {name}")
    
    def add_fail(self, name, error):
        self.failed += 1
        self.errors.append((name, error))
        print(f"❌ {name}: {error}")
    
    def summary(self):
        print(f"\n{'='*50}")
        print(f"SUMMARY: {self.passed} passed, {self.failed} failed")
        if self.errors:
            print("\nFailed Tests:")
            for name, err in self.errors:
                print(f"  - {name}: {err}")
        return self.failed == 0

results = TestResult()
ACCESS_TOKEN = None
USER_ID = None

def headers(auth=False):
    h = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    if auth and ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    return h

# ==============================================================================
# TEST 1: Health Check
# ==============================================================================
def test_health():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "healthy":
                results.add_pass("Health Check")
                return True
        results.add_fail("Health Check", f"Status: {r.status_code}")
    except Exception as e:
        results.add_fail("Health Check", str(e))
    return False

# ==============================================================================
# TEST 2: User Registration
# ==============================================================================
def test_register():
    global ACCESS_TOKEN, USER_ID
    try:
        # Use unique email
        email = f"test_{int(time.time())}@example.com"
        r = requests.post(f"{BASE_URL}/auth/register", headers=headers(), json={
            "email": email,
            "password": "TestPass123!",
            "confirm_password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User",
            "username": f"testuser_{int(time.time())}"
        }, timeout=10)
        if r.status_code in [200, 201]:
            data = r.json()
            ACCESS_TOKEN = data.get("access_token")
            USER_ID = data.get("user", {}).get("id")
            if ACCESS_TOKEN:
                results.add_pass("User Registration")
                return True
        results.add_fail("User Registration", f"Status: {r.status_code} - {r.text[:200]}")
    except Exception as e:
        results.add_fail("User Registration", str(e))
    return False

# ==============================================================================
# TEST 3: User Login
# ==============================================================================
def test_login():
    global ACCESS_TOKEN, USER_ID
    try:
        r = requests.post(f"{BASE_URL}/auth/login", headers=headers(), json={
            "email": "test@example.com",
            "password": "TestPass123!"
        }, timeout=10)
        if r.status_code == 200:
            data = r.json()
            ACCESS_TOKEN = data.get("access_token")
            USER_ID = data.get("user", {}).get("id")
            if ACCESS_TOKEN:
                results.add_pass("User Login")
                return True
        results.add_fail("User Login", f"Status: {r.status_code} - {r.text[:200]}")
    except Exception as e:
        results.add_fail("User Login", str(e))
    return False

# ==============================================================================
# TEST 4: AI Chat Endpoint
# ==============================================================================
def test_chat():
    if not ACCESS_TOKEN:
        results.add_fail("AI Chat", "No access token")
        return False
    try:
        r = requests.post(f"{BASE_URL}/api/v1/chat", headers=headers(auth=True), json={
            "message": "What is 2+2?",
            "include_chips": 1,
            "include_ctas": 1
        }, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get("response") or data.get("success"):
                results.add_pass("AI Chat Endpoint")
                return True
        results.add_fail("AI Chat Endpoint", f"Status: {r.status_code} - {r.text[:300]}")
    except Exception as e:
        results.add_fail("AI Chat Endpoint", str(e))
    return False

# ==============================================================================
# TEST 5: Chat with Course Trigger
# ==============================================================================
def test_course_trigger():
    if not ACCESS_TOKEN:
        results.add_fail("Course Trigger", "No access token")
        return False
    try:
        r = requests.post(f"{BASE_URL}/api/v1/chat", headers=headers(auth=True), json={
            "message": "Create a course about Python programming for beginners",
            "include_chips": 1,
            "include_ctas": 1
        }, timeout=30)
        if r.status_code == 200:
            data = r.json()
            response_text = data.get("response", "").lower()
            # Check if Lyo acknowledges course creation request
            if "course" in response_text or "python" in response_text or "beginner" in response_text:
                results.add_pass("Course Trigger (Chat)")
                return True
        results.add_fail("Course Trigger (Chat)", f"Status: {r.status_code} - {r.text[:300]}")
    except Exception as e:
        results.add_fail("Course Trigger (Chat)", str(e))
    return False

# ==============================================================================
# TEST 6: Multi-Agent Course Generation API
# ==============================================================================
def test_multi_agent_course():
    if not ACCESS_TOKEN:
        results.add_fail("Multi-Agent Course", "No access token")
        return False
    try:
        r = requests.post(f"{BASE_URL}/api/v1/multi-agent-v2/courses", headers=headers(auth=True), json={
            "topic": "Introduction to Machine Learning",
            "level": "beginner",
            "interests": ["AI", "data science"]
        }, timeout=60)
        if r.status_code in [200, 201, 202]:
            results.add_pass("Multi-Agent Course API")
            return True
        results.add_fail("Multi-Agent Course API", f"Status: {r.status_code} - {r.text[:300]}")
    except Exception as e:
        results.add_fail("Multi-Agent Course API", str(e))
    return False

# ==============================================================================
# TEST 7: A2A Protocol Agents Discovery
# ==============================================================================
def test_a2a_discovery():
    try:
        r = requests.get(f"{BASE_URL}/api/v1/a2a/agents", headers=headers(), timeout=10)
        if r.status_code == 200:
            results.add_pass("A2A Agents Discovery")
            return True
        results.add_fail("A2A Agents Discovery", f"Status: {r.status_code}")
    except Exception as e:
        results.add_fail("A2A Agents Discovery", str(e))
    return False

# ==============================================================================
# TEST 8: Stack/Learning Queue
# ==============================================================================
def test_stack():
    if not ACCESS_TOKEN:
        results.add_fail("Stack Endpoint", "No access token")
        return False
    try:
        r = requests.get(f"{BASE_URL}/api/v1/stack", headers=headers(auth=True), timeout=10)
        if r.status_code in [200, 404]:  # 404 is ok if no items
            results.add_pass("Stack Endpoint")
            return True
        results.add_fail("Stack Endpoint", f"Status: {r.status_code}")
    except Exception as e:
        results.add_fail("Stack Endpoint", str(e))
    return False

# ==============================================================================
# TEST 9: Personalization Profile
# ==============================================================================
def test_personalization():
    if not ACCESS_TOKEN:
        results.add_fail("Personalization", "No access token")
        return False
    try:
        r = requests.get(f"{BASE_URL}/personalization/profile", headers=headers(auth=True), timeout=10)
        if r.status_code in [200, 404]:  # 404 is ok if no profile yet
            results.add_pass("Personalization Profile")
            return True
        results.add_fail("Personalization Profile", f"Status: {r.status_code}")
    except Exception as e:
        results.add_fail("Personalization Profile", str(e))
    return False

# ==============================================================================
# RUN ALL TESTS
# ==============================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("COMPREHENSIVE BACKEND TEST SUITE")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 50)
    print()
    
    # Run tests in order
    test_health()
    test_register()
    test_login()
    test_chat()
    test_course_trigger()
    test_multi_agent_course()
    test_a2a_discovery()
    test_stack()
    test_personalization()
    
    # Summary
    success = results.summary()
    exit(0 if success else 1)
