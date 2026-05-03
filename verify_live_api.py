import requests
import json
import time

BASE_URL = "https://lyo-production.up.railway.app"

def test_chat():
    print(f"\n--- Testing AI Chat: {BASE_URL}/api/v1/ai/chat ---")
    payload = {
        "message": "Hello, who are you and what can you help me with?",
        "context": "User is a tech enthusiast interested in AI."
    }
    
    try:
        start_time = time.time()
        r = requests.post(f"{BASE_URL}/api/v1/ai/chat", json=payload, timeout=30)
        elapsed = time.time() - start_time
        
        print(f"Status: {r.status_code} ({elapsed:.2f}s)")
        if r.status_code == 200:
            data = r.json()
            print(f"Response: {data.get('response', 'NO RESPONSE')[:200]}...")
            print(f"UI Components: {len(data.get('uiComponent', data.get('ui_component', [])))}")
            return True
        else:
            print(f"Error Body: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"Request FAILED: {e}")
        return False

def test_course_gen():
    print(f"\n--- Testing Course Generation: {BASE_URL}/api/v1/ai/generate-course ---")
    payload = {
        "topic": "Fundamentals of Space Exploration",
        "difficulty": "beginner",
        "num_modules": 2,
        "lessons_per_module": 2
    }
    
    try:
        start_time = time.time()
        r = requests.post(f"{BASE_URL}/api/v1/ai/generate-course", json=payload, timeout=60)
        elapsed = time.time() - start_time
        
        print(f"Status: {r.status_code} ({elapsed:.2f}s)")
        if r.status_code == 200:
            data = r.json()
            print(f"Course Title: {data.get('title')}")
            print(f"Modules: {len(data.get('modules', []))}")
            print(f"First Lesson: {data.get('modules', [{}])[0].get('lessons', [{}])[0].get('title')}")
            return True
        else:
            print(f"Error Body: {r.text[:500]}")
            return False
    except Exception as e:
        print(f"Request FAILED: {e}")
        return False

if __name__ == "__main__":
    chat_ok = test_chat()
    course_ok = test_course_gen()
    
    if chat_ok and course_ok:
        print("\n✅ Verification SUCCESS: Both AI Chat and Course Generation are working on production!")
    else:
        print("\n❌ Verification FAILED: Some endpoints are not responding correctly.")
