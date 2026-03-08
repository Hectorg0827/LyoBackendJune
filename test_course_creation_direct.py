from fastapi.testclient import TestClient
from lyo_app.main import app
import json

def run_test():
    # Mock embedding service
    from lyo_app.services.embedding_service import embedding_service
    async def mock_embed(*args, **kwargs):
        return [0.0] * 768
    embedding_service.embed_text = mock_embed
    
    print("Initializing TestClient with lifespan...")
    payload = {
        "title": "Intro to Python",
        "topic": "Python",
        "level": "beginner",
        "difficulty_level": "beginner",
        "instructor_id": 1
    }
    with TestClient(app) as client:
        print("Sending POST request to /api/v1/learning/courses")
        response = client.post(
            "/api/v1/learning/courses",
            json=payload
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    run_test()
