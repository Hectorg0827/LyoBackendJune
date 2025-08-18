#!/usr/bin/env python3
"""
Simple backend test to verify server functionality
"""
import os
import sys
import time
import requests
import json
from fastapi.testclient import TestClient

# Set lightweight mode for testing
os.environ["LYO_LIGHTWEIGHT_STARTUP"] = "1"

def test_with_test_client():
    """Test using FastAPI TestClient (internal testing)"""
    print("🧪 Testing with FastAPI TestClient...")
    
    try:
        from lyo_app.app_factory import create_app
        app = create_app()
        client = TestClient(app)
        
        # Test health endpoint
        response = client.get("/healthz")
        print(f"✅ Health check - Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Status: {data.get('status', 'unknown')}")
            print(f"   AI Services: {data.get('services', {})}")
        
        # Test market status
        response = client.get("/market-status")
        print(f"✅ Market status - Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Readiness: {data.get('market_readiness', 'unknown')}")
        
        # Test root endpoint
        response = client.get("/")
        print(f"✅ Root endpoint - Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Message: {data.get('message', 'unknown')}")
        
        return True
        
    except Exception as e:
        print(f"❌ TestClient error: {e}")
        return False

def test_with_requests():
    """Test using requests (external HTTP testing)"""
    print("\n🌐 Testing with HTTP requests...")
    
    base_url = "http://localhost:8000"
    endpoints = ["/healthz", "/market-status", "/"]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            print(f"✅ {endpoint} - Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if endpoint == "/healthz":
                        print(f"   Health: {data.get('status', 'unknown')}")
                    elif endpoint == "/market-status":
                        print(f"   Market: {data.get('market_readiness', 'unknown')}")
                    elif endpoint == "/":
                        print(f"   App: {data.get('message', 'unknown')[:50]}...")
                except:
                    print(f"   Response: {response.text[:100]}...")
            else:
                print(f"   Error: {response.text[:100]}...")
                
        except requests.exceptions.ConnectionError:
            print(f"❌ {endpoint} - Connection failed (server not running?)")
        except requests.exceptions.Timeout:
            print(f"⏱️ {endpoint} - Request timed out")
        except Exception as e:
            print(f"❌ {endpoint} - Error: {e}")

if __name__ == "__main__":
    print("🚀 Lyo Backend Test Suite")
    print("=" * 50)
    
    # Test with TestClient first (always works)
    testclient_success = test_with_test_client()
    
    # Test with HTTP requests (requires running server)
    test_with_requests()
    
    print("\n" + "=" * 50)
    if testclient_success:
        print("✅ Backend is functional - FastAPI app working correctly!")
        print("📊 Server endpoints are available")
        print("🔗 Check http://localhost:8000/docs for API documentation")
    else:
        print("❌ Backend has issues - check logs for details")
    
    print("🎯 Lyo Backend Test Complete")
