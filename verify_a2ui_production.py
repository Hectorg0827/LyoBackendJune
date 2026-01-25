#!/usr/bin/env python3
import requests
import json
import sys
import time

BASE_URL = "https://lyo-backend-production-5oq7jszolq-uc.a.run.app"

def log(status, message):
    icon = "✅" if status else "❌"
    print(f"{icon} {message}")

def check_endpoint(name, url, expected_status=200):
    print(f"\nTesting {name} ({url})...")
    try:
        start = time.time()
        response = requests.get(url, timeout=10)
        duration = (time.time() - start) * 1000
        
        if response.status_code == expected_status:
            log(True, f"Status {response.status_code} ({duration:.0f}ms)")
            try:
                data = response.json()
                return True, data
            except:
                log(False, "Failed to parse JSON")
                return False, None
        else:
            log(False, f"Status {response.status_code} (Expected {expected_status})")
            print(f"Response: {response.text[:200]}")
            return False, None
    except Exception as e:
        log(False, f"Connection failed: {str(e)}")
        return False, None

def verify_a2ui():
    print("🚀 Verifying A2UI Implementation on Production")
    print(f"Target: {BASE_URL}")
    print("=" * 50)

    # 1. General Health
    success, data = check_endpoint("Backend Health", f"{BASE_URL}/health")
    if not success:
        print("CRITICAL: Backend is down")
        sys.exit(1)
    
    # 2. A2UI Service Health
    success, data = check_endpoint("A2UI Service Health", f"{BASE_URL}/api/v1/a2ui/health")
    if success:
        if data.get("status") == "healthy" and data.get("generator") == "ready":
             log(True, "A2UI Service is healthy and generator is ready")
        else:
             log(False, f"A2UI Service reported unhealthy: {data}")
    
    # 3. A2UI Component Generation
    success, data = check_endpoint("A2UI Generation Test", f"{BASE_URL}/api/v1/a2ui/components/test")
    if success:
        components = data.get("components", {})
        count = len(components)
        if count > 0:
            log(True, f"Successfully generated {count} test components")
            
            # Validate one component structure
            if "quiz" in components:
                quiz = components["quiz"]
                if quiz.get("type") == "quiz" and "props" in quiz:
                    log(True, "Quiz component structure valid (type='quiz', has props)")
                else:
                    log(False, "Quiz component structure invalid")
                    print(json.dumps(quiz, indent=2))
            
            if "course" in components:
                 course = components["course"]
                 if course.get("type") == "coursecard":
                     log(True, "Course Card component structure valid")
        else:
             log(False, "No components returned in test response")

    print("\n" + "=" * 50)
    print("✨ Verification Complete")

if __name__ == "__main__":
    verify_a2ui()
