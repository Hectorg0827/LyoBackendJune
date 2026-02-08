import sys
import os
import json
import asyncio
from datetime import datetime

# Ensure we can import lyo_app
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from lyo_app.enhanced_main import app
from lyo_app.auth.dependencies import get_current_user
from lyo_app.auth.schemas import UserRead

async def mock_get_current_user():
    return UserRead(
        id=1,
        email="test@lyo.app",
        username="testuser",
        first_name="Test",
        last_name="User",
        is_active=True,
        is_verified=True,
        created_at=datetime.utcnow()
    )

app.dependency_overrides[get_current_user] = mock_get_current_user

def verify_sse_stream():
    print("🚀 Starting Dry-Run SSE Verification...")
    client = TestClient(app)
    
    payload = {
        "request": "The Physics of Black Holes",
        "quality_tier": "standard",
        "user_context": {
            "difficulty": "beginner"
        }
    }
    
    print("📡 Requesting /api/v2/courses/stream-a2a...")
    
    with client.stream("POST", "/api/v2/courses/stream-a2a", json=payload) as response:
        print(f"Status Code: {response.status_code}")
        if response.status_code != 200:
            response.read()
            print(f"❌ Failed: {response.text}")
            return
            
        print("\n📊 SSE Stream Events:")
        print("-" * 50)
        
        for line in response.iter_lines():
            if not line:
                continue
                
            if line.startswith("data: "):
                data_str = line[6:]
                print(f"📥 Received: {data_str}")
                
                try:
                    data = json.loads(data_str)
                    # Check for mandatory protocol keys
                    required = ["event_type", "pipeline_id", "timestamp"]
                    missing = [k for k in required if k not in data]
                    if missing:
                        print(f"❌ Missing keys in SSE data: {missing}")
                    else:
                        print(f"✅ Format OK: {data.get('event_type')} Phase: {data.get('phase', 'None')}")
                    
                    if data.get("event_type") == "pipeline_completed":
                        print("\n🏁 Pipeline Completed in stream!")
                        break
                        
                except json.JSONDecodeError:
                    print(f"❌ JSON Decode Error: {data_str}")

if __name__ == "__main__":
    verify_sse_stream()
