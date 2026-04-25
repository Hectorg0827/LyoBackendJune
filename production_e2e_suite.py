import requests
import json
import time

BASE_URL = "https://lyo-backend-830162750094.us-central1.run.app"
API_KEY = "lyo_sk_live_S5ALtW3WDjhF-TAgn767ORCCga4Nx52xBlAkMHg2-TQ"

def run_test(name, endpoint, payload, expected_type=None):
    print(f"\n--- Testing {name} ---")
    url = f"{BASE_URL}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
        "X-Platform": "iOS"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Failed: {response.text}")
            return False
            
        json_data = response.json()
        print(f"✅ Success! Received response.")
        
        # Validation for Classroom/Course Gen
        if expected_type:
            resp_type = json_data.get("response_type")
            print(f"Response Type: {resp_type}")
            if resp_type != expected_type:
                print(f"❌ Type mismatch: Expected {expected_type}, got {resp_type}")
                return False
        
        # Validation for Chat (Simple/Quiz)
        if "response" in json_data:
            print(f"Text Snippet: {json_data['response'][:100]}...")
            
        if "lyoBlocks" in json_data:
            print(f"Blocks received: {len(json_data['lyoBlocks'])}")
            
        if "uiComponent" in json_data and json_data["uiComponent"]:
            print(f"UI Component: {json_data['uiComponent'].get('type')}")

        return True
    except Exception as e:
        print(f"💥 Error: {e}")
        return False

def main():
    results = {}
    
    # 1. Simple Query
    results["Simple Query"] = run_test(
        "Simple Query", 
        "/api/v1/chat", 
        {"message": "What is the capital of Japan?", "sessionId": "e2e-test-1"}
    )
    
    # 2. Quiz and Flashcards
    results["Quiz/Flashcards"] = run_test(
        "Quiz Request", 
        "/api/v1/chat", 
        {
            "message": "Give me a quiz on World War II", 
            "modeHint": "quiz",
            "sessionId": "e2e-test-2"
        }
    )
    
    # 3. AI Classroom
    results["AI Classroom"] = run_test(
        "AI Classroom Invitation", 
        "/api/v1/classroom/chat", 
        {
            "message": "I want to learn about photosynthesis", 
            "stream": False
        },
        expected_type="OPEN_CLASSROOM"
    )
    
    # 4. Full Course Generator
    results["Full Course Generator"] = run_test(
        "Full Course Generation", 
        "/api/v1/classroom/chat", 
        {
            "message": "Generate a full 5-module course on Web Development with React and Node.js", 
            "stream": False
        },
        expected_type="OPEN_CLASSROOM"
    )
    
    print("\n" + "="*40)
    print("📊 FINAL E2E RESULTS")
    print("="*40)
    for test, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test.ljust(25)}: {status}")

if __name__ == "__main__":
    main()
