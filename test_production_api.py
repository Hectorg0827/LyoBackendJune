#!/usr/bin/env python3
"""
Production API Test - Verifies all endpoints are working
Run: python3 test_production_api.py
"""

import asyncio
import aiohttp
import json
import time

BASE_URL = "https://lyo-backend-production-830162750094.us-central1.run.app"

async def test_endpoint(session, name, method, path, data=None, expected_status=200):
    """Test a single endpoint"""
    url = f"{BASE_URL}{path}"
    start = time.time()
    
    try:
        if method == "GET":
            async with session.get(url) as resp:
                status = resp.status
                body = await resp.text()
        else:
            async with session.post(url, json=data) as resp:
                status = resp.status
                body = await resp.text()
        
        elapsed = int((time.time() - start) * 1000)
        
        if status == expected_status:
            print(f"✅ {name}: {status} ({elapsed}ms)")
            try:
                return json.loads(body)
            except:
                return body
        else:
            print(f"❌ {name}: Expected {expected_status}, got {status} ({elapsed}ms)")
            print(f"   Response: {body[:200]}")
            return None
            
    except Exception as e:
        print(f"❌ {name}: Error - {e}")
        return None

async def main():
    print("=" * 60)
    print("🧪 LYO BACKEND PRODUCTION API TEST")
    print(f"🌐 URL: {BASE_URL}")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # 1. Health Check
        print("\n📊 HEALTH & STATUS")
        health = await test_endpoint(session, "Health Check", "GET", "/health")
        if health:
            print(f"   Version: {health.get('version')}")
            print(f"   Environment: {health.get('environment')}")
            print(f"   AI Status: {health.get('services', {}).get('ai', {}).get('models', {})}")
        
        # 2. AI Generate - Educational Explanation
        print("\n🤖 AI GENERATION TESTS")
        
        ai_result = await test_endpoint(
            session, 
            "AI Explain (Gemini)", 
            "POST", 
            "/api/v1/ai/generate",
            {
                "prompt": "What is Python?",
                "task_type": "EDUCATIONAL_EXPLANATION",
                "temperature": 0.7,
                "max_tokens": 500
            }
        )
        
        if ai_result:
            response = ai_result.get("response", "")
            if response:
                print(f"   ✅ Got response: {response[:100]}...")
                print(f"   Model: {ai_result.get('model_used')}")
                print(f"   Tokens: {ai_result.get('tokens_used')}")
            else:
                print(f"   ❌ Empty response! Full result: {ai_result}")
        
        # 3. AI Generate - Course
        print("\n📚 COURSE GENERATION TEST")
        
        course_result = await test_endpoint(
            session,
            "Course Generation",
            "POST",
            "/api/v1/ai/generate",
            {
                "prompt": "Basic mathematics",
                "task_type": "COURSE_GENERATION",
                "temperature": 0.7,
                "max_tokens": 2000
            }
        )
        
        if course_result:
            response = course_result.get("response", "")
            if response:
                print(f"   ✅ Course generated! Length: {len(response)} chars")
                print(f"   Preview: {response[:200]}...")
                print(f"   Model: {course_result.get('model_used')}")
            else:
                print(f"   ❌ Empty course response!")
        
        # 4. AI Classroom
        print("\n🎓 AI CLASSROOM TEST")
        
        classroom_result = await test_endpoint(
            session,
            "AI Classroom Chat",
            "POST",
            "/api/v1/classroom/chat",
            {
                "message": "Teach me about algorithms",
                "session_id": None,
                "include_audio": False
            }
        )
        
        if classroom_result:
            content = classroom_result.get("content", "")
            if content:
                print(f"   ✅ Classroom response: {content[:100]}...")
                print(f"   Response type: {classroom_result.get('response_type')}")
                print(f"   State: {classroom_result.get('state')}")
        
        # 5. TTS Voices
        print("\n🔊 TTS TEST")
        
        voices_result = await test_endpoint(
            session,
            "TTS Voices",
            "GET",
            "/api/v1/tts/voices"
        )
        
        if voices_result:
            voices = voices_result.get("voices", [])
            print(f"   ✅ Available voices: {len(voices)}")
        
        # 6. Image Gen Types
        print("\n🖼️ IMAGE GENERATION TEST")
        
        image_types = await test_endpoint(
            session,
            "Image Types",
            "GET",
            "/api/v1/images/types"
        )
        
        if image_types:
            types = image_types.get("image_types", [])
            print(f"   ✅ Available types: {len(types)}")
        
        # Summary
        print("\n" + "=" * 60)
        print("📋 TEST COMPLETE")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
