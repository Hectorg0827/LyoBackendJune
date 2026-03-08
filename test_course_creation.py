import asyncio
import json
from httpx import AsyncClient

async def run_test():
    payload = {
        "title": "Intro to Python",
        "topic": "Python",
        "level": "beginner",
        "difficulty_level": "beginner",
        "instructor_id": 1
    }
    
    async with AsyncClient() as client:
        # Assuming the server is running on localhost:8000
        response = await client.post(
            "http://127.0.0.1:8000/api/v1/learning/courses",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    asyncio.run(run_test())
