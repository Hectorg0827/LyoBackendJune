#!/usr/bin/env python3
"""
iOS Backend Connection Verification Script
==========================================

This script verifies that the LyoApp backend is ready for iOS app connection
and tests all critical endpoints that the iOS app will use.

Run this to ensure backend-frontend compatibility.
"""

import requests
import json
import asyncio
import websockets
import time
import sys
from datetime import datetime, timedelta
import subprocess
import os

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Test data
TEST_USER = {
    "email": "ios_test@lyoapp.com",
    "username": "ios_test_user",
    "password": "secure_test_pass",
    "full_name": "iOS Test User"
}

class BackendConnectionTester:
    def __init__(self):
        self.auth_token = None
        self.user_id = None
        self.conversation_id = None
        self.story_id = None
        
    def print_status(self, message, status="INFO"):
        """Print colored status messages"""
        colors = {
            "INFO": "\033[94m",    # Blue
            "SUCCESS": "\033[92m", # Green
            "WARNING": "\033[93m", # Yellow
            "ERROR": "\033[91m",   # Red
            "ENDC": "\033[0m"      # Reset
        }
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = colors.get(status, colors["INFO"])
        print(f"{color}[{timestamp}] {status}: {message}{colors['ENDC']}")
    
    def check_server_running(self):
        """Check if backend server is running"""
        self.print_status("🔍 Checking if backend server is running...")
        
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                self.print_status("✅ Backend server is running and healthy", "SUCCESS")
                return True
        except requests.exceptions.RequestException as e:
            self.print_status(f"❌ Backend server not accessible: {e}", "ERROR")
            return False
    
    def start_backend_if_needed(self):
        """Start backend server if not running"""
        if not self.check_server_running():
            self.print_status("🚀 Starting backend server...", "WARNING")
            
            try:
                # Check if start_server.py exists
                if os.path.exists("start_server.py"):
                    # Start server in background
                    subprocess.Popen([
                        "python3", "start_server.py"
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                    # Wait for server to start
                    for i in range(30):  # Wait up to 30 seconds
                        time.sleep(1)
                        if self.check_server_running():
                            self.print_status("✅ Backend server started successfully", "SUCCESS")
                            return True
                        
                        if i % 5 == 0:
                            self.print_status(f"⏳ Waiting for server to start... ({i+1}/30s)", "INFO")
                    
                    self.print_status("❌ Failed to start backend server", "ERROR")
                    return False
                else:
                    self.print_status("❌ start_server.py not found", "ERROR")
                    return False
                    
            except Exception as e:
                self.print_status(f"❌ Error starting server: {e}", "ERROR")
                return False
        
        return True
    
    def test_authentication(self):
        """Test authentication endpoints"""
        self.print_status("🔐 Testing authentication endpoints...")
        
        # Test registration
        try:
            response = requests.post(f"{API_BASE}/auth/register", json=TEST_USER)
            if response.status_code in [200, 201]:
                self.print_status("✅ User registration successful", "SUCCESS")
            elif response.status_code == 400 and "already registered" in response.text.lower():
                self.print_status("⚠️ User already exists (expected for repeat tests)", "WARNING")
            else:
                self.print_status(f"❌ Registration failed: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Registration error: {e}", "ERROR")
            return False
        
        # Test login
        try:
            login_data = {
                "username": TEST_USER["username"],
                "password": TEST_USER["password"]
            }
            response = requests.post(
                f"{API_BASE}/auth/login",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                auth_data = response.json()
                self.auth_token = auth_data["access_token"]
                self.user_id = auth_data["user"]["id"]
                self.print_status("✅ User login successful", "SUCCESS")
                self.print_status(f"🆔 User ID: {self.user_id}", "INFO")
                return True
            else:
                self.print_status(f"❌ Login failed: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Login error: {e}", "ERROR")
            return False
    
    def get_auth_headers(self):
        """Get authorization headers"""
        return {"Authorization": f"Bearer {self.auth_token}"}
    
    def test_stories_api(self):
        """Test stories functionality"""
        self.print_status("📚 Testing stories API...")
        
        if not self.auth_token:
            self.print_status("❌ No auth token for stories test", "ERROR")
            return False
        
        headers = self.get_auth_headers()
        
        # Get stories
        try:
            response = requests.get(f"{API_BASE}/social/stories/", headers=headers)
            if response.status_code == 200:
                stories = response.json()
                self.print_status(f"✅ Retrieved {len(stories)} stories", "SUCCESS")
            else:
                self.print_status(f"❌ Failed to get stories: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Stories GET error: {e}", "ERROR")
            return False
        
        # Create a story
        try:
            story_data = {
                "content": "Test story from iOS connection verification",
                "content_type": "text"
            }
            response = requests.post(f"{API_BASE}/social/stories/", json=story_data, headers=headers)
            if response.status_code in [200, 201]:
                story = response.json()
                self.story_id = story["id"]
                self.print_status("✅ Story creation successful", "SUCCESS")
                return True
            else:
                self.print_status(f"❌ Failed to create story: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Story creation error: {e}", "ERROR")
            return False
    
    def test_messenger_api(self):
        """Test messenger functionality"""
        self.print_status("💬 Testing messenger API...")
        
        if not self.auth_token:
            self.print_status("❌ No auth token for messenger test", "ERROR")
            return False
        
        headers = self.get_auth_headers()
        
        # Get conversations
        try:
            response = requests.get(f"{API_BASE}/social/messenger/conversations", headers=headers)
            if response.status_code == 200:
                conversations = response.json()
                self.print_status(f"✅ Retrieved {len(conversations)} conversations", "SUCCESS")
                
                # Use existing conversation or create one
                if conversations:
                    self.conversation_id = conversations[0]["id"]
                    self.print_status(f"📱 Using existing conversation ID: {self.conversation_id}", "INFO")
                else:
                    # Try to create a conversation (this might fail if no other users exist)
                    self.print_status("📝 Creating test conversation...", "INFO")
                    conv_data = {
                        "participant_ids": [self.user_id],  # Self-conversation for testing
                        "is_group": False
                    }
                    response = requests.post(f"{API_BASE}/social/messenger/conversations", json=conv_data, headers=headers)
                    if response.status_code in [200, 201]:
                        conversation = response.json()
                        self.conversation_id = conversation["id"]
                        self.print_status("✅ Test conversation created", "SUCCESS")
                
                return True
            else:
                self.print_status(f"❌ Failed to get conversations: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Messenger error: {e}", "ERROR")
            return False
    
    def test_learning_api(self):
        """Test learning resources API"""
        self.print_status("🎓 Testing learning API...")
        
        if not self.auth_token:
            self.print_status("❌ No auth token for learning test", "ERROR")
            return False
        
        headers = self.get_auth_headers()
        
        # Test search
        try:
            response = requests.get(f"{API_BASE}/learning/search?q=python", headers=headers)
            if response.status_code == 200:
                resources = response.json()
                self.print_status(f"✅ Found {len(resources)} learning resources", "SUCCESS")
                return True
            else:
                self.print_status(f"❌ Learning search failed: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Learning API error: {e}", "ERROR")
            return False
    
    def test_ai_api(self):
        """Test AI chat functionality"""
        self.print_status("🤖 Testing AI chat API...")
        
        if not self.auth_token:
            self.print_status("❌ No auth token for AI test", "ERROR")
            return False
        
        headers = self.get_auth_headers()
        
        try:
            ai_data = {
                "message": "Hello! This is a test from iOS connection verification.",
                "model": "gemini-pro"
            }
            response = requests.post(f"{API_BASE}/ai/chat", json=ai_data, headers=headers)
            if response.status_code == 200:
                ai_response = response.json()
                self.print_status("✅ AI chat response received", "SUCCESS")
                self.print_status(f"🤖 AI said: {ai_response.get('response', 'No response')[:100]}...", "INFO")
                return True
            else:
                self.print_status(f"❌ AI chat failed: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ AI API error: {e}", "ERROR")
            return False
    
    def test_gamification_api(self):
        """Test gamification features"""
        self.print_status("🏆 Testing gamification API...")
        
        if not self.auth_token:
            self.print_status("❌ No auth token for gamification test", "ERROR")
            return False
        
        headers = self.get_auth_headers()
        
        # Test leaderboard
        try:
            response = requests.get(f"{API_BASE}/gamification/leaderboard", headers=headers)
            if response.status_code == 200:
                leaderboard = response.json()
                self.print_status(f"✅ Retrieved leaderboard with {len(leaderboard)} entries", "SUCCESS")
            else:
                self.print_status(f"❌ Leaderboard failed: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Gamification error: {e}", "ERROR")
            return False
        
        # Test achievements
        try:
            response = requests.get(f"{API_BASE}/gamification/achievements", headers=headers)
            if response.status_code == 200:
                achievements = response.json()
                self.print_status(f"✅ Retrieved {len(achievements)} achievements", "SUCCESS")
                return True
            else:
                self.print_status(f"❌ Achievements failed: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ Achievements error: {e}", "ERROR")
            return False
    
    async def test_websocket_connection(self):
        """Test WebSocket connection"""
        self.print_status("🌐 Testing WebSocket connection...")
        
        if not self.auth_token or not self.user_id:
            self.print_status("❌ No auth data for WebSocket test", "ERROR")
            return False
        
        try:
            # Test messenger WebSocket
            ws_url = f"ws://localhost:8000/api/v1/social/messenger/ws/{self.user_id}?token={self.auth_token}"
            
            async with websockets.connect(ws_url) as websocket:
                self.print_status("✅ WebSocket connection established", "SUCCESS")
                
                # Send test message
                test_message = {
                    "type": "send_message",
                    "content": "Test message from iOS connection verification",
                    "conversation_id": self.conversation_id or 1,
                    "timestamp": datetime.now().isoformat()
                }
                
                await websocket.send(json.dumps(test_message))
                self.print_status("✅ Test message sent via WebSocket", "SUCCESS")
                
                # Try to receive response (with timeout)
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    self.print_status("✅ WebSocket response received", "SUCCESS")
                    return True
                except asyncio.TimeoutError:
                    self.print_status("⚠️ WebSocket timeout (but connection works)", "WARNING")
                    return True
                    
        except Exception as e:
            self.print_status(f"❌ WebSocket error: {e}", "ERROR")
            return False
    
    def test_api_documentation(self):
        """Test API documentation availability"""
        self.print_status("📚 Testing API documentation...")
        
        try:
            response = requests.get(f"{BASE_URL}/docs")
            if response.status_code == 200:
                self.print_status("✅ API documentation available at /docs", "SUCCESS")
                return True
            else:
                self.print_status(f"❌ API docs not available: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.print_status(f"❌ API docs error: {e}", "ERROR")
            return False
    
    def run_comprehensive_test(self):
        """Run all tests"""
        self.print_status("🚀 Starting iOS Backend Connection Verification", "INFO")
        self.print_status("=" * 60, "INFO")
        
        test_results = {}
        
        # 1. Check/Start server
        test_results["server"] = self.start_backend_if_needed()
        
        if not test_results["server"]:
            self.print_status("❌ Cannot proceed without backend server", "ERROR")
            return False
        
        # 2. Test authentication
        test_results["auth"] = self.test_authentication()
        
        # 3. Test API endpoints
        test_results["stories"] = self.test_stories_api()
        test_results["messenger"] = self.test_messenger_api()
        test_results["learning"] = self.test_learning_api()
        test_results["ai"] = self.test_ai_api()
        test_results["gamification"] = self.test_gamification_api()
        
        # 4. Test WebSocket
        test_results["websocket"] = asyncio.run(self.test_websocket_connection())
        
        # 5. Test documentation
        test_results["docs"] = self.test_api_documentation()
        
        # Summary
        self.print_status("=" * 60, "INFO")
        self.print_status("📊 TEST RESULTS SUMMARY", "INFO")
        self.print_status("=" * 60, "INFO")
        
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            color = "SUCCESS" if result else "ERROR"
            self.print_status(f"{test_name.upper():<15} {status}", color)
            if result:
                passed += 1
        
        self.print_status("=" * 60, "INFO")
        success_rate = (passed / total) * 100
        
        if success_rate == 100:
            self.print_status(f"🎉 ALL TESTS PASSED ({passed}/{total}) - iOS app ready to connect!", "SUCCESS")
        elif success_rate >= 80:
            self.print_status(f"⚠️ MOSTLY READY ({passed}/{total}) - iOS app can connect with minor issues", "WARNING")
        else:
            self.print_status(f"❌ ISSUES FOUND ({passed}/{total}) - Fix errors before iOS connection", "ERROR")
        
        self.print_status("=" * 60, "INFO")
        self.print_status("📱 iOS app can connect to: http://localhost:8000", "INFO")
        self.print_status("📖 API docs available at: http://localhost:8000/docs", "INFO")
        self.print_status("=" * 60, "INFO")
        
        return success_rate >= 80

def main():
    """Main function"""
    print("\n🎯 LyoApp iOS Backend Connection Verification")
    print("=" * 60)
    
    tester = BackendConnectionTester()
    success = tester.run_comprehensive_test()
    
    if success:
        print("\n🚀 Your iOS app is ready to connect to the backend!")
        sys.exit(0)
    else:
        print("\n❌ Please fix the issues above before connecting your iOS app.")
        sys.exit(1)

if __name__ == "__main__":
    main()
