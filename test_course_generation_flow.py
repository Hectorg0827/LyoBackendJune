#!/usr/bin/env python3
"""
Test A2A → A2UI Course Generation Flow

Tests:
1. Backend /api/v2/courses/generate endpoint
2. Job polling /api/v2/courses/status/{job_id}
3. Result retrieval /api/v2/courses/{job_id}/result
4. Chat → Course creation via /api/v1/ai/chat
"""

import asyncio
import httpx
import json
import time
from typing import Dict, Any

# Configuration
BASE_URL = "http://localhost:8000"
TEST_USER_EMAIL = "tester@example.com"
TEST_USER_PASSWORD = "Test123456!"

async def login() -> str:
    """Login and get access token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            return data["access_token"]
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(response.text)
            return None


async def test_course_generation_v2(token: str):
    """Test V2 course generation API"""
    print("\n" + "=" * 60)
    print("TEST: V2 Course Generation API")
    print("=" * 60)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=300.0) as client:
        # Step 1: Submit job
        print("\n📤 Step 1: Submitting course generation job...")
        response = await client.post(
            f"{BASE_URL}/api/v2/courses/generate",
            headers=headers,
            json={
                "request": "Python programming for beginners",
                "quality_tier": "standard",
                "enable_code_examples": True,
                "enable_practice_exercises": True,
                "enable_final_quiz": True
            }
        )
        
        if response.status_code != 200:
            print(f"❌ Job submission failed: {response.status_code}")
            print(response.text)
            return False
        
        job_data = response.json()
        job_id = job_data["job_id"]
        print(f"✅ Job submitted: {job_id}")
        print(f"💰 Estimated cost: ${job_data['estimated_cost_usd']}")
        
        # Step 2: Poll for completion
        print(f"\n⏳ Step 2: Polling for completion...")
        max_attempts = 60
        for attempt in range(max_attempts):
            response = await client.get(
                f"{BASE_URL}/api/v2/courses/status/{job_id}",
                headers=headers
            )
            
            if response.status_code != 200:
                print(f"❌ Status check failed: {response.status_code}")
                return False
            
            status_data = response.json()
            status = status_data["status"]
            progress = status_data["progress_percent"]
            step = status_data.get("current_step", "")
            
            print(f"📊 [{attempt + 1}/{max_attempts}] Status: {status} - {progress}% - {step}")
            
            if status == "completed":
                print("✅ Course generation completed!")
                break
            elif status == "failed":
                error = status_data.get("error", "Unknown error")
                print(f"❌ Course generation failed: {error}")
                return False
            
            await asyncio.sleep(5)
        else:
            print("❌ Timeout waiting for completion")
            return False
        
        # Step 3: Retrieve result
        print(f"\n📥 Step 3: Retrieving course result...")
        response = await client.get(
            f"{BASE_URL}/api/v2/courses/{job_id}/result",
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"❌ Result retrieval failed: {response.status_code}")
            print(response.text)
            return False
        
        course_data = response.json()
        print("✅ Course retrieved successfully!")
        print(f"\n📚 Course Details:")
        print(f"  Title: {course_data['title']}")
        print(f"  Description: {course_data['description']}")
        print(f"  Modules: {len(course_data['modules'])}")
        print(f"  Duration: {course_data['estimated_duration']} minutes")
        print(f"  Difficulty: {course_data['difficulty']}")
        
        # Show first lesson
        if course_data['modules']:
            first_module = course_data['modules'][0]
            print(f"\n  📖 First Module: {first_module['title']}")
            if first_module['lessons']:
                first_lesson = first_module['lessons'][0]
                print(f"    → Lesson: {first_lesson['title']}")
                print(f"    → Duration: {first_lesson['duration_minutes']} min")
        
        return True


async def test_chat_course_creation(token: str):
    """Test chat-based course creation (A2A → A2UI flow)"""
    print("\n" + "=" * 60)
    print("TEST: Chat → Course Creation (A2A → A2UI)")
    print("=" * 60)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("\n💬 Sending course creation request via chat...")
        response = await client.post(
            f"{BASE_URL}/api/v1/ai/chat",
            headers=headers,
            json={
                "message": "Create a course on Machine Learning basics",
                "conversation_history": []
            }
        )
        
        if response.status_code != 200:
            print(f"❌ Chat request failed: {response.status_code}")
            print(response.text)
            return False
        
        chat_data = response.json()
        print(f"✅ Chat response received")
        print(f"\n📝 Response: {chat_data['response'][:200]}...")
        
        # Check for UI component
        ui_component = chat_data.get("ui_component")
        if ui_component:
            print(f"\n🎨 UI Component detected: {len(ui_component)} components")
            for idx, component in enumerate(ui_component):
                comp_type = component.get("type", "unknown")
                print(f"  [{idx + 1}] Type: {comp_type}")
                
                if comp_type == "course_roadmap":
                    roadmap = component.get("course_roadmap", {})
                    print(f"      Title: {roadmap.get('title', 'N/A')}")
                    print(f"      Modules: {len(roadmap.get('modules', []))}")
                elif comp_type == "quiz":
                    quiz = component.get("quiz", {})
                    print(f"      Title: {quiz.get('title', 'N/A')}")
                    print(f"      Questions: {len(quiz.get('questions', []))}")
        else:
            print("⚠️ No UI components in response")
        
        return True


async def main():
    """Run all tests"""
    print("🧪 Testing A2A → A2UI Course Generation Flow")
    print("=" * 60)
    
    # Login
    print("\n🔐 Logging in...")
    token = await login()
    if not token:
        print("❌ Cannot proceed without authentication")
        return
    
    print("✅ Authenticated successfully")
    
    # Test V2 API
    v2_success = await test_course_generation_v2(token)
    
    # Test Chat flow
    chat_success = await test_chat_course_creation(token)
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"V2 Course Generation: {'✅ PASS' if v2_success else '❌ FAIL'}")
    print(f"Chat Course Creation: {'✅ PASS' if chat_success else '❌ FAIL'}")
    print("\n" + ("🎉 ALL TESTS PASSED" if v2_success and chat_success else "❌ SOME TESTS FAILED"))


if __name__ == "__main__":
    asyncio.run(main())
