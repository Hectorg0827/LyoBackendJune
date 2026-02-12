import asyncio
import httpx
import json
import jwt
import datetime

# Prod URL
BASE_URL = "https://lyo-backend-830162750094.us-central1.run.app"

# We need a token. We'll try to generate a dummy one if we knew the secret, 
# but for now we will just test the public health endpoint and stories (expecting 401) 
# and maybe just print what to run manually.

async def test_stories():
    print(f"Testing {BASE_URL}/api/v1/stories...")
    async with httpx.AsyncClient() as client:
        try:
            # Test 1: Unauthenticated
            resp = await client.get(f"{BASE_URL}/api/v1/stories")
            print(f"Unauth Status: {resp.status_code}")
            
            if resp.status_code == 500:
                print("❌ ERROR: Still getting 500!")
            elif resp.status_code == 401:
                 print("✅ Success (Got 401 as expected for unauth)")
            elif resp.status_code == 200:
                 print("✅ Success (Got 200!!)")
            else:
                 print(f"⚠️ Unexpected status: {resp.status_code}")

        except Exception as e:
            print(f"Connection failed: {e}")

async def test_chat_stream():
    print(f"\nTesting {BASE_URL}/api/v1/chat/stream... (Mock test)")
    # Since we can't easily auth, we just verify the endpoint exists (405 or 401)
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/api/v1/chat/stream")
        print(f"Status: {resp.status_code}")
        if resp.status_code != 404:
             print("✅ Endpoint exists (not 404)")
        else:
             print("❌ Endpoint 404!")

if __name__ == "__main__":
    asyncio.run(test_stories())
    asyncio.run(test_chat_stream())
