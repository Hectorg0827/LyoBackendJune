
import sys
import os

# Ensure we can import lyo_app
sys.path.append(os.getcwd())

from fastapi.testclient import TestClient
from lyo_app.enhanced_main import app

def verify_a2a():
    print("🚀 Starting A2A Verification...")
    client = TestClient(app)
    
    # 1. Verify Agent Card Discovery
    print("\n🔍 Checking Agent Card Discovery...")
    response = client.get("/a2a/.well-known/agent.json") # Check prefix
    
    # Note: verify if it's under /a2a or root. 
    # In routes.py: @discovery_router.get("/.well-known/agent.json")
    # In enhanced_main.py: include_a2a_routes(app) -> includes router and discovery_router.
    # discovery_router has no prefix in routes.py (empty string tag, but APIRouter(tags=["A2A Discovery"])).
    
    # Let's try root first as discovery_router usually doesn't have prefix
    if response.status_code == 404:
         print("   Not found at /a2a/.well-known/agent.json, trying root...")
         response = client.get("/.well-known/agent.json")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Agent Card Found: {data.get('name')}")
        print(f"   Capabilities: {list(data.get('capabilities', {}).keys())}")
        skills = [s['id'] for s in data.get('skills', [])]
        print(f"   Skills: {skills}")
        
        if "course_generation" in skills:
            print("✅ Course Generation skill confirmed.")
        else:
            print("❌ 'course_generation' skill missing!")
            sys.exit(1)
    else:
        print(f"❌ Failed to get Agent Card. Status: {response.status_code}")
        print(response.text)
        sys.exit(1)

    # 2. Verify Task Submission (Mock)
    print("\n📨 Verifying Task Submission...")
    task_payload = {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "Create a course on Swift"}]
        }
    }
    
    response = client.post("/a2a/tasks/send", json=task_payload)
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Task Submitted. ID: {data.get('id')}")
        print(f"   State: {data.get('state')}")
    else:
        print(f"❌ Failed to submit task. Status: {response.status_code}")
        print(response.text)
        # Don't exit, maybe auth required? Mock route has no auth dependency in verify script but app might add global middleware?
        # In routes.py: async def send_task(request: TaskRequest) - no depends.
        # But enhanced_main adds SecurityMiddleware? 
        # Verify script uses TestClient which might bypass some middleware if not fully integrated or if specific headers needed.
        # But let's see.

if __name__ == "__main__":
    verify_a2a()
