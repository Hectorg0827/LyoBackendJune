#!/usr/bin/env python3
"""
Test the /api/v1/chat endpoint
"""
import requests
import json

BASE_URL = "https://lyo-backend-production-830162750094.us-central1.run.app"
API_KEY = "lyo_sk_live_S5ALtW3WDjhF-TAgn767ORCCga4Nx52xBlAkMHg2-TQ"

def test_chat_endpoint():
    """Test the chat endpoint"""
    url = f"{BASE_URL}/api/v1/chat"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    payload = {
        "message": "Hello! Can you help me with Python?",
        "conversation_history": [],
        "include_chips": 0,
        "include_ctas": 0
    }
    
    print("🧪 Testing /api/v1/chat endpoint...")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print("\n" + "="*60 + "\n")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"\nResponse Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Chat endpoint is working!")
            return True
        else:
            print(f"\n❌ FAILED: Got status code {response.status_code}")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return False

if __name__ == "__main__":
    success = test_chat_endpoint()
    exit(0 if success else 1)
