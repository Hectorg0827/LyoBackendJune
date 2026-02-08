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

STREAM_ENDPOINT = f"{BASE_URL}/api/v1/chat/stream"

def test_chat_stream():
    print(f"🌊 Testing chat stream at {STREAM_ENDPOINT}...")
    headers = {
        "Content-Type": "application/json",
    }
    # Matches ChatStreamRequest from iOS: message and context (string)
    payload = {
        "message": "Hello stream",
        "context": "mode: test" 
    }
    
    try:
        # Note: In real usage this is SSE, but requests.post should return 200 OK and stream content
        response = requests.post(STREAM_ENDPOINT, json=payload, headers=headers, stream=True)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Chat stream endpoint exists and returns 200!")
            # Verify we get some content
            for line in response.iter_lines():
                if line:
                    print(f"Received chunk: {line}")
                    break # Just verify we get something
            return True
        else:
            print(f"❌ Chat stream test failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Chat stream request failed: {e}")
        return False

if __name__ == "__main__":
    if check_health():
        chat_ok = test_chat()
        stream_ok = test_chat_stream()
        if chat_ok and stream_ok:
            print("🎉 All verifications passed!") 
        else:
            print("⚠️ Some verifications failed.")
    else:
        print("⚠️ Health check failed, skipping chat test.")
