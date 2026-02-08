import asyncio
import httpx
import json
import sys
import os

# Default to production if not provided
BASE_URL = os.getenv("LYO_PROD_URL", "https://lyo-backend-production-xxxxxxxx-uc.a.run.app") + "/api/v1/lyo2"

async def test_prod_stream():
    print(f"🚀 Testing Lyo 2.0 Production Stream at {BASE_URL}...")
    
    # Needs a real valid token for production usually, or at least API key if auth is bypassed for debugging
    # Assuming we might need a token.
    token = os.getenv("AUTH_TOKEN", "test_token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-API-Key": os.getenv("API_KEY", "test_api_key")
    }
    
    payload = {
        "text": "Explain photosynthesis to a 5 year old",
        "history": []
    }
    
    try:
        url = f"{BASE_URL}/chat/stream"
        print(f"Connecting to {url}...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                print(f"Status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"❌ Error: {response.status_code}")
                    print(await response.aread())
                    return

                print("✅ Stream connected! Receiving events...")
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            print("✅ [DONE] validated")
                            break
                        try:
                            json_data = json.loads(data)
                            event_type = json_data.get("type")
                            print(f"   -> Event: {event_type}")
                            if event_type == "answer":
                                content = json_data.get("block", {}).get("content", {}).get("markdown", {}).get("value", "")
                                print(f"      Content: {content[:50]}...")
                        except:
                            print(f"   -> Raw: {data[:50]}...")
                            
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        BASE_URL = sys.argv[1] + "/api/v1/lyo2"
    
    # Determine URL
    if "xxxxxxxx" in BASE_URL:
        print("⚠️  Please set LYO_PROD_URL environment variable or pass the base URL as an argument.")
        print("Example: python verify_prod_lyo2.py https://lyo-backend-production-123456-uc.a.run.app")
        sys.exit(1)

    asyncio.run(test_prod_stream())
