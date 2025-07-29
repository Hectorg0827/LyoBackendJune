#!/usr/bin/env python3
"""
iOS Connection Simulation Script
Simulates iOS app connecting to the backend and tests all critical paths.
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any, Optional

class iOSConnectionSimulator:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.auth_token = None
        self.user_id = None
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def simulate_app_launch(self) -> bool:
        """Simulate iOS app launch sequence"""
        print("📱 Simulating iOS App Launch...")
        
        # 1. Check backend connectivity
        try:
            async with self.session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    print("✅ Backend connectivity confirmed")
                    return True
                else:
                    print(f"❌ Backend not responding: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    async def simulate_user_authentication(self) -> bool:
        """Simulate user login flow"""
        print("\n🔐 Simulating User Authentication...")
        
        # Create test user
        timestamp = int(time.time())
        user_data = {
            "email": f"ios_test_{timestamp}@example.com",
            "username": f"ios_user_{timestamp}",
            "password": "iOSTestPassword123!",
            "full_name": "iOS Test User"
        }
        
        # Register user
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/register",
                json=user_data
            ) as response:
                if response.status in [200, 201]:
                    user_response = await response.json()
                    self.user_id = user_response.get("id")
                    print("✅ User registration successful")
                else:
                    print(f"❌ Registration failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Registration error: {e}")
            return False
        
        # Login user
        try:
            login_data = {
                "username": user_data["username"],
                "password": user_data["password"]
            }
            
            async with self.session.post(
                f"{self.base_url}/api/v1/auth/login",
                data=login_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as response:
                if response.status == 200:
                    auth_response = await response.json()
                    self.auth_token = auth_response.get("access_token")
                    print("✅ User login successful")
                    return True
                else:
                    print(f"❌ Login failed: {response.status}")
                    return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    async def simulate_main_feed_loading(self) -> bool:
        """Simulate loading main app feeds"""
        print("\n📰 Simulating Main Feed Loading...")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Load stories
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/social/stories",
                headers=headers
            ) as response:
                if response.status == 200:
                    stories = await response.json()
                    print(f"✅ Stories loaded: {len(stories) if isinstance(stories, list) else 'N/A'}")
                else:
                    print(f"⚠️ Stories endpoint: {response.status}")
        except Exception as e:
            print(f"⚠️ Stories error: {e}")
        
        # Load social feed
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/feeds/",
                headers=headers
            ) as response:
                if response.status == 200:
                    feed = await response.json()
                    print(f"✅ Social feed loaded")
                else:
                    print(f"⚠️ Feed endpoint: {response.status}")
        except Exception as e:
            print(f"⚠️ Feed error: {e}")
        
        # Load learning content
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/learning/courses",
                headers=headers
            ) as response:
                if response.status == 200:
                    courses = await response.json()
                    print(f"✅ Learning content loaded")
                else:
                    print(f"⚠️ Learning endpoint: {response.status}")
        except Exception as e:
            print(f"⚠️ Learning error: {e}")
        
        return True
    
    async def simulate_story_creation(self) -> Optional[str]:
        """Simulate creating a story"""
        print("\n📸 Simulating Story Creation...")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return None
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        story_data = {
            "content": "This is a test story from iOS app simulation!",
            "content_type": "text"
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/social/stories/",
                json=story_data,
                headers=headers
            ) as response:
                if response.status in [200, 201]:
                    story = await response.json()
                    story_id = story.get("id")
                    print(f"✅ Story created: {story_id}")
                    return story_id
                else:
                    print(f"⚠️ Story creation: {response.status}")
                    return None
        except Exception as e:
            print(f"⚠️ Story creation error: {e}")
            return None
    
    async def simulate_messaging(self) -> bool:
        """Simulate messaging functionality"""
        print("\n💬 Simulating Messaging...")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Create conversation
        conversation_data = {
            "name": "iOS Test Chat",
            "participant_ids": [self.user_id] if self.user_id else [],
            "is_group": False
        }
        
        conversation_id = None
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/social/conversations/",
                json=conversation_data,
                headers=headers
            ) as response:
                if response.status in [200, 201]:
                    conversation = await response.json()
                    conversation_id = conversation.get("id")
                    print(f"✅ Conversation created: {conversation_id}")
                else:
                    print(f"⚠️ Conversation creation: {response.status}")
        except Exception as e:
            print(f"⚠️ Conversation error: {e}")
        
        # Send message (if conversation created)
        if conversation_id:
            message_data = {
                "content": "Hello from iOS app simulation!",
                "message_type": "text"
            }
            
            try:
                async with self.session.post(
                    f"{self.base_url}/api/v1/social/conversations/{conversation_id}/messages",
                    json=message_data,
                    headers=headers
                ) as response:
                    if response.status in [200, 201]:
                        print("✅ Message sent successfully")
                    else:
                        print(f"⚠️ Message sending: {response.status}")
            except Exception as e:
                print(f"⚠️ Message error: {e}")
        
        return True
    
    async def simulate_ai_interaction(self) -> bool:
        """Simulate AI chat interaction"""
        print("\n🤖 Simulating AI Interaction...")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        ai_request = {
            "message": "Hello AI! Can you help me learn Python programming?",
            "model": "gpt-3.5-turbo"
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/v1/ai/chat",
                json=ai_request,
                headers=headers
            ) as response:
                if response.status == 200:
                    ai_response = await response.json()
                    response_text = ai_response.get("response", "No response")
                    print(f"✅ AI response: {response_text[:100]}...")
                    return True
                else:
                    print(f"⚠️ AI chat: {response.status}")
                    return False
        except Exception as e:
            print(f"⚠️ AI chat error: {e}")
            return False
    
    async def simulate_file_upload(self) -> bool:
        """Simulate file upload"""
        print("\n📁 Simulating File Upload...")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Create test file data
        test_file_content = b"iOS app test file content"
        
        try:
            data = aiohttp.FormData()
            data.add_field('file', test_file_content, 
                         filename='ios_test.txt', 
                         content_type='text/plain')
            
            async with self.session.post(
                f"{self.base_url}/files/upload",
                data=data,
                headers=headers
            ) as response:
                if response.status in [200, 201]:
                    upload_result = await response.json()
                    print(f"✅ File uploaded: {upload_result.get('filename')}")
                    return True
                else:
                    print(f"⚠️ File upload: {response.status}")
                    return False
        except Exception as e:
            print(f"⚠️ File upload error: {e}")
            return False
    
    async def simulate_gamification_check(self) -> bool:
        """Simulate checking gamification progress"""
        print("\n🎮 Simulating Gamification Check...")
        
        if not self.auth_token:
            print("❌ No auth token available")
            return False
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # Check user's gamification profile
        try:
            async with self.session.get(
                f"{self.base_url}/api/v1/gamification/profile",
                headers=headers
            ) as response:
                if response.status == 200:
                    profile = await response.json()
                    print(f"✅ Gamification profile loaded")
                    return True
                else:
                    print(f"⚠️ Gamification profile: {response.status}")
                    return False
        except Exception as e:
            print(f"⚠️ Gamification error: {e}")
            return False
    
    async def run_complete_simulation(self) -> Dict[str, bool]:
        """Run complete iOS app simulation"""
        print("🚀 Starting Complete iOS App Connection Simulation\n")
        
        results = {}
        
        # App launch
        results["app_launch"] = await self.simulate_app_launch()
        if not results["app_launch"]:
            return results
        
        # Authentication
        results["authentication"] = await self.simulate_user_authentication()
        
        # Main features (even if auth fails, test what we can)
        results["feed_loading"] = await self.simulate_main_feed_loading()
        results["story_creation"] = await self.simulate_story_creation() is not None
        results["messaging"] = await self.simulate_messaging()
        results["ai_interaction"] = await self.simulate_ai_interaction()
        results["file_upload"] = await self.simulate_file_upload()
        results["gamification"] = await self.simulate_gamification_check()
        
        return results

async def main():
    """Main simulation runner"""
    async with iOSConnectionSimulator() as simulator:
        results = await simulator.run_complete_simulation()
        
        # Print results summary
        print("\n" + "="*60)
        print("📱 iOS CONNECTION SIMULATION RESULTS")
        print("="*60)
        
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)
        
        for feature, success in results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            feature_name = feature.replace("_", " ").title()
            print(f"{feature_name:20} {status}")
        
        print(f"\nSummary: {passed_tests}/{total_tests} features working")
        
        if passed_tests == total_tests:
            print("🎉 All iOS connection tests passed! Your backend is ready.")
        elif passed_tests >= total_tests * 0.7:
            print("⚠️  Most features working. Some endpoints may need implementation.")
        else:
            print("❌ Several issues found. Check backend implementation.")
        
        return passed_tests >= total_tests * 0.7

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
