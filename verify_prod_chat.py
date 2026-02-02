import requests
import json
import time

BASE_URL = "https://lyo-backend-5oq7jszolq-uc.a.run.app"
CHAT_ENDPOINT = f"{BASE_URL}/api/v1/chat"
HEALTH_ENDPOINT = f"{BASE_URL}/health"

def check_health():
    print(f"🏥 Checking health at {HEALTH_ENDPOINT}...")
    try:
        response = requests.get(HEALTH_ENDPOINT)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_chat():
    print(f"💬 Testing chat at {CHAT_ENDPOINT}...")
    headers = {
        "Content-Type": "application/json",
        # Add authorization header if needed, for now assuming public or key based
        # "Authorization": "Bearer <YOUR_TOKEN>" 
    }
    payload = {
        "message": "Hello, are you working?",
        "modeHint": "chat",
        "sessionId": "test-session-123"
    }
    
    try:
        response = requests.post(CHAT_ENDPOINT, json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response Headers: {response.headers}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200:
            print("✅ Chat test passed!")
            return True
        else:
            print("❌ Chat test failed!")
            return False
    except Exception as e:
        print(f"❌ Chat request failed: {e}")
        return False

if __name__ == "__main__":
    if check_health():
        test_chat()
    else:
        print("⚠️ Health check failed, skipping chat test.")
