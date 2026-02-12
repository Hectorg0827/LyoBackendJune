
import asyncio
import httpx
import uuid
import sys
import json

BASE_URL = "https://lyo-backend-830162750094.us-central1.run.app"

async def verify_community_events():
    print(f"🧪 Verifying Community Events API at: {BASE_URL}")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Register a temp user
        unique_id = str(uuid.uuid4())[:8]
        user_data = {
            "email": f"test_verify_{unique_id}@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "username": f"verifier_{unique_id}",
            "first_name": "Test",
            "last_name": "Verifier"
        }
        
        print(f"👤 Registering temp user: {user_data['email']}...")
        try:
            # TRYING THE NEW /auth/register endpoint which supports JSON and full model
            reg_resp = await client.post(f"{BASE_URL}/auth/register", json=user_data)
            
            if reg_resp.status_code != 201:
                print(f"❌ Registration failed: {reg_resp.status_code}")
                print(reg_resp.text)
                return False

            data = reg_resp.json()
            token = data.get("access_token")
            if not token:
                print("❌ No access token in registration response")
                return False
                
            print("✅ Registered and got access token")
            
        except Exception as e:
            print(f"❌ Auth error: {e}")
            return False

        # Step 2: Call the problematic endpoint
                
            print("✅ Registered and got access token")
            
        except Exception as e:
            print(f"❌ Auth error: {e}")
            return False

        # Step 2: Call the problematic endpoint
        print("🚀 Calling GET /api/v1/community/events (Authenticated)...")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        try:
            # Lat/Lng for San Francisco (as per user request)
            params = {"lat": 37.7749, "lng": -122.4194}
            resp = await client.get(f"{BASE_URL}/api/v1/community/events", headers=headers, params=params)
            
            print(f"Status Code: {resp.status_code}")
            
            if resp.status_code == 200:
                print("✅ Success! Endpoint returned 200 OK")
                print(f"Response: {resp.text[:200]}...") # Print first 200 chars
                return True
            elif resp.status_code == 500:
                print("❌ Failed: Still returning 500 Internal Server Error")
                print(resp.text)
                return False
            else:
                print(f"⚠️ Unexpected status: {resp.status_code}")
                print(resp.text)
                return False
                
        except Exception as e:
            print(f"❌ Request error: {e}")
            return False

if __name__ == "__main__":
    success = asyncio.run(verify_community_events())
    if not success:
        sys.exit(1)
