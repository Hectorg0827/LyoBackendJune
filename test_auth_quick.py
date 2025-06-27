#!/usr/bin/env python3
"""
Quick authentication test - step by step.
"""

import subprocess
import time
import requests
import json

def start_server():
    """Start the development server."""
    print("🚀 Starting server...")
    process = subprocess.Popen([
        "python", "start_server.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for server to start
    for i in range(15):
        time.sleep(1)
        try:
            response = requests.get("http://localhost:8000/health", timeout=2)
            if response.status_code == 200:
                print("✅ Server is running")
                return process
        except:
            print(f"⏳ Waiting for server... ({i+1}/15)")
            continue
    
    print("❌ Server failed to start")
    return None

def test_registration():
    """Test user registration."""
    print("\n👤 Testing registration...")
    
    user_data = {
        "username": "testuser123",
        "email": "test@example.com", 
        "password": "TestPass123!",
        "full_name": "Test User"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/auth/register",
            json=user_data,
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 201:
            print("✅ Registration successful")
            return response.json()
        else:
            print("❌ Registration failed")
            return None
            
    except Exception as e:
        print(f"❌ Registration error: {e}")
        return None

def test_login():
    """Test user login."""
    print("\n🔐 Testing login...")
    
    login_data = {
        "username": "testuser123",
        "password": "TestPass123!"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/api/v1/auth/login",
            json=login_data,
            timeout=10
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Login successful")
            return response.json()
        else:
            print("❌ Login failed")
            return None
            
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def main():
    """Run quick auth test."""
    print("🔒 Quick Authentication Test")
    print("=" * 40)
    
    # Start server
    process = start_server()
    if not process:
        return
    
    try:
        # Test registration
        user = test_registration()
        
        # Test login
        token_data = test_login()
        
        print("\n📊 Summary:")
        if user and token_data:
            print("✅ Authentication system working!")
        else:
            print("❌ Authentication issues found")
            
    finally:
        # Stop server
        print("\n🛑 Stopping server...")
        process.terminate()
        process.wait()

if __name__ == "__main__":
    main()
