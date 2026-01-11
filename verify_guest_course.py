
import requests
import json
import sys
import time

# URL and Key from user logs
BASE_URL = "https://lyo-backend-production-5oq7jszolq-uc.a.run.app"
API_KEY = "lyo_sk_live_S5ALtW3WDjhF-TAgn767ORCCga4Nx52xBlAkMHg2-TQ"

def test_guest_course_generation():
    endpoint = f"{BASE_URL}/api/v1/classroom/chat"
    print(f"Testing Endpoint: {endpoint}")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
        "X-Platform": "iOS",
        "X-App-Version": "1.0",
        "Accept": "application/json"
    }
    
    payload = {
        "message": "Create a complete interactive course on 'Algebra' suitable for beginner learners.",
        "stream": False,
        "include_audio": False
    }
    
    try:
        print("Sending POST request...")
        start_time = time.time()
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        elapsed = time.time() - start_time
        
        print(f"Status Code: {response.status_code}")
        print(f"Time: {elapsed:.2f}s")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ SUCCESS! Guest access working.")
            print("Response Preview:")
            print(json.dumps(data, indent=2)[:500] + "...")
            
            # Check for generated course ID
            if data.get('generated_course_id'):
                 print(f"Contains Course ID: {data['generated_course_id']}")
            else:
                 print("⚠️ Warning: No generated_course_id found in response (might be normal chat reply?)")
            
            return True
        elif response.status_code == 401:
            print("❌ FAILED: 401 Unauthorized.")
            print("The backend still requires a Bearer token. Deployment might not be updated yet.")
            print(response.text)
            return False
        else:
            print(f"❌ FAILED: Unexpected status {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_guest_course_generation()
    sys.exit(0 if success else 1)
