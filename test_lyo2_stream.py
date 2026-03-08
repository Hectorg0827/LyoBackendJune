import asyncio
import httpx
import json

async def test_stream():
    url = "http://localhost:8000/api/v1/lyo2/chat/stream"
    payload = {
        "user_id": "test_user",
        "text": "Hello Lyo! What can you do?"
    }
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": "dev_key"
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                print(f"Status Code: {response.status_code}")
                # We expect to see 'a2ui' event emitted
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            print("\nStream completed.")
                            break
                        try:
                            data = json.loads(data_str)
                            print(f"\nReceived event type: {data.get('type')}")
                            if data.get('type') == 'a2ui':
                                print(f"SUCCESS: Received A2UI block!")
                                print(json.dumps(data, indent=2)[:500] + "\n...")
                        except json.JSONDecodeError:
                            print(f"Failed to decode: {data_str}")
    except Exception as e:
        print(f"Error testing stream: {e}")

if __name__ == "__main__":
    asyncio.run(test_stream())
