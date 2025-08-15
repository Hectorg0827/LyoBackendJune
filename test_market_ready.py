#!/usr/bin/env python3
"""
Market-Ready Backend API Test
============================

Tests all major endpoints to verify functionality.
"""

import requests
import json
import time
from datetime import datetime

def test_endpoint(url, method="GET", data=None, description=""):
    """Test an API endpoint."""
    try:
        if method == "GET":
            response = requests.get(url, timeout=5)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=5)
        
        status = "✅ PASS" if response.status_code == 200 else f"❌ FAIL ({response.status_code})"
        print(f"{status} {description}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and "status" in data:
                    print(f"      Status: {data.get('status')}")
                elif isinstance(data, dict) and "name" in data:
                    print(f"      Service: {data.get('name')}")
                elif isinstance(data, list) and len(data) > 0:
                    print(f"      Items: {len(data)}")
            except:
                print(f"      Response length: {len(response.text)} chars")
        else:
            print(f"      Error: {response.text[:100]}")
            
        return response.status_code == 200
        
    except requests.exceptions.RequestException as e:
        print(f"❌ FAIL {description} - Connection Error: {e}")
        return False

def main():
    """Run comprehensive API tests."""
    print("\n" + "="*60)
    print("🧪 LyoApp Market-Ready Backend API Tests")
    print("="*60)
    print(f"🕐 Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🌐 Base URL: http://localhost:8000")
    print("="*60 + "\n")
    
    base_url = "http://localhost:8000"
    
    # Test system endpoints
    print("📊 System Health Checks:")
    test_endpoint(f"{base_url}/", description="Root Endpoint")
    test_endpoint(f"{base_url}/health", description="Health Check")
    test_endpoint(f"{base_url}/ready", description="Readiness Check")
    
    # Test authentication module
    print("\n🔐 Authentication Module:")
    test_endpoint(f"{base_url}/v1/auth/health", description="Auth Health Check")
    test_endpoint(f"{base_url}/v1/auth/login", method="POST", description="Login Endpoint")
    test_endpoint(f"{base_url}/v1/auth/register", method="POST", description="Register Endpoint")
    
    # Test media module
    print("\n📸 Media Module:")
    test_endpoint(f"{base_url}/v1/media/health", description="Media Health Check")
    test_endpoint(f"{base_url}/v1/media/presign", method="POST", description="Media Presign")
    
    # Test posts & feed module
    print("\n📝 Posts & Feed Module:")
    test_endpoint(f"{base_url}/v1/posts", method="POST", description="Create Post")
    test_endpoint(f"{base_url}/v1/feed/following", description="Following Feed")
    
    # Test AI tutor module
    print("\n🤖 AI Tutor Module:")
    test_endpoint(f"{base_url}/v1/tutor/health", description="Tutor Health Check")
    test_endpoint(f"{base_url}/v1/tutor/turn", method="POST", description="Tutor Interaction")
    
    # Test course planner module
    print("\n📚 Course Planner Module:")
    test_endpoint(f"{base_url}/v1/planner/health", description="Planner Health Check")
    test_endpoint(f"{base_url}/v1/planner/draft", method="POST", description="Create Course Plan")
    
    # Test search module
    print("\n🔍 Search Module:")
    test_endpoint(f"{base_url}/v1/search/health", description="Search Health Check")
    test_endpoint(f"{base_url}/v1/search?q=python", description="Search Query")
    
    # Test gamification module
    print("\n🎮 Gamification Module:")
    test_endpoint(f"{base_url}/v1/gamification/health", description="Gamification Health Check")
    test_endpoint(f"{base_url}/v1/gamification/leaderboard", description="Leaderboard")
    
    # Test messaging module
    print("\n💬 Messaging Module:")
    test_endpoint(f"{base_url}/v1/messaging/health", description="Messaging Health Check")
    test_endpoint(f"{base_url}/v1/messaging/conversations", description="Conversations")
    
    # Test monitoring module
    print("\n📈 Monitoring Module:")
    test_endpoint(f"{base_url}/v1/monitoring/health", description="Monitoring Health Check")
    test_endpoint(f"{base_url}/v1/monitoring/metrics", description="System Metrics")
    
    # Test admin module
    print("\n👨‍💼 Admin Module:")
    test_endpoint(f"{base_url}/v1/admin/health", description="Admin Health Check")
    test_endpoint(f"{base_url}/v1/admin/stats", description="Admin Statistics")
    
    print("\n" + "="*60)
    print("✅ Market-Ready Backend API Test Complete!")
    print("🌐 Visit http://localhost:8000/v1/docs for interactive documentation")
    print("="*60 + "\n")

if __name__ == "__main__":
    # Wait a moment for server to be ready
    print("⏳ Waiting for server to be ready...")
    time.sleep(2)
    
    main()
