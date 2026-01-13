
import sys
import requests
import json
import time

BASE_URL = "https://lyo-backend-830162750094.us-central1.run.app"

def verify_a2a_prod():
    print(f"🚀 Starting A2A Production Verification against {BASE_URL}...")
    
    # 1. Verify Agent Card Discovery
    print("\n🔍 Checking Agent Card Discovery...")
    try:
        url = f"{BASE_URL}/.well-known/agent.json" # Try root first per discovery router
        response = requests.get(url, timeout=90)
        
        if response.status_code == 404:
             print(f"   Not found at {url}, trying /a2a prefix...")
             url = f"{BASE_URL}/a2a/.well-known/agent.json"
             response = requests.get(url, timeout=90)
        
        if response.status_code == 200:
            data = response.json()
            print(f"DEBUG RESPONSE: {data}")
            print(f"✅ Agent Card Found: {data.get('name')}")
            print(f"   Capabilities: {list(data.get('capabilities', {}).keys())}")
            skills = [s['id'] for s in data.get('skills', [])]
            print(f"   Skills: {skills}")
            
            if "course_generation" in skills:
                print("✅ Course Generation skill confirmed.")
            else:
                print("❌ 'course_generation' skill missing!")
                sys.exit(1)
        else:
            print(f"❌ Failed to get Agent Card. Status: {response.status_code}")
            print(response.text)
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Exception during Agent Card check: {e}")
        sys.exit(1)

    # 2. Verify Task Submission (Mock)
    print("\n📨 Verifying Task Submission...")
    task_payload = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "Create a course on Swift"}]
        }
    }
    
    try:
        url = f"{BASE_URL}/a2a/tasks/send"
        response = requests.post(url, json=task_payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Task Submitted. ID: {data.get('id')}")
            print(f"   State: {data.get('state')}")
        else:
            print(f"❌ Failed to submit task. Status: {response.status_code}")
            print(response.text)
            # Not exiting here as auth might be an issue on prod, but checking if endpoint exists is key
    except Exception as e:
        print(f"❌ Exception during Task Submission check: {e}")

if __name__ == "__main__":
    verify_a2a_prod()
