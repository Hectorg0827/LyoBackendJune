
import asyncio
import sys
import os
import aiohttp
import json

# Add project root to path
sys.path.append(os.getcwd())

async def verify_a2a_connection():
    print("🤖 Verifying A2A Backend Connection...")
    
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        # 1. Check Health
        try:
            async with session.get(f"{base_url}/health") as resp:
                if resp.status == 200:
                    print("   ✅ Backend is HEALTHY")
                else:
                    print(f"   ❌ Backend Health Check Failed: {resp.status}")
                    return
        except Exception as e:
            print(f"   ❌ Connection Failed: {e}")
            return

        # 2. Trigger Generation
        print("   - Requesting A2A Course Generation...")
        payload = {
            "request": "Quantum Computing 101", # Matches A2ACourseRequest 'request' field or 'topic' depending on schema
            "topic": "Quantum Computing 101",   # Providing both to be safe
            "quality_tier": "fast",
            "user_context": {
                "level": "beginner",
                "style": "socratic"
            }
        }
        
        task_id = None
        
        try:
            async with session.post(f"{base_url}/api/v1/chat/a2a/generate", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    task_id = data.get('task_id')
                    print(f"   ✅ A2A Generation Triggered: {task_id}")
                else:
                    text = await resp.text()
                    print(f"   ❌ A2A Request Failed: {resp.status} - {text}")
                    return
        except Exception as e:
            print(f"   ❌ Generation Request Error: {e}")
            return
            
        # 3. Poll for Status
        if task_id:
            print(f"   - Polling Status for {task_id}...")
            max_retries = 30
            for i in range(max_retries):
                await asyncio.sleep(2)
                try:
                    async with session.get(f"{base_url}/api/v1/chat/a2a/status/{task_id}") as resp:
                        if resp.status == 200:
                            status_data = await resp.json()
                            status = status_data.get("status")
                            progress = status_data.get("progress_percent", 0)
                            stage = status_data.get("current_stage")
                            
                            print(f"     Status: {status} ({progress}%) - Stage: {stage}")
                            
                            if status == "completed":
                                print("   ✅ Task Completed!")
                                break
                            elif status == "failed":
                                print("   ❌ Task Failed!")
                                break
                        else:
                            print(f"     ⚠️ Status check failed: {resp.status}")
                except Exception as e:
                     print(f"     ⚠️ Polling error: {e}")
            
            # 4. Fetch Result
            print("   - Fetching Final Result...")
            async with session.get(f"{base_url}/api/v1/chat/a2a/result/{task_id}") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   ✅ Result Fetched: {result.get('title')}")
                    print(f"      ID: {result.get('course_id')}")
                else:
                    print(f"   ❌ Failed to fetch result: {resp.status}")

if __name__ == "__main__":
    asyncio.run(verify_a2a_connection())
