#!/usr/bin/env python3
"""
Test client to verify backend functionality
"""
import requests
import json
import time
import sys

def test_endpoint(url, description=""):
    """Test a specific endpoint."""
    print(f"\n🧪 Testing {description}: {url}")
    try:
        response = requests.get(url, timeout=10)
        print(f"✅ Status: {response.status_code}")
        if response.headers.get('content-type', '').startswith('application/json'):
            print(f"📄 Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"📄 Response: {response.text[:200]}...")
        return True
    except requests.exceptions.ConnectRefused:
        print("❌ Connection refused - server not running")
        return False
    except requests.exceptions.Timeout:
        print("❌ Timeout - server not responding")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_ai_endpoint(base_url):
    """Test AI functionality."""
    url = f"{base_url}/api/v1/ai/test-real"
    print(f"\n🤖 Testing AI endpoint: {url}")
    
    try:
        payload = {"prompt": "Hello, are you working? Please respond with 'Yes, I am working!'"}
        response = requests.post(url, json=payload, timeout=15)
        print(f"✅ Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"🎯 AI Response: {data.get('response', 'No response')}")
            print(f"🔧 Model: {data.get('model', 'Unknown')}")
            print(f"🚫 Mock Mode: {data.get('mock', 'Unknown')}")
            return True
        else:
            print(f"❌ Error response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    base_urls = [
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:8080",
        "http://127.0.0.1:8080"
    ]
    
    print("🚀 LyoBackend Functionality Test")
    print("=" * 50)
    
    working_server = None
    
    # Find working server
    for base_url in base_urls:
        if test_endpoint(f"{base_url}/", f"Root endpoint ({base_url})"):
            working_server = base_url
            break
        time.sleep(1)
    
    if not working_server:
        print("\n❌ No working server found!")
        sys.exit(1)
    
    print(f"\n✅ Found working server at: {working_server}")
    
    # Test all endpoints
    endpoints = [
        ("/health", "Health Check"),
        ("/docs", "API Documentation")
    ]
    
    for endpoint, description in endpoints:
        test_endpoint(f"{working_server}{endpoint}", description)
        time.sleep(0.5)
    
    # Test AI functionality
    test_ai_endpoint(working_server)
    
    print("\n🎉 Backend functionality test complete!")

if __name__ == "__main__":
    main()
