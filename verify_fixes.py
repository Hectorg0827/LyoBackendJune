import requests
import json
import time

BASE_URL = "https://lyo-backend-production-830162750094.us-central1.run.app"
API_KEY = "lyo_sk_live_S5ALtW3WDjhF-TAgn767ORCCga4Nx52xBlAkMHg2-TQ"

def test_public_chat():
    print("\n--- Testing Public Chat (AI Persona & History) ---")
    url = f"{BASE_URL}/api/v1/ai/chat"
    
    # 1. First message
    print("1. Sending initial message...")
    initial_payload = {
        "message": "My name is HECTOR.",
        "context": "User is on the home screen."
    }
    requests.post(url, json=initial_payload) # Just warm up or ignore response
    
    # 2. Second message with HISTORY (snake_case)
    print("2. Sending follow-up with history (snake_case)...")
    payload = {
        "message": "What is my name?",
        "conversation_history": [
            {"role": "user", "content": "My name is HECTOR."},
            {"role": "assistant", "content": "Nice to meet you HECTOR! I'm Lyo."}
        ],
        "context": "User is in chat."
    }
    
    try:
        start = time.time()
        response = requests.post(url, json=payload, timeout=90)
        duration = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            reply = data.get("response", "")
            print(f"✅ Status 200 OK ({duration:.2f}s)")
            print(f"AI Reply: {reply}")
            
            # Verification Logic
            if "HECTOR" in reply or "Hector" in reply:
                print("✅ PASS: AI remembered name from history!")
            else:
                print("⚠️ WARN: AI did not explicitly say the name. Check reply context.")
                
            if "I will be Lyo" in reply or "Okay, I'm ready" in reply:
                print("❌ FAIL: AI returned meta-response (System prompt leak)")
                
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

def test_course_generation():
    print("\n--- Testing Course Generation ---")
    url = f"{BASE_URL}/api/v1/ai/generate-course"
    payload = {
        "topic": "SwiftUI for Beginners",
        "difficulty": "beginner",
        "num_modules": 2,
        "lessons_per_module": 2
    }
    try:
        start = time.time()
        print(f"Generating course '{payload['topic']}' (this may take 10-20s)...")
        response = requests.post(url, json=payload, timeout=120)
        duration = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status 200 OK ({duration:.2f}s)")
            print(f"Title: {data.get('title')}")
            modules = data.get("modules", [])
            print(f"Modules Generated: {len(modules)}")
            
            if len(modules) > 0 and len(modules[0].get("lessons", [])) > 0:
                 print("✅ PASS: Course structure generated successfully")
            else:
                 print("❌ FAIL: Modules or lessons missing")
        else:
            print(f"❌ Failed: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    print(f"Targeting: {BASE_URL}")
    test_public_chat()
    test_course_generation()
